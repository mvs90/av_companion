"""Optional AV orchestration; all LG I/O belongs to LG Professional Display."""

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from custom_components.lg_rs232_ip.api import get_display_api
from .const import DOMAIN
from .alerts import LGDisplayAlertState

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SWITCH, Platform.SENSOR]


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    api = get_display_api(hass, entry.data["lg_entry_id"], version=1)
    if not api.ready:
        raise ConfigEntryNotReady("Configure/load the selected LG display first")
    data = hass.data.setdefault(DOMAIN, {})
    if any(
        key != entry.entry_id and value["lg_entry_id"] == entry.data["lg_entry_id"]
        for key, value in data.items()
    ):
        raise HomeAssistantError("Only one AV system may control each display")
    entry.async_on_unload(entry.add_update_listener(_reload))
    data[entry.entry_id] = {
        "name": entry.title,
        "lg_display": api,
        "lg_entry_id": entry.data["lg_entry_id"],
        "sync_automation_enabled": True,
        "alert_state": LGDisplayAlertState(entry.entry_id),
    }

    @callback
    def entity_renamed(event):
        old = event.data.get("old_entity_id")
        new = event.data.get("entity_id")
        if not old or not new:
            return
        options = dict(entry.options)
        changed = False
        for key, value in options.items():
            if key.endswith("_entity_id") and value == old:
                options[key] = new
                changed = True
        if changed:
            hass.config_entries.async_update_entry(entry, options=options)

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, entity_renamed)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data["lg_display"].set_power_supply_state(None)
        return True
    return False
