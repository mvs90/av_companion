"""Repair a native Apple TV session without issuing device control commands."""

import asyncio
import time
from datetime import datetime, timezone

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store


class LinkedConnectionHealth:
    def _init_linked_connection(self):
        self._linked_connection_refreshing = False
        self._linked_connection_attempt = None
        self._linked_connection_health = {}

    def _apple_tv_entry(self):
        if self.hass.config_entries is None or not self._linked_entity_id:
            return None
        entity = er.async_get(self.hass).async_get(self._linked_entity_id)
        if entity is None or entity.platform != "apple_tv":
            return None
        entry = self.hass.config_entries.async_get_entry(entity.config_entry_id)
        return entry if entry is not None and entry.domain == "apple_tv" else None

    async def async_refresh_linked_connection(self, repair_missing_raop=False):
        """Explicit maintenance; retain entity IDs, pairing and physical power."""
        if self._state != "off" or self._control_lock.locked():
            raise HomeAssistantError(
                "Connection maintenance requires the AV display off"
            )
        entry = self._apple_tv_entry()
        if entry is None:
            raise HomeAssistantError("Configure a native Apple TV media player first")
        await self._refresh_apple_tv(entry, repair_missing_raop)

    async def _async_check_linked_connection(self):
        if (
            not self._config_entry.options.get("linked_connection_watchdog", False)
            or self._ha_stopping
            or not self._sync_automation_enabled
            or self._state != "off"
            or self._control_lock.locked()
            or self._linked_connection_refreshing
        ):
            return
        if (
            self._linked_connection_attempt is not None
            and time.monotonic() - self._linked_connection_attempt < 1800
        ):
            return
        source = self.hass.states.get(self._linked_entity_id)
        if source is None or source.attributes.get("restored"):
            return
        if source.state not in {"off", "idle", "paused", "unknown", "unavailable"}:
            return
        reported = getattr(source, "last_reported", source.last_updated)
        age = (datetime.now(timezone.utc) - reported).total_seconds()
        if age < 1800:
            return
        entry = self._apple_tv_entry()
        if entry is not None:
            try:
                await self._refresh_apple_tv(entry, False)
            except Exception:
                # Failure is diagnosed above; do not suppress display polling.
                pass

    async def _refresh_apple_tv(self, entry, repair_missing_raop):
        if self._linked_connection_refreshing:
            return
        self._linked_connection_refreshing = True
        self._linked_connection_attempt = time.monotonic()
        self._linked_connection_health = {
            "action": "refreshing",
            "entry_id": entry.entry_id,
        }
        try:
            if repair_missing_raop:
                from pyatv.const import Protocol

                reason = entry.reason or ""
                prefix, suffix = "Protocol(s) ", " not yet found"
                missing = (
                    reason.split(prefix, 1)[1].split(suffix, 1)[0]
                    if prefix in reason and suffix in reason
                    else ""
                )
                if missing != "RAOP":
                    raise HomeAssistantError(
                        "Only an explicitly missing RAOP protocol can be repaired"
                    )
                credentials = dict(entry.data.get("credentials", {}))
                raop = next(
                    (key for key in credentials if int(key) == Protocol.RAOP.value),
                    None,
                )
                required = {Protocol.AirPlay.value, Protocol.Companion.value}
                if raop is None or not required.issubset(
                    {int(key) for key in credentials}
                ):
                    raise HomeAssistantError(
                        "Retain paired AirPlay and Companion protocols"
                    )
                store = Store(
                    self.hass, 1, "av_companion.apple_tv_recovery." + entry.entry_id
                )
                if await store.async_load() is None:
                    # Secrets remain in protected HA storage, never diagnostics/logs.
                    await store.async_save({"credentials": dict(credentials)})
                credentials.pop(raop)
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, "credentials": credentials}
                )
                self._linked_connection_health["removed_optional_protocol"] = "RAOP"
            loaded = await asyncio.wait_for(
                self.hass.config_entries.async_reload(entry.entry_id), timeout=45
            )
            self._linked_connection_health["action"] = (
                "refreshed" if loaded else "retry_pending"
            )
            if loaded:
                self._clear_issue(
                    "linked_connection_stalled", message="Apple TV connection refreshed"
                )
            else:
                self._report_issue(
                    "linked_connection_stalled",
                    "Apple TV connection has not recovered",
                    source=self._linked_entity_id,
                    trigger="connection maintenance",
                )
        except Exception as err:
            self._linked_connection_health.update(
                action="failed", error_type=type(err).__name__
            )
            self._report_issue(
                "linked_connection_stalled",
                "Apple TV connection maintenance failed",
                source=self._linked_entity_id,
                trigger="connection maintenance",
                details={"error_type": type(err).__name__},
            )
            raise
        finally:
            self._linked_connection_refreshing = False
