from typing import Any

"""AV automation lock."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import HomeAssistant
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [LGDisplaySyncAutomationSwitch(hass, entry.title, entry.entry_id)]
    )


class LGDisplaySyncAutomationSwitch(SwitchEntity, RestoreEntity):
    """Block or allow linked power automation for LG Display."""

    _attr_entity_registry_enabled_default = True

    _attr_entity_category = None

    def __init__(self, hass: HomeAssistant, name: str, entry_id: str) -> None:
        self.hass = hass
        self._name = name
        self._entry_id = entry_id
        self._is_on = False

    def _update_shared_state(self) -> None:
        if DOMAIN in self.hass.data and self._entry_id in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][self._entry_id][
                "sync_automation_enabled"
            ] = not self._is_on

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
        self._update_shared_state()

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_sync_automation"

    @property
    def name(self) -> str:
        return "Sync Automation Lock"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def available(self) -> bool:
        return True

    @property
    def icon(self) -> str:
        return "mdi:lock" if self._is_on else "mdi:lock-open-variant"

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name,
            "manufacturer": "AV Companion",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        self._update_shared_state()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        self._update_shared_state()
        self.async_write_ha_state()
