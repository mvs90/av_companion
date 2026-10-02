from homeassistant.components.switch import SwitchEntity


async def async_setup_entry(hass, entry, add):
    add([Supply("socket"), Supply("night"), Supply("speech")])


class Supply(SwitchEntity):
    _attr_should_poll = False

    def __init__(self, name):
        self._attr_unique_id = "av_test_" + name
        self._attr_name = "AV Test " + name
        self._attr_is_on = True

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()
