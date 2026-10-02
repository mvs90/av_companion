from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature as F,
    MediaPlayerState as S,
)


async def async_setup_entry(hass, entry, add):
    add([Player("source"), Player("sound")])


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

    async def async_turn_on(self):
        self._attr_state = S.IDLE
        self.async_write_ha_state()

    async def async_turn_off(self):
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
