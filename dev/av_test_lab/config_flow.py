from homeassistant import config_entries


class Flow(config_entries.ConfigFlow, domain="av_test_lab"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id("test")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="AV Test Fixtures", data={})
