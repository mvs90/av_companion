"""AV system alerts."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN


class LGDisplayBaseSensor(SensorEntity):
    _attr_has_entity_name = True


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            LGDisplayAlertSensor(
                hass.data[DOMAIN][entry.entry_id]["alert_state"],
                entry.title,
                entry.entry_id,
            )
        ]
    )


class LGDisplayAlertSensor(LGDisplayBaseSensor):
    """Sensor that exposes the latest integration alert for notifications."""

    _attr_entity_registry_enabled_default = True

    def __init__(self, alert_state, name: str, unique_id: str) -> None:
        self._alert_state = alert_state
        self._name = name
        self._unique_id = unique_id
        self._alert_unsub = None

    @property
    def unique_id(self) -> str:
        return f"{self._unique_id}_alert_status"

    @property
    def name(self) -> str:
        return "Alert Status"

    @property
    def state(self) -> str:
        return self._alert_state.state

    @property
    def available(self) -> bool:
        return True

    @property
    def icon(self) -> str:
        level = self._alert_state.attributes.get("level", "info")
        if self._alert_state.state == "OK":
            return "mdi:check-circle"
        if level == "error":
            return "mdi:alert-circle"
        return "mdi:alert"

    @property
    def extra_state_attributes(self) -> dict:
        return self._alert_state.attributes

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._name,
            "manufacturer": "AV Companion",
        }

    async def async_added_to_hass(self) -> None:
        self._alert_unsub = self._alert_state.subscribe(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._alert_unsub is not None:
            self._alert_unsub()
            self._alert_unsub = None
