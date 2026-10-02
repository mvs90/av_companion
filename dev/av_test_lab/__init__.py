from homeassistant.const import Platform


async def async_setup_entry(hass, entry):
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.MEDIA_PLAYER, Platform.SWITCH]
    )
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(
        entry, [Platform.MEDIA_PLAYER, Platform.SWITCH]
    )
