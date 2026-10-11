import base64
import voluptuous as vol
from homeassistant.helpers import entity_platform
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature as F,
    MediaPlayerState as S,
)


async def async_setup_entry(hass, entry, add):
    add([Player("source"), Player("sound")])
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_playback",
        {
            vol.Required("state"): vol.In(
                ["on", "off", "idle", "playing", "paused", "unknown", "unavailable"]
            ),
            vol.Optional("app_name", default=""): str,
            vol.Optional("app_id", default=""): str,
            vol.Optional("title", default=""): str,
            vol.Optional("cover", default=False): bool,
        },
        "async_set_playback",
    )


class Player(MediaPlayerEntity):
    _attr_should_poll = False
    _attr_supported_features = (
        F.TURN_ON
        | F.TURN_OFF
        | F.PLAY
        | F.PAUSE
        | F.STOP
        | F.SELECT_SOURCE
        | F.VOLUME_SET
        | F.VOLUME_MUTE
        | F.PLAY_MEDIA
    )
    _attr_source_list = ["TV", "Music"]

    def __init__(self, name):
        self._attr_unique_id = "av_test_" + name
        self._attr_name = "AV Test " + name
        self._attr_state = S.OFF
        self._attr_volume_level = 0.3
        self._attr_is_volume_muted = False
        self._attr_source = "TV"
        self._attr_media_title = "Fixture"
        self._attr_extra_state_attributes = {"turn_off_calls": 0}

    async def async_set_playback(self, state, app_name, app_id, title, cover):
        self._attr_available = state != "unavailable"
        self._attr_state = None if state == "unknown" else state
        self._attr_app_name = app_name or None
        self._attr_app_id = app_id or None
        self._attr_media_title = title or None
        self._attr_media_image_url = "fixture://real-cover" if cover else None
        self.async_write_ha_state()

    async def async_get_media_image(self):
        if not self._attr_media_image_url:
            return None, None
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1sAAAAASUVORK5CYII="
        ), "image/png"

    async def async_turn_on(self):
        self._attr_state = S.IDLE
        self.async_write_ha_state()

    async def async_turn_off(self):
        self._attr_extra_state_attributes["turn_off_calls"] += 1
        self._attr_state = S.OFF
        self.async_write_ha_state()

    async def async_media_play(self):
        self._attr_state = S.PLAYING
        self.async_write_ha_state()

    async def async_media_pause(self):
        self._attr_state = S.PAUSED
        self.async_write_ha_state()

    async def async_media_stop(self):
        self._attr_state = S.IDLE
        self.async_write_ha_state()

    async def async_select_source(self, source):
        self._attr_source = source
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume):
        self._attr_volume_level = volume
        self.async_write_ha_state()

    async def async_mute_volume(self, mute):
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()

    async def async_play_media(self, *args, **kwargs):
        await self.async_media_play()
