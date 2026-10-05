"""Media player platform for AV Companion integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Optional

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import DOMAIN, INPUT_SOURCES
from custom_components.lg_rs232_ip.api import DisplayAPI as LGDisplay
from .standby import StandbyGuard
from .controls import ExtendedControls
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

_LINKED_ACTIVE_STATES = {
    STATE_ON,
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_IDLE,
    "buffering",
}

_LINKED_INACTIVE_STATES = {
    STATE_OFF,
    "standby",
}

_UNAVAILABLE_STATES = {"unavailable", "unknown"}

_STARTUP_OFF_GUARD_SECONDS = 15.0
_OFF_CONFIRM_DELAY_SECONDS = 2.0
_DISPLAY_WAKE_TIMEOUT_SECONDS = 30.0
_DISPLAY_UNRESPONSIVE_ALERT_DELAY_SECONDS = 10.0
_AUTOMATION_BLOCKED_TURN_OFF_DELAY_SECONDS = 5.0


def _extract_entity_id(value: Any) -> Optional[str]:
    """Normalize an options value into a media_player entity_id string."""
    if value is None:
        return None

    if isinstance(value, str):
        return value or None

    if isinstance(value, dict):
        entity_id = value.get("entity_id")
        if isinstance(entity_id, str) and entity_id:
            return entity_id

    return None


def _is_restored_state(state_obj: Any) -> bool:
    """Return True if a Home Assistant state object originates from restore-state."""
    if state_obj is None:
        return False
    attrs = getattr(state_obj, "attributes", None)
    if not isinstance(attrs, dict):
        return False
    return bool(attrs.get("restored"))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up media player entities for LG Display."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    lg_display = data["lg_display"]

    player = AVMediaPlayer(
        hass, config_entry, lg_display, data["name"], config_entry.entry_id
    )
    data["media_player"] = player
    async_add_entities([player])
    platform = entity_platform.async_get_current_platform()
    services = {
        "send_remote_command": (
            {
                vol.Required("command"): vol.In(
                    [
                        "up",
                        "down",
                        "left",
                        "right",
                        "select",
                        "menu",
                        "home",
                        "information",
                        "skip_forward",
                        "skip_backward",
                        "next",
                        "previous",
                    ]
                )
            },
            "async_send_remote_command",
        ),
        "show_content": (
            {
                vol.Required("media_id"): cv.string,
                vol.Optional("media_type", default="video"): cv.string,
                vol.Optional("duration", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=3600)
                ),
                vol.Optional("priority", default="normal"): vol.In(
                    ["normal", "urgent"]
                ),
            },
            "async_show_content",
        ),
        "show_notification": (
            {
                vol.Required("message"): cv.string,
                vol.Optional("title", default=""): cv.string,
                vol.Optional("duration", default=10): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=3600)
                ),
                vol.Optional("priority", default="normal"): vol.In(
                    ["normal", "urgent"]
                ),
                vol.Optional("mode", default="overlay"): vol.In(
                    ["overlay", "fullscreen"]
                ),
            },
            "async_show_notification",
        ),
        "show_display_content": (
            {
                vol.Required("kind"): vol.In(["image", "video", "stream", "website"]),
                vol.Required("media_id"): cv.string,
                vol.Optional("duration", default=60): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=3600)
                ),
                vol.Optional("muted", default=True): cv.boolean,
            },
            "async_show_display_content",
        ),
        "clear_content": ({}, "async_clear_content"),
        "set_sound_mode": (
            {
                vol.Required("mode"): vol.In(["night", "speech"]),
                vol.Required("enabled"): cv.boolean,
            },
            "async_set_sound_mode",
        ),
        "announce": (
            {
                vol.Required("media_id"): cv.string,
                vol.Optional("media_type", default="music"): cv.string,
                vol.Optional("volume", default=40): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
            },
            "async_announce",
        ),
    }
    for service, (schema, method) in services.items():
        platform.async_register_entity_service(
            service,
            schema,
            method,
            supports_response=SupportsResponse.OPTIONAL
            if service == "prepare_boot_image"
            else SupportsResponse.NONE,
        )


class AVMediaPlayer(ExtendedControls, MediaPlayerEntity):
    """Media player entity for LG professional displays."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        lg_display: LGDisplay,
        name: str,
        unique_id: str,
    ) -> None:
        self._hass = hass
        self._config_entry = config_entry
        self._lg_display = lg_display
        self._name = name
        self._unique_id = unique_id

        self._state: MediaPlayerState = MediaPlayerState.OFF
        self._volume_level: Optional[float] = None
        self._is_muted: Optional[bool] = None
        self._source: Optional[str] = None
        self._current_input_id: Optional[int] = None
        self._linked_source: Optional[str] = None
        self._linked_source_list: list[str] = []
        self._linked_volume_level: Optional[float] = None
        self._linked_is_muted: Optional[bool] = None
        self._linked_state: Optional[str] = None
        self._linked_media_title: Optional[str] = None
        self._linked_media_artist: Optional[str] = None
        self._linked_media_album_name: Optional[str] = None
        self._linked_media_image_url: Optional[str] = None
        self._linked_state_unsub = None
        self._volume_state_unsub = None
        self._power_supply_state_unsub = None
        self._last_display_power: Optional[bool] = None
        self._pending_state: Optional[MediaPlayerState] = None
        self._pending_state_until: float = 0.0
        self._pending_source: Optional[str] = None
        self._pending_source_until: float = 0.0
        self._startup_off_guard_until: float = (
            time.monotonic() + _STARTUP_OFF_GUARD_SECONDS
        )
        self._ha_stopping = False
        self._ha_stop_unsub = None
        self._display_off_confirm_count = 0
        self._display_off_forwarded = False
        self._power_supply_off_task = None
        self._display_wake_task = None
        self._blocked_linked_turn_off_task = None
        self._display_unresponsive_since: Optional[float] = None
        self._suppress_linked_power_on_until: float = 0.0

        self._init_controls()
        self._standby_guard = StandbyGuard()
        self._standby_latched = False
        self._signal_present: bool | None = None
        self._last_standby_reason: str | None = None
        self._sources, self._source_names_by_id = self._build_input_source_maps()

    @property
    def _any_presentation_active(self):
        return self._presentation_active or self._lg_display.presentation_active

    def _build_input_source_maps(self) -> tuple[dict[str, int], dict[int, str]]:
        """Build visible media-player source names for the display inputs."""
        option_keys = {
            "HDMI 1": "input_name_hdmi1",
            "HDMI 2": "input_name_hdmi2",
            "HDMI 3": "input_name_hdmi3",
        }
        visibility_keys = {
            "HDMI 1": "show_input_hdmi1",
            "HDMI 2": "show_input_hdmi2",
            "HDMI 3": "show_input_hdmi3",
        }
        visible_to_id: dict[str, int] = {}
        id_to_visible: dict[int, str] = {}
        used_names: set[str] = set()

        for canonical_name, source_id in INPUT_SOURCES.items():
            if not bool(
                self._config_entry.options.get(visibility_keys[canonical_name], True)
            ):
                continue

            configured_name = self._config_entry.options.get(
                option_keys.get(canonical_name, ""), canonical_name
            )
            visible_name = str(configured_name).strip() or canonical_name
            if visible_name in used_names:
                visible_name = canonical_name
            if visible_name in used_names:
                visible_name = f"{canonical_name} ({source_id:02x})"

            used_names.add(visible_name)
            visible_to_id[visible_name] = source_id
            id_to_visible[source_id] = visible_name

        return visible_to_id, id_to_visible

    @property
    def _linked_input_name(self) -> str:
        value = str(
            self._config_entry.options.get("linked_media_player_input", "HDMI 1")
        )
        if value in INPUT_SOURCES:
            return value
        return "HDMI 1"

    @property
    def _linked_input_id(self) -> Optional[int]:
        return INPUT_SOURCES.get(self._linked_input_name)

    @property
    def _is_linked_input_active(self) -> bool:
        linked_input_id = self._linked_input_id
        return linked_input_id is not None and self._current_input_id == linked_input_id

    @property
    def _show_linked_app_sources(self) -> bool:
        return bool(self._config_entry.options.get("show_linked_app_sources", True))

    @property
    def _visible_linked_media_sources(self) -> Optional[set[str]]:
        value = self._config_entry.options.get("visible_linked_media_sources")
        if value is None:
            return None

        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if str(item).strip()}

        source_name = str(value).strip()
        return {source_name} if source_name else set()

    def _linked_source_display_map(self) -> dict[str, str]:
        """Map displayed source names to the linked media player's real source names."""
        if not self._linked_entity_id or not self._show_linked_app_sources:
            return {}

        used_names = set(self._sources.keys())
        display_map: dict[str, str] = {}
        candidate_sources: list[str] = []
        visible_sources = self._visible_linked_media_sources

        if self._linked_source:
            candidate_sources.append(self._linked_source)
        candidate_sources.extend(self._linked_source_list)

        for raw_source in candidate_sources:
            source_name = str(raw_source).strip()
            if not source_name or source_name in display_map.values():
                continue
            if visible_sources is not None and source_name not in visible_sources:
                continue

            display_name = source_name
            if display_name in used_names or display_name in display_map:
                display_name = f"{source_name} (App)"
                suffix = 2
                while display_name in used_names or display_name in display_map:
                    display_name = f"{source_name} (App {suffix})"
                    suffix += 1

            display_map[display_name] = source_name

        return display_map

    def _display_name_for_linked_source(
        self, linked_source: Optional[str]
    ) -> Optional[str]:
        """Return the visible source label for a linked media-player source."""
        if not linked_source:
            return None

        for display_name, actual_name in self._linked_source_display_map().items():
            if actual_name == linked_source:
                return display_name

        return None

    def _resolve_source_name(self, input_id: Optional[int]) -> Optional[str]:
        """Resolve the currently exposed media-player source name."""
        if input_id is None:
            return None

        if input_id == self._linked_input_id:
            linked_source_name = self._display_name_for_linked_source(
                self._linked_source
            )
            if linked_source_name:
                return linked_source_name

        return self._source_names_by_id.get(input_id, f"0x{input_id:02x}")

    @property
    def _linked_entity_id(self) -> Optional[str]:
        return _extract_entity_id(
            self._config_entry.options.get("linked_media_player_entity_id")
        )

    @property
    def _linked_volume_sync_mode(self) -> str:
        return str(
            self._config_entry.options.get("linked_volume_sync_mode", "hdmi1_only")
        )

    @property
    def _volume_entity_id(self) -> Optional[str]:
        volume_entity_id = _extract_entity_id(
            self._config_entry.options.get("linked_volume_media_player_entity_id")
        )
        if volume_entity_id is not None:
            return volume_entity_id
        return self._linked_entity_id

    @property
    def _power_supply_switch_entity_id(self) -> Optional[str]:
        return _extract_entity_id(
            self._config_entry.options.get("power_supply_switch_entity_id")
        )

    @property
    def _alert_state(self):
        return (
            self._hass.data.get(DOMAIN, {})
            .get(self._config_entry.entry_id, {})
            .get("alert_state")
        )

    @property
    def _sync_automation_enabled(self) -> bool:
        return bool(
            self.hass.data.get(DOMAIN, {})
            .get(self._config_entry.entry_id, {})
            .get("sync_automation_enabled", True)
        )

    @property
    def _use_linked_content_sync(self) -> bool:
        return self._linked_entity_id is not None and self._is_linked_input_active

    @property
    def _use_linked_volume_sync(self) -> bool:
        if self._volume_entity_id is None:
            return False

        mode = self._linked_volume_sync_mode
        if mode == "always":
            return True
        if mode == "display_only":
            return False
        return self._is_linked_input_active

    @property
    def _pending_power_seconds(self) -> float:
        value = self._config_entry.options.get("media_player_pending_power_seconds", 12)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 12.0

    @property
    def _pending_source_seconds(self) -> float:
        value = self._config_entry.options.get("media_player_pending_source_seconds", 8)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 8.0

    @property
    def _power_supply_off_delay_seconds(self) -> float:
        value = self._config_entry.options.get("power_supply_off_delay_seconds", 5)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 5.0

    @property
    def unique_id(self) -> str:
        return f"{self._unique_id}_media_player"

    @property
    def name(self) -> str:
        return "AV System"

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._name,
            "manufacturer": "AV Companion",
            "model": "Composite AV system",
            "sw_version": self._lg_display.software_version,
        }

    @property
    def device_class(self) -> MediaPlayerDeviceClass:
        return MediaPlayerDeviceClass.TV

    @property
    def state(self) -> MediaPlayerState:
        if self._lg_display.presentation_active:
            return MediaPlayerState.ON
        if self._state != MediaPlayerState.OFF and self._playback_target:
            state = self.hass.states.get(self._playback_target)
            if state and state.state in {"playing", "paused", "idle", "buffering"}:
                return MediaPlayerState(state.state)
        return self._state

    @property
    def available(self) -> bool:
        if not self._lg_display.ready:
            return False
        now = time.monotonic()
        if self._pending_state is not None and now < self._pending_state_until:
            return True

        if self._display_wake_task is not None and not self._display_wake_task.done():
            return True

        if self._linked_entity_id:
            return True

        if self._lg_display.is_intentionally_unpowered:
            return True

        return self._lg_display.is_available

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        feature = MediaPlayerEntityFeature
        supported = feature.TURN_ON | feature.TURN_OFF | feature.SELECT_SOURCE
        if self._playback_target:
            supported |= self._features_for(self._playback_target) & (
                feature.PLAY
                | feature.PAUSE
                | feature.STOP
                | feature.NEXT_TRACK
                | feature.PREVIOUS_TRACK
                | feature.SEEK
                | feature.SHUFFLE_SET
                | feature.REPEAT_SET
            )
        if self._features_for(self._content_target) & feature.PLAY_MEDIA:
            supported |= feature.PLAY_MEDIA
        volume_features = feature.VOLUME_SET | feature.VOLUME_STEP | feature.VOLUME_MUTE
        supported |= (
            self._features_for(self._volume_entity_id) & volume_features
            if self._use_linked_volume_sync
            else volume_features
        )
        return supported

    @property
    def volume_level(self) -> Optional[float]:
        if self._use_linked_volume_sync:
            return self._linked_volume_level
        return self._volume_level

    @property
    def is_volume_muted(self) -> Optional[bool]:
        if self._use_linked_volume_sync:
            return self._linked_is_muted
        return self._is_muted

    @property
    def dashboard_source(self) -> Optional[str]:
        # Optional API extension: AV remains compatible with LG 2.0/API v1.
        if getattr(self._lg_display, "dashboard_available", False) is not True:
            return None
        return self._app_source_name("Dashboard")

    @property
    def pip_source(self) -> Optional[str]:
        if getattr(self._lg_display, "pip_available", False) is not True:
            return None
        return self._app_source_name("PiP")

    @property
    def media_view_source(self) -> Optional[str]:
        if getattr(self._lg_display, "media_view_available", False) is not True:
            return None
        return self._app_source_name("Mediaplayer")

    def _app_source_name(self, name):
        used = set(self._sources) | set(self._linked_source_display_map())
        while name in used:
            name += " (App)"
        return name

    @property
    def source(self) -> Optional[str]:
        if getattr(self._lg_display, "media_view_active", False) is True:
            return self.media_view_source
        if getattr(self._lg_display, "pip_active", False) is True:
            return self.pip_source
        if getattr(self._lg_display, "dashboard_active", False) is True:
            return self.dashboard_source
        return self._source

    @property
    def source_list(self) -> list[str]:
        display_sources = list(self._sources.keys())
        if self.dashboard_source:
            display_sources.append(self.dashboard_source)
        if self.pip_source:
            display_sources.append(self.pip_source)
        if self.media_view_source:
            display_sources.append(self.media_view_source)
        linked_sources = list(self._linked_source_display_map().keys())
        if not linked_sources:
            return display_sources

        combined_sources: list[str] = []
        linked_input_name = None
        if self._linked_input_id is not None:
            linked_input_name = self._source_names_by_id.get(self._linked_input_id)

        for display_source in display_sources:
            combined_sources.append(display_source)
            if linked_input_name is not None and display_source == linked_input_name:
                combined_sources.extend(linked_sources)

        if linked_input_name is None:
            combined_sources.extend(linked_sources)

        return combined_sources

    @property
    def media_title(self):
        if self._lg_display.presentation_active:
            return None
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        return (
            state.attributes.get("media_title")
            if state and state.state not in _UNAVAILABLE_STATES
            else None
        )

    @property
    def media_artist(self):
        if self._lg_display.presentation_active:
            return None
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        return (
            state.attributes.get("media_artist")
            if state and state.state not in _UNAVAILABLE_STATES
            else None
        )

    @property
    def media_album_name(self):
        if self._lg_display.presentation_active:
            return None
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        return (
            state.attributes.get("media_album_name")
            if state and state.state not in _UNAVAILABLE_STATES
            else None
        )

    @property
    def media_image_url(self):
        if self._lg_display.presentation_active:
            return None
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        return (
            state.attributes.get("entity_picture")
            if state and state.state not in _UNAVAILABLE_STATES
            else None
        )

    async def async_added_to_hass(self) -> None:
        @callback
        def display_changed(event):
            if event.data.get("entry_id") == self._config_entry.data.get("lg_entry_id"):
                self.async_schedule_update_ha_state(True)

        self.async_on_remove(
            self.hass.bus.async_listen("lg_rs232_ip_status", display_changed)
        )
        self.async_on_remove(
            self.hass.bus.async_listen(
                "homekit_tv_remote_key_pressed", self._async_homekit_key
            )
        )

        async def refresh(_now):
            self.async_schedule_update_ha_state(True)

        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                refresh,
                timedelta(
                    seconds=self._config_entry.options.get("polling_interval", 60)
                ),
            )
        )
        self.async_schedule_update_ha_state(True)
        self._startup_off_guard_until = time.monotonic() + _STARTUP_OFF_GUARD_SECONDS
        self._ha_stop_unsub = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            self._async_handle_hass_stop,
        )

        linked_entity_id = self._linked_entity_id
        if linked_entity_id:
            self._linked_state_unsub = async_track_state_change_event(
                self.hass,
                [linked_entity_id],
                self._async_handle_linked_state_change,
            )

        volume_entity_id = self._volume_entity_id
        if volume_entity_id and volume_entity_id != linked_entity_id:
            self._volume_state_unsub = async_track_state_change_event(
                self.hass,
                [volume_entity_id],
                self._async_handle_volume_state_change,
            )

        power_supply_switch_entity_id = self._power_supply_switch_entity_id
        if power_supply_switch_entity_id:
            self._sync_power_supply_hint_from_state(power_supply_switch_entity_id)
            self._power_supply_state_unsub = async_track_state_change_event(
                self.hass,
                [power_supply_switch_entity_id],
                self._async_handle_power_supply_state_change,
            )

    async def async_will_remove_from_hass(self) -> None:
        self._ha_stopping = True
        await self._async_cancel_presentations()
        await self._async_cancel_wake()
        tasks = [
            task
            for task in (
                self._power_supply_off_task,
                self._blocked_linked_turn_off_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._ha_stop_unsub is not None:
            self._ha_stop_unsub()
            self._ha_stop_unsub = None

        if self._linked_state_unsub is not None:
            self._linked_state_unsub()
            self._linked_state_unsub = None

        if self._volume_state_unsub is not None:
            self._volume_state_unsub()
            self._volume_state_unsub = None

        if self._power_supply_state_unsub is not None:
            self._power_supply_state_unsub()
            self._power_supply_state_unsub = None

        if (
            self._power_supply_off_task is not None
            and not self._power_supply_off_task.done()
        ):
            self._power_supply_off_task.cancel()
            self._power_supply_off_task = None

        if self._display_wake_task is not None and not self._display_wake_task.done():
            self._display_wake_task.cancel()
            self._display_wake_task = None

        if (
            self._blocked_linked_turn_off_task is not None
            and not self._blocked_linked_turn_off_task.done()
        ):
            self._blocked_linked_turn_off_task.cancel()
            self._blocked_linked_turn_off_task = None

    def _update_linked_cache_from_state(self) -> None:
        linked_entity_id = self._linked_entity_id
        if not linked_entity_id:
            return

        state = self.hass.states.get(linked_entity_id)
        if state is None or _is_restored_state(state):
            self._linked_state = None
            return

        if state.state in _UNAVAILABLE_STATES:
            self._linked_state = None
            self._report_issue(
                "linked_media_player_unavailable",
                "Linked media player not available or not responding",
                level="warning",
                source=linked_entity_id,
                trigger="state refresh",
                details={"state": state.state},
            )
            return

        self._clear_issue(
            "linked_media_player_unavailable",
            message="Linked media player reachable again",
        )

        self._linked_state = state.state
        self._linked_media_title = state.attributes.get("media_title")
        self._linked_media_artist = state.attributes.get("media_artist")
        self._linked_media_album_name = state.attributes.get("media_album_name")
        self._linked_media_image_url = state.attributes.get("entity_picture")

        linked_source = state.attributes.get("source") or state.attributes.get(
            "app_name"
        )
        self._linked_source = (
            linked_source if isinstance(linked_source, str) and linked_source else None
        )

        source_list = state.attributes.get("source_list")
        if isinstance(source_list, (list, tuple)):
            self._linked_source_list = [
                str(item) for item in source_list if item not in (None, "")
            ]

        if self._is_linked_input_active:
            now = time.monotonic()
            if not self._pending_source or now >= self._pending_source_until:
                resolved_source = self._resolve_source_name(self._current_input_id)
                if resolved_source is not None:
                    self._source = resolved_source

    def _update_volume_cache_from_state(self) -> None:
        self._linked_volume_level = None
        self._linked_is_muted = None
        volume_entity_id = self._volume_entity_id
        if not volume_entity_id:
            return

        state = self.hass.states.get(volume_entity_id)
        if state is None or _is_restored_state(state):
            return

        issue_code = (
            "linked_media_player_unavailable"
            if volume_entity_id == self._linked_entity_id
            else "linked_volume_media_player_unavailable"
        )
        issue_message = (
            "Linked media player not available or not responding"
            if issue_code == "linked_media_player_unavailable"
            else "Linked volume media player not available or not responding"
        )

        if state.state in _UNAVAILABLE_STATES:
            if (
                issue_code == "linked_volume_media_player_unavailable"
                and not self._display_is_online_for_linked_volume_warning()
            ):
                self._clear_issue(
                    issue_code,
                    message="Linked volume warning suppressed while display offline",
                )
                return

            self._report_issue(
                issue_code,
                issue_message,
                level="warning",
                source=volume_entity_id,
                trigger="volume state refresh",
                details={"state": state.state},
            )
            return

        self._clear_issue(issue_code, message=f"Resolved: {issue_message}")
        self._linked_volume_level = state.attributes.get("volume_level")
        self._linked_is_muted = state.attributes.get("is_volume_muted")

    def _sync_power_supply_hint_from_state(
        self, entity_id: Optional[str] = None
    ) -> None:
        """Mirror the configured smart-plug state into the LG connection guard."""
        switch_entity_id = entity_id or self._power_supply_switch_entity_id
        if not switch_entity_id:
            return

        state = self.hass.states.get(switch_entity_id)
        if state is None or _is_restored_state(state):
            return

        if state.state in _UNAVAILABLE_STATES:
            self._report_issue(
                "power_supply_unavailable",
                "Power supply switch not available or not responding",
                level="error",
                source=switch_entity_id,
                trigger="state refresh",
                details={"state": state.state},
            )
            return

        self._clear_issue(
            "power_supply_unavailable",
            message="Power supply switch reachable again",
        )

        if state.state == STATE_OFF:
            self._lg_display.set_power_supply_state(False)
        elif state.state == STATE_ON:
            self._lg_display.set_power_supply_state(True)

    @property
    def _linked_power_on_suppressed(self) -> bool:
        return time.monotonic() < self._suppress_linked_power_on_until

    def _suppress_linked_power_on(
        self, reason: str, duration: Optional[float] = None
    ) -> None:
        suppress_for = (
            self._pending_power_seconds if duration is None else max(0.0, duration)
        )
        self._suppress_linked_power_on_until = time.monotonic() + suppress_for
        self._log_power_sync(
            "linked power-on temporarily suppressed",
            reason=reason,
            suppress_for_seconds=suppress_for,
        )

    def _cancel_power_supply_off_task(self) -> None:
        if (
            self._power_supply_off_task is not None
            and not self._power_supply_off_task.done()
        ):
            self._power_supply_off_task.cancel()
        self._power_supply_off_task = None

    def _cancel_blocked_linked_turn_off_task(self) -> None:
        """Cancel a pending forced standby action for the linked media player."""
        if (
            self._blocked_linked_turn_off_task is not None
            and not self._blocked_linked_turn_off_task.done()
        ):
            self._blocked_linked_turn_off_task.cancel()
        self._blocked_linked_turn_off_task = None

    def _schedule_blocked_linked_turn_off(self, reason: str) -> None:
        """Send the linked media player back to standby after a blocked wake attempt."""
        self._cancel_blocked_linked_turn_off_task()
        self._blocked_linked_turn_off_task = self.hass.async_create_task(
            self._async_turn_off_linked_after_delay(reason)
        )

    async def _async_turn_off_linked_after_delay(self, reason: str) -> None:
        """Turn the linked media player back off after a blocked automation wake."""
        try:
            await asyncio.sleep(_AUTOMATION_BLOCKED_TURN_OFF_DELAY_SECONDS)
            if self._ha_stopping or self._sync_automation_enabled:
                return

            linked_entity_id = self._linked_entity_id
            if not linked_entity_id:
                return

            state = self.hass.states.get(linked_entity_id)
            if state is None or _is_restored_state(state):
                return

            if state.state not in _LINKED_ACTIVE_STATES:
                return

            if await self._async_call_linked_service("turn_off"):
                self._log_power_sync(
                    "linked entity sent back to standby after blocked wake attempt",
                    linked_entity_id=linked_entity_id,
                    reason=reason,
                    delay_seconds=_AUTOMATION_BLOCKED_TURN_OFF_DELAY_SECONDS,
                )
        except asyncio.CancelledError:
            return
        finally:
            if self._blocked_linked_turn_off_task is asyncio.current_task():
                self._blocked_linked_turn_off_task = None

    def _start_display_wake_task(self, reason: str) -> None:
        self._cancel_power_supply_off_task()
        if self._display_wake_task is not None and not self._display_wake_task.done():
            return
        self._display_wake_task = self.hass.async_create_task(
            self._async_ensure_display_on_after_power_restore(reason)
        )

    def _schedule_power_supply_off(self, reason: str) -> None:
        if self._power_supply_switch_entity_id is None:
            return
        if (
            self._power_supply_off_task is not None
            and not self._power_supply_off_task.done()
        ):
            return
        self._power_supply_off_task = self.hass.async_create_task(
            self._async_delayed_power_supply_off(reason)
        )

    async def _async_delayed_power_supply_off(self, reason: str) -> None:
        try:
            delay_seconds = self._power_supply_off_delay_seconds
            await asyncio.sleep(delay_seconds)
            if self._ha_stopping or self._any_presentation_active:
                return

            async with self._lg_display.supply_guard() as allowed:
                if (
                    allowed
                    and not self._ha_stopping
                    and not self._any_presentation_active
                ):
                    await self._async_call_power_supply_service("turn_off")
        except asyncio.CancelledError:
            return
        finally:
            if self._power_supply_off_task is asyncio.current_task():
                self._power_supply_off_task = None

    async def _async_ensure_display_on_after_power_restore(self, reason: str) -> None:
        try:
            if self._power_supply_switch_entity_id is not None:
                if await self._async_call_power_supply_service("turn_on"):
                    self._log_power_sync(
                        "power supply turned on for display wake",
                        reason=reason,
                        switch_entity_id=self._power_supply_switch_entity_id,
                    )
                else:
                    self._report_issue(
                        "power_supply_unavailable",
                        "Power supply did not become available",
                    )
                    return

            await asyncio.sleep(
                self._config_entry.options.get("power_supply_startup_delay", 0)
            )
            deadline = time.monotonic() + self._config_entry.options.get(
                "display_wake_timeout", 60
            )
            requested_on = False
            while time.monotonic() < deadline and not self._ha_stopping:
                power_status = await self._lg_display.async_get_power_status(
                    use_cache=False
                )
                if power_status is True:
                    self._clear_issue(
                        "display_unresponsive", message="Display reachable again"
                    )
                    self._state = MediaPlayerState.ON
                    self.async_write_ha_state()
                    return
                if power_status is False and not requested_on:
                    if not await self._lg_display.async_power_on():
                        self._report_issue(
                            "display_unresponsive",
                            "Display rejected power-on",
                            level="error",
                            trigger=reason,
                        )
                        return
                    requested_on = True
                await asyncio.sleep(1)

            self._report_issue(
                "display_unresponsive",
                "Display did not switch on or respond",
                level="error",
                source=self.entity_id,
                trigger=reason,
                details={
                    "timeout_seconds": self._config_entry.options.get(
                        "display_wake_timeout", 60
                    )
                },
            )
            self._log_power_sync(
                "display wake timed out waiting for reachable power status",
                reason=reason,
                timeout_seconds=_DISPLAY_WAKE_TIMEOUT_SECONDS,
            )
        finally:
            if self._display_wake_task is asyncio.current_task():
                self._display_wake_task = None

    def _log_power_sync(self, message: str, **context: Any) -> None:
        """Emit structured debug logs for power sync decisions."""
        details = ", ".join(f"{key}={value}" for key, value in context.items())
        if details:
            _LOGGER.debug("Power-sync decision: %s | %s", message, details)
        else:
            _LOGGER.debug("Power-sync decision: %s", message)

    def _report_issue(
        self,
        code: str,
        message: str,
        *,
        level: str = "warning",
        source: Optional[str] = None,
        trigger: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Publish an issue for the alert sensor."""
        alert_state = self._alert_state
        if alert_state is None:
            return

        alert_state.set_issue(
            code,
            message,
            level=level,
            source=source,
            trigger=trigger,
            details=details,
        )

    def _clear_issue(self, code: str, *, message: Optional[str] = None) -> None:
        """Clear a resolved issue from the alert sensor."""
        alert_state = self._alert_state
        if alert_state is None:
            return

        alert_state.clear_issue(code, message=message)

    def _is_in_expected_display_transition(self, now: Optional[float] = None) -> bool:
        """Return True while a temporary display disconnect is expected."""
        if now is None:
            now = time.monotonic()

        if self._lg_display.is_intentionally_unpowered:
            return True

        if self._pending_state is not None and now < self._pending_state_until:
            return True

        if self._display_wake_task is not None and not self._display_wake_task.done():
            return True

        return False

    def _display_is_online_for_linked_volume_warning(self) -> bool:
        """Return True only when linked-volume availability warnings are relevant."""
        if self._is_in_expected_display_transition():
            return False

        if self._last_display_power is True:
            return True

        return self._state == MediaPlayerState.ON and self._lg_display.is_available

    async def _async_call_linked_service(self, service: str, **kwargs: Any) -> bool:
        linked_entity_id = self._linked_entity_id
        if service == "turn_off":
            self._log_power_sync(
                "calling linked turn_off service",
                linked_entity_id=linked_entity_id,
                kwargs=kwargs,
            )
        return await self._async_call_entity_service(
            linked_entity_id, service, **kwargs
        )

    async def _async_call_volume_service(self, service: str, **kwargs: Any) -> bool:
        volume_entity_id = self._volume_entity_id
        return await self._async_call_entity_service(
            volume_entity_id, service, **kwargs
        )

    async def _async_call_power_supply_service(self, service: str) -> bool:
        switch_entity_id = self._power_supply_switch_entity_id
        result = await self._async_call_switch_service(switch_entity_id, service)
        if result and service in {"turn_on", "turn_off"}:
            self._lg_display.set_power_supply_state(service == "turn_on")
        return result

    async def _async_call_switch_service(
        self, entity_id: Optional[str], service: str
    ) -> bool:
        if not entity_id:
            return False

        service_data = {"entity_id": entity_id}
        try:
            await self.hass.services.async_call(
                "switch",
                service,
                service_data,
                blocking=True,
            )
            expected = "on" if service == "turn_on" else "off"
            state = self.hass.states.get(entity_id)
            for _ in range(20):
                if state is not None and state.state == expected:
                    break
                await asyncio.sleep(0.25)
                state = self.hass.states.get(entity_id)
            if state is None or state.state != expected:
                self._report_issue(
                    "power_supply_unavailable",
                    "Power supply switch not available or not responding",
                    level="error",
                    source=entity_id,
                    trigger=f"switch.{service}",
                    details={"state": None if state is None else state.state},
                )
                return False

            self._clear_issue(
                "power_supply_unavailable",
                message="Power supply switch reachable again",
            )
            return True
        except Exception as err:
            self._report_issue(
                "power_supply_unavailable",
                "Power supply switch not available or not responding",
                level="error",
                source=entity_id,
                trigger=f"switch.{service}",
                details={"error": str(err)},
            )
            _LOGGER.debug(
                "Switch service %s failed for %s: %s",
                service,
                entity_id,
                err,
            )
            return False

    async def _async_call_entity_service(
        self, entity_id: Optional[str], service: str, **kwargs: Any
    ) -> bool:
        linked_entity_id = entity_id
        if not linked_entity_id:
            return False

        if self.entity_id and linked_entity_id == self.entity_id:
            return False

        service_data: dict[str, Any] = {"entity_id": linked_entity_id}
        service_data.update(kwargs)

        issue_code = (
            "linked_media_player_unavailable"
            if linked_entity_id == self._linked_entity_id
            else "linked_volume_media_player_unavailable"
        )
        issue_message = (
            "Linked media player not available or not responding"
            if issue_code == "linked_media_player_unavailable"
            else "Linked volume media player not available or not responding"
        )

        try:
            await self.hass.services.async_call(
                "media_player",
                service,
                service_data,
                blocking=True,
            )
            state = self.hass.states.get(linked_entity_id)
            if state is None or state.state in _UNAVAILABLE_STATES:
                if (
                    issue_code == "linked_volume_media_player_unavailable"
                    and not self._display_is_online_for_linked_volume_warning()
                ):
                    self._clear_issue(
                        issue_code,
                        message="Linked volume warning suppressed while display offline",
                    )
                    return False

                self._report_issue(
                    issue_code,
                    issue_message,
                    level="warning",
                    source=linked_entity_id,
                    trigger=f"media_player.{service}",
                    details={"state": None if state is None else state.state},
                )
                return False

            self._clear_issue(issue_code, message=f"Resolved: {issue_message}")
            return True
        except Exception as err:
            if not (
                issue_code == "linked_volume_media_player_unavailable"
                and not self._display_is_online_for_linked_volume_warning()
            ):
                self._report_issue(
                    issue_code,
                    issue_message,
                    level="warning",
                    source=linked_entity_id,
                    trigger=f"media_player.{service}",
                    details={"error": str(err)},
                )
            _LOGGER.debug(
                "Linked media player service %s failed for %s: %s",
                service,
                linked_entity_id,
                err,
            )
            return False

    async def _async_handle_volume_state_change(self, event) -> None:
        try:
            new_state = event.data.get("new_state")
            if new_state is None:
                return

            self._update_volume_cache_from_state()
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.debug("Error handling linked volume state change: %s", err)

    async def _async_handle_power_supply_state_change(self, event) -> None:
        try:
            new_state = event.data.get("new_state")
            if new_state is None or _is_restored_state(new_state):
                return

            if new_state.state in _UNAVAILABLE_STATES:
                self._report_issue(
                    "power_supply_unavailable",
                    "Power supply switch not available or not responding",
                    level="error",
                    source=self._power_supply_switch_entity_id,
                    trigger="state change",
                    details={"state": new_state.state},
                )
                self.async_write_ha_state()
                return

            self._clear_issue(
                "power_supply_unavailable",
                message="Power supply switch reachable again",
            )

            if new_state.state == STATE_OFF:
                await self._async_cancel_wake()
                self._lg_display.set_power_supply_state(False)
                self._suppress_linked_power_on("power supply switch turned off")
                self._state = MediaPlayerState.OFF
            elif new_state.state == STATE_ON:
                self._lg_display.set_power_supply_state(True)
                self._suppress_linked_power_on_until = 0.0

            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.debug("Error handling power supply state change: %s", err)

    async def _async_handle_hass_stop(self, event) -> None:
        """Mark integration as stopping to suppress sync side-effects."""
        self._ha_stopping = True
        await self._async_cancel_presentations()
        await self._async_cancel_wake()
        self._log_power_sync("home assistant stopping: suppress automatic power sync")

    async def _async_handle_linked_state_change(self, event) -> None:
        if self._ha_stopping or self._any_presentation_active:
            self._log_power_sync("skip linked state change: home assistant stopping")
            return

        new_state = event.data.get("new_state")
        if new_state is None:
            self._report_issue(
                "linked_media_player_unavailable",
                "Linked media player not available or not responding",
                level="warning",
                source=self._linked_entity_id,
                trigger="state event missing",
            )
            self._log_power_sync("linked state event ignored: new_state is None")
            return
        old_state_obj = event.data.get("old_state")
        old_state = old_state_obj.state if old_state_obj is not None else None
        old_state_restored = _is_restored_state(old_state_obj)
        new_state_restored = _is_restored_state(new_state)

        now = time.monotonic()
        if old_state != new_state.state or new_state_restored:
            self._standby_guard.reset()
        self._update_linked_cache_from_state()

        if not self._sync_automation_enabled:
            if new_state.state in _LINKED_ACTIVE_STATES:
                self._report_issue(
                    "automation_blocked_turn_on",
                    "Blocked display turn-on while sync automation lock is enabled",
                    level="warning",
                    source=self._linked_entity_id,
                    trigger=f"{old_state}->{new_state.state}",
                    details={
                        "old_state": old_state,
                        "new_state": new_state.state,
                        "action": "linked_turn_off_scheduled",
                        "delay_seconds": _AUTOMATION_BLOCKED_TURN_OFF_DELAY_SECONDS,
                    },
                )
                self._schedule_blocked_linked_turn_off(
                    f"automation disabled: {old_state}->{new_state.state}"
                )
            else:
                self._cancel_blocked_linked_turn_off_task()
            self._log_power_sync(
                "skip linked power sync: automation lock enabled",
                old_state=old_state,
                new_state=new_state.state,
            )
            self.async_write_ha_state()
            return

        if new_state.state in _LINKED_INACTIVE_STATES:
            if now < self._startup_off_guard_until:
                self._log_power_sync(
                    "skip linked off: within startup guard",
                    old_state=old_state,
                    new_state=new_state.state,
                    old_state_restored=old_state_restored,
                    new_state_restored=new_state_restored,
                    guard_until=self._startup_off_guard_until,
                    now=now,
                )
                self.async_write_ha_state()
                return

            if old_state_restored or new_state_restored:
                self._log_power_sync(
                    "skip linked off: restored startup state",
                    old_state=old_state,
                    new_state=new_state.state,
                    old_state_restored=old_state_restored,
                    new_state_restored=new_state_restored,
                )
                self.async_write_ha_state()
                return

            # Avoid shutdown on Home Assistant startup baseline (old_state is None)
            # and ignore repeated inactive->inactive updates.
            # Also ignore transitions from unavailable/unknown, which commonly occur
            # while integrations are restoring after startup.
            if (
                old_state is None
                or old_state in _LINKED_INACTIVE_STATES
                or old_state in {"unavailable", "unknown"}
            ):
                self._log_power_sync(
                    "skip linked off: startup/baseline transition",
                    old_state=old_state,
                    new_state=new_state.state,
                    old_state_restored=old_state_restored,
                    new_state_restored=new_state_restored,
                )
                self.async_write_ha_state()
                return

            # Debounce off events during startup churn: confirm state after short delay.
            linked_entity_id = self._linked_entity_id
            if linked_entity_id:
                await asyncio.sleep(_OFF_CONFIRM_DELAY_SECONDS)
                confirmed_state_obj = self.hass.states.get(linked_entity_id)
                confirmed_state = (
                    confirmed_state_obj.state
                    if confirmed_state_obj is not None
                    else None
                )
                if confirmed_state not in _LINKED_INACTIVE_STATES:
                    self._log_power_sync(
                        "skip linked off: off not confirmed after delay",
                        old_state=old_state,
                        initial_new_state=new_state.state,
                        confirmed_state=confirmed_state,
                        delay_seconds=_OFF_CONFIRM_DELAY_SECONDS,
                    )
                    self.async_write_ha_state()
                    return

            if (
                self._ha_stopping
                or self._any_presentation_active
                or not self._sync_automation_enabled
            ):
                return
            if await self._lg_display.async_get_input() != self._linked_input_id:
                return
            display_power = await self._lg_display.async_get_power_status()
            self._log_power_sync(
                "linked off requested",
                old_state=old_state,
                new_state=new_state.state,
                old_state_restored=old_state_restored,
                new_state_restored=new_state_restored,
                display_power=display_power,
            )
            if display_power:
                await self._async_cancel_wake()
                if await self._lg_display.async_power_off():
                    self._schedule_power_supply_off("linked standby confirmed")
                    self._standby_latched = True
                    self._log_power_sync("display powered off from linked off event")
                    self._state = MediaPlayerState.OFF
                else:
                    self._log_power_sync(
                        "display power_off command failed on linked off event"
                    )
        elif new_state.state in _LINKED_ACTIVE_STATES:
            # Attribute-only idle updates and restored states are not wake intent.
            if (
                new_state_restored
                or old_state_restored
                or old_state is None
                or old_state in _UNAVAILABLE_STATES
                or old_state == new_state.state
                or (
                    new_state.state == STATE_IDLE
                    and (
                        self._standby_latched
                        or old_state not in _LINKED_INACTIVE_STATES
                    )
                )
            ):
                self.async_write_ha_state()
                return
            self._standby_latched = False
            display_power = await self._lg_display.async_get_power_status()
            self._log_power_sync(
                "linked active observed",
                old_state=old_state,
                new_state=new_state.state,
                display_power=display_power,
            )
            if self._linked_power_on_suppressed:
                self._log_power_sync(
                    "skip linked active wake: off transition still in progress",
                    old_state=old_state,
                    new_state=new_state.state,
                )
            elif display_power is not True:
                self._state = MediaPlayerState.ON
                self._pending_state = MediaPlayerState.ON
                self._pending_state_until = (
                    time.monotonic() + self._pending_power_seconds
                )
                self._start_display_wake_task("linked active event")

        self.async_write_ha_state()

    async def _async_cancel_wake(self):
        task = self._display_wake_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._display_wake_task = None

    async def async_turn_on(self) -> None:
        await self._async_cancel_presentations()
        async with self._control_lock:
            await self._async_turn_on_locked()

    async def _async_turn_on_locked(self) -> None:
        self._standby_latched = False
        self._standby_guard.reset()
        self._cancel_power_supply_off_task()
        self._suppress_linked_power_on_until = 0.0
        self._state = MediaPlayerState.ON
        self._pending_state = MediaPlayerState.ON
        self._pending_state_until = time.monotonic() + self._pending_power_seconds
        self._start_display_wake_task("local media_player turn_on")
        await self._async_remote_power(True)
        if self._config_entry.options.get("sonos_select_tv_source", False):
            await self._required_call(
                "media_player",
                "select_source",
                self._volume_entity_id,
                source=self._config_entry.options.get("sonos_tv_source", "TV"),
            )
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        await self._async_cancel_presentations()
        await self._lg_display.async_clear_content()
        async with self._control_lock:
            self._suppress_linked_power_on("explicit off")
            await self._async_cancel_wake()
            await self._async_turn_off_locked()

    async def _async_turn_off_locked(self) -> None:
        self._standby_latched = True
        self._standby_guard.reset()
        self._log_power_sync("local media_player turn_off requested")
        self._suppress_linked_power_on("local media_player turn_off")
        if (
            await self._lg_display.async_get_power_status(use_cache=False) is False
            or await self._lg_display.async_power_off()
        ):
            self._log_power_sync("display powered off from local media_player turn_off")
            self._state = MediaPlayerState.OFF
            self._pending_state = MediaPlayerState.OFF
            self._pending_state_until = time.monotonic() + self._pending_power_seconds
            await self._async_remote_power(False)
            self._schedule_power_supply_off("explicit confirmed off")
            self.async_write_ha_state()
        else:
            self._report_issue(
                "display_unresponsive",
                "Display did not switch off or respond",
                level="error",
                source=self.entity_id,
                trigger="local media_player turn_off",
            )
            self._log_power_sync(
                "display power_off command failed on local media_player turn_off"
            )

    async def async_set_volume_level(self, volume: float) -> None:
        if self._use_linked_volume_sync and await self._async_call_volume_service(
            "volume_set", volume_level=volume
        ):
            self._linked_volume_level = volume
            self.async_write_ha_state()
        if self._use_linked_volume_sync:
            # Never fall back to display volume while linked volume sync is enabled.
            return

        # Home Assistant uses 0.0 - 1.0; RS232 uses 0 - 100
        volume_value = max(0, min(100, int(round(volume * 100))))
        if await self._lg_display.async_set_volume(volume_value):
            self._volume_level = volume_value / 100
            self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        if self._use_linked_volume_sync and await self._async_call_volume_service(
            "volume_up"
        ):
            self._update_volume_cache_from_state()
            self.async_write_ha_state()
        if self._use_linked_volume_sync:
            return

        if await self._lg_display.async_volume_up_step():
            if self._volume_level is not None:
                self._volume_level = min(1.0, self._volume_level + 0.01)
            self.async_write_ha_state()

    async def async_volume_down(self) -> None:
        if self._use_linked_volume_sync and await self._async_call_volume_service(
            "volume_down"
        ):
            self._update_volume_cache_from_state()
            self.async_write_ha_state()
        if self._use_linked_volume_sync:
            return

        if await self._lg_display.async_volume_down_step():
            if self._volume_level is not None:
                self._volume_level = max(0.0, self._volume_level - 0.01)
            self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        if self._use_linked_volume_sync and await self._async_call_volume_service(
            "volume_mute", is_volume_muted=mute
        ):
            self._linked_is_muted = mute
            self.async_write_ha_state()
        if self._use_linked_volume_sync:
            return

        value = 0x00 if mute else 0x01
        result = await self._lg_display.async_set_mute_raw(value)
        if result is not None:
            self._is_muted = mute
            self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        await self._async_cancel_presentations()
        await self._lg_display.async_clear_content()
        async with self._control_lock:
            await self._async_select_source_locked(source)

    async def _async_select_source_locked(self, source: str) -> None:
        if (
            source not in self._sources
            and source not in self._linked_source_display_map()
            and source != self.dashboard_source
            and source != self.pip_source
            and source != self.media_view_source
        ):
            raise HomeAssistantError("Unknown source")
        await self._async_cancel_wake()
        await self._async_ensure_display_on_after_power_restore("source selection")
        if await self._lg_display.async_get_power_status(use_cache=False) is not True:
            raise HomeAssistantError("Display did not become ready")
        self._standby_guard.reset()
        if source in (self.dashboard_source, self.pip_source, self.media_view_source):
            if source == self.media_view_source:
                await self._lg_display.async_select_media_view()
            elif source == self.pip_source:
                await self._lg_display.async_select_pip()
            else:
                await self._lg_display.async_select_dashboard()
            self._current_input_id = None
            self._source = source
            self._pending_source = None
            self._pending_source_until = 0.0
            self.async_write_ha_state()
            return
        source_id = self._sources.get(source)
        if source_id is not None:
            if await self._lg_display.async_set_input(source_id):
                self._current_input_id = source_id
                self._source = source
                self._pending_source = source
                self._pending_source_until = (
                    time.monotonic() + self._pending_source_seconds
                )
                self.async_write_ha_state()
            return

        linked_source = self._linked_source_display_map().get(source)
        linked_input_id = self._linked_input_id
        if linked_source is None or linked_input_id is None:
            _LOGGER.warning("Unsupported source requested: %s", source)
            return

        switched_to_linked_input = (
            self._current_input_id == linked_input_id
            and getattr(self._lg_display, "dashboard_active", False) is not True
            and getattr(self._lg_display, "pip_active", False) is not True
            and getattr(self._lg_display, "media_view_active", False) is not True
        )
        if not switched_to_linked_input:
            switched_to_linked_input = await self._lg_display.async_set_input(
                linked_input_id
            )

        if not switched_to_linked_input:
            _LOGGER.warning(
                "Failed to switch display to linked HDMI input for source: %s",
                source,
            )
            return

        self._current_input_id = linked_input_id
        self._source = source
        self._pending_source = source
        self._pending_source_until = time.monotonic() + self._pending_source_seconds
        await self._async_call_linked_service("select_source", source=linked_source)
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        await self._async_playback_action(
            "media_next_track", MediaPlayerEntityFeature.NEXT_TRACK
        )

    async def async_media_previous_track(self) -> None:
        await self._async_playback_action(
            "media_previous_track", MediaPlayerEntityFeature.PREVIOUS_TRACK
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "presentation_active": self._any_presentation_active,
            "presentation_queue_size": len(self._presentation_queue),
            "presentation_error": self._presentation_error,
            "notification_backend_configured": bool(
                self._option_entity("notification_script_entity_id")
            ),
            "osd_restore_error": self._lg_display.osd_restore_error,
            "signal_present": self._signal_present,
            "standby_candidate": self._standby_guard.reason,
            "standby_samples": self._standby_guard.samples,
            "last_standby_reason": self._last_standby_reason,
            "automatic_wake_blocked": self._standby_latched,
        }

    async def _async_check_standby(self) -> None:
        options = self._config_entry.options
        now = time.monotonic()
        eligible = (
            bool(self._linked_entity_id)
            and not self._any_presentation_active
            and self._is_linked_input_active
            and self._sync_automation_enabled
            and not self._ha_stopping
            and now >= self._startup_off_guard_until
            and now >= self._pending_state_until
            and now >= self._pending_source_until
            and not self._is_in_expected_display_transition(now)
        )
        if not eligible:
            self._standby_guard.reset()
            return
        self._signal_present = (
            await self._lg_display.async_get_signal_status()
            if options.get("standby_signal_check", True)
            else None
        )
        self._update_linked_cache_from_state()
        reason = self._standby_guard.observe(
            time.monotonic(),
            self._linked_state,
            self._signal_present,
            low_power=self._power_sensor_in_standby(),
            eligible=eligible,
            no_signal_seconds=options.get("standby_no_signal_seconds", 120),
            idle_seconds=options.get("standby_idle_seconds", 900),
        )
        if reason is None:
            return
        # Re-read the physical input and power before committing a shutdown.
        power = await self._lg_display.async_get_power_status(use_cache=False)
        input_id = await self._lg_display.async_get_input(use_cache=False)
        if (
            power is not True
            or input_id != self._linked_input_id
            or self._ha_stopping
            or not self._sync_automation_enabled
            or self._any_presentation_active
            or time.monotonic()
            < max(self._pending_state_until, self._pending_source_until)
        ):
            self._standby_guard.reset()
            return
        signal = (
            await self._lg_display.async_get_signal_status()
            if options.get("standby_signal_check", True)
            else None
        )
        self._update_linked_cache_from_state()
        confirmed = self._standby_guard.observe(
            time.monotonic(),
            self._linked_state,
            signal,
            low_power=self._power_sensor_in_standby(),
            eligible=not self._ha_stopping
            and not self._any_presentation_active
            and self._sync_automation_enabled,
            no_signal_seconds=options.get("standby_no_signal_seconds", 120),
            idle_seconds=options.get("standby_idle_seconds", 900),
        )
        if confirmed != reason:
            return
        self._last_standby_reason = reason
        _LOGGER.info("Standby confirmed for %s: %s", self.entity_id, reason)
        # Automatic shutdown must never cancel a native presentation that started
        # while the last status queries were in flight. The LG API also checks
        # this condition under its command lock.
        async with self._control_lock:
            if self._any_presentation_active or not self._lg_display.ready:
                self._standby_guard.reset()
                return
            await self._async_cancel_wake()
            await self._async_turn_off_locked()

    async def async_media_play(self) -> None:
        await self._async_playback_action("media_play", MediaPlayerEntityFeature.PLAY)

    async def async_media_pause(self) -> None:
        await self._async_playback_action("media_pause", MediaPlayerEntityFeature.PAUSE)

    async def async_media_stop(self) -> None:
        await self._async_playback_action("media_stop", MediaPlayerEntityFeature.STOP)

    async def async_update(self) -> None:
        if self._ha_stopping or self._any_presentation_active:
            return

        self._update_linked_cache_from_state()
        self._update_volume_cache_from_state()
        now = time.monotonic()

        power = await self._lg_display.async_get_power_status()
        if power is None:
            self._standby_guard.reset()
            if self._is_in_expected_display_transition(now):
                self._display_unresponsive_since = None
                self._log_power_sync(
                    "polling skipped: display power status is None during expected transition"
                )
                return

            if self._display_unresponsive_since is None:
                self._display_unresponsive_since = now
                self._log_power_sync(
                    "display power status unavailable: waiting before raising alert",
                    delay_seconds=_DISPLAY_UNRESPONSIVE_ALERT_DELAY_SECONDS,
                )
                return

            if (
                now - self._display_unresponsive_since
            ) >= _DISPLAY_UNRESPONSIVE_ALERT_DELAY_SECONDS:
                self._report_issue(
                    "display_unresponsive",
                    "Display not responding or not reachable",
                    level="error",
                    source=self.entity_id,
                    trigger="status poll",
                    details={
                        "delay_seconds": _DISPLAY_UNRESPONSIVE_ALERT_DELAY_SECONDS,
                        "unresponsive_since": self._display_unresponsive_since,
                    },
                )
            else:
                self._log_power_sync(
                    "display power status still unavailable but within alert grace period",
                    elapsed_seconds=round(now - self._display_unresponsive_since, 1),
                    delay_seconds=_DISPLAY_UNRESPONSIVE_ALERT_DELAY_SECONDS,
                )
            return

        self._display_unresponsive_since = None
        self._clear_issue("display_unresponsive", message="Display reachable again")
        if self._sync_automation_enabled:
            self._cancel_blocked_linked_turn_off_task()
            self._clear_issue(
                "automation_blocked_turn_on",
                message="Automation lock no longer blocking display turn-on",
            )

        # Wake only on explicit commands or genuine state transitions. Polling a
        # stale Apple TV state must never undo display/hardware standby.

        polled_state = MediaPlayerState.ON if power else MediaPlayerState.OFF
        if self._pending_state and now < self._pending_state_until:
            if polled_state == self._pending_state:
                self._state = polled_state
                self._pending_state = None
                self._pending_state_until = 0.0
            else:
                # Keep requested state briefly to avoid UI bounce after command.
                self._state = self._pending_state
        else:
            self._state = polled_state
            self._pending_state = None
            self._pending_state_until = 0.0

        if power is True:
            self._cancel_power_supply_off_task()
            self._suppress_linked_power_on_until = 0.0
            self._display_off_confirm_count = 0
            self._display_off_forwarded = False
        elif power is False:
            if self._last_display_power is True:
                self._display_off_confirm_count = 1
                self._display_off_forwarded = False
                self._log_power_sync(
                    "display off detected: waiting for second confirmation",
                    confirm_count=self._display_off_confirm_count,
                )
            elif (
                self._display_off_confirm_count > 0 and not self._display_off_forwarded
            ):
                self._display_off_confirm_count += 1

            if self._display_off_confirm_count >= 2 and not self._display_off_forwarded:
                self._standby_latched = True
                self._suppress_linked_power_on("display off confirmed")
                self._log_power_sync(
                    "display off confirmed: forwarding linked turn_off",
                    confirm_count=self._display_off_confirm_count,
                    last_display_power=self._last_display_power,
                    power=power,
                )
                if self._sync_automation_enabled:
                    await self._async_call_linked_service("turn_off")
                else:
                    self._log_power_sync(
                        "skip linked turn_off forwarding: automation lock enabled"
                    )
                self._schedule_power_supply_off("display off confirmed")
                self._display_off_forwarded = True

        self._last_display_power = power

        if not power:
            self._standby_guard.reset()
            return

        if not self._use_linked_volume_sync:
            volume = await self._lg_display.async_get_volume()
            if volume is not None:
                self._volume_level = max(0.0, min(1.0, volume / 100))

            mute = await self._lg_display.async_get_mute_raw()
            if mute is not None:
                self._is_muted = mute == 0x00

        input_id = await self._lg_display.async_get_input()
        if input_id is None:
            self._standby_guard.reset()
            return

        self._current_input_id = input_id
        await self._async_check_standby()
        if self._state == MediaPlayerState.OFF:
            return
        resolved_source = self._resolve_source_name(input_id)
        if resolved_source is None:
            return

        if self._pending_source and now < self._pending_source_until:
            if resolved_source == self._pending_source:
                self._source = resolved_source
                self._pending_source = None
                self._pending_source_until = 0.0
            else:
                # Keep requested source briefly to avoid UI bounce after command.
                self._source = self._pending_source
            return

        self._pending_source = None
        self._pending_source_until = 0.0
        self._source = resolved_source
