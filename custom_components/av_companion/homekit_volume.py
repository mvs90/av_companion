"""Instance-scoped absolute-volume compatibility for AV HomeKit televisions.

Some HA HomeKit TelevisionMediaPlayer versions neither normalize the HAP
percentage on write nor synchronize its absolute Volume characteristic on read.
Bind only this AV entity's existing accessory; never patch HomeKit classes,
recreate accessories, or issue a command while attaching/updating feedback.
"""

from datetime import timedelta
import logging
import math
from numbers import Real

from homeassistant.core import callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

_LOGGER = logging.getLogger(__name__)


def percent_to_level(value):
    """Normalize a valid HAP percentage, including 1% (which is not 100%)."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return float(value) / 100.0


def level_to_percent(value):
    """Return feedback only for valid HA levels; unknown is never guessed as 0."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    if not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return int(round(value * 100))


class HomeKitVolumeAdapter:
    """Manage callbacks for only one AV entity and restore them on unload."""

    def __init__(self, hass, entity_id):
        self.hass = hass
        self.entity_id = entity_id
        self._bindings = {}
        self._entry_unsubs = {}
        self._unsubs = []
        self._active = False

    @callback
    def start(self):
        if self._active or self.hass.config_entries is None:
            return
        self._active = True
        self._unsubs = [
            async_track_state_change_event(self.hass, [self.entity_id], self._changed),
            # Also catch HomeKit accessory recreation/reload while AV is idle.
            async_track_time_interval(self.hass, self._changed, timedelta(seconds=15)),
        ]
        self._reconcile()

    @callback
    def _changed(self, _event=None):
        if self._active:
            self._reconcile()

    @callback
    def _reconcile(self):
        entries = self.hass.config_entries.async_entries("homekit")
        entry_ids = {entry.entry_id for entry in entries}
        for entry_id in set(self._entry_unsubs) - entry_ids:
            self._entry_unsubs.pop(entry_id)()
        found = {}
        for entry in entries:
            if entry.entry_id not in self._entry_unsubs:
                self._entry_unsubs[entry.entry_id] = entry.async_on_state_change(
                    self._changed
                )
            runtime = getattr(entry, "runtime_data", None)
            homekit = getattr(runtime, "homekit", None)
            driver = getattr(homekit, "driver", None)
            root = getattr(driver, "accessory", None)
            if root is None:
                continue
            children = getattr(root, "accessories", None)
            candidates = children.values() if isinstance(children, dict) else [root]
            for accessory in candidates:
                if getattr(accessory, "entity_id", None) != self.entity_id:
                    continue
                char = getattr(accessory, "char_volume", None)
                if (
                    char is None
                    or not hasattr(char, "setter_callback")
                    or not callable(getattr(accessory, "async_call_service", None))
                ):
                    continue
                found[id(accessory)] = (accessory, char)
        for key in set(self._bindings) - set(found):
            self._restore(self._bindings.pop(key))
        for key, (accessory, char) in found.items():
            if key not in self._bindings:
                original = char.setter_callback

                def set_volume(value, *, target=accessory):
                    if not self._active or id(target) not in self._bindings:
                        return
                    level = percent_to_level(value)
                    if level is None:
                        _LOGGER.warning("Ignoring invalid HomeKit AV volume percentage")
                        self._sync_feedback()
                        return
                    # Same HomeKit service dispatcher/context, correctly normalized.
                    target.async_call_service(
                        "media_player", "volume_set",
                        {"entity_id": self.entity_id, "volume_level": level},
                    )

                char.setter_callback = set_volume
                self._bindings[key] = (char, original, set_volume)
        self._sync_feedback()

    @callback
    def _sync_feedback(self):
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state in {"unknown", "unavailable"}:
            return
        percent = level_to_percent(state.attributes.get("volume_level"))
        if percent is None:
            return
        for char, _, _ in self._bindings.values():
            if char.value != percent:
                # Characteristic.set_value updates/announces feedback only. It does
                # NOT call setter_callback (client_update_value is the write path).
                char.set_value(percent)

    @staticmethod
    def _restore(binding):
        char, original, ours = binding
        if char.setter_callback is ours:
            char.setter_callback = original

    @callback
    def stop(self):
        self._active = False
        for unsub in self._unsubs:
            unsub()
        for unsub in self._entry_unsubs.values():
            unsub()
        for binding in self._bindings.values():
            self._restore(binding)
        self._unsubs.clear()
        self._entry_unsubs.clear()
        self._bindings.clear()

    @property
    def diagnostics(self):
        return {"active": self._active, "accessories": len(self._bindings)}
