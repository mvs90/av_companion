"""Audible-player routing, independent display views and explicit TV selection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from homeassistant.core import State
from homeassistant.components.media_player import MediaPlayerEntityFeature as F
from custom_components.av_companion.alerts import LGDisplayAlertState


@pytest.fixture
def audio(player):
    player._config_entry.options["linked_volume_media_player_entity_id"] = (
        "media_player.sonos"
    )
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv",
        "playing",
        {
            "friendly_name": "Wohnzimmer Apple TV",
            "media_title": "Film",
            "entity_picture": "/api/media_player_proxy/apple",
            "supported_features": int(F.PLAY | F.PAUSE),
        },
    )
    player._test_states["media_player.sonos"] = State(
        "media_player.sonos",
        "playing",
        {
            "source": "Music",
            "media_title": "Song",
            "media_artist": "Artist",
            "entity_picture": "/api/media_player_proxy/sonos",
            "media_position": 12,
            "supported_features": int(F.PLAY | F.PAUSE | F.NEXT_TRACK),
        },
    )
    api = player._lg_display
    api.dashboard_available = api.pip_available = api.media_view_available = True
    api.view_sources = {
        "dashboard": "Dashboard",
        "pip_view": "Dashboard PiP",
        "media_view": "Mediaplayer",
    }
    api.active_view = None
    api.dashboard_active = api.pip_active = api.media_view_active = False

    async def view(key):
        api.active_view = key
        api.presentation_active = True

    api.async_select_view = AsyncMock(side_effect=view)
    api.async_select_pip = AsyncMock(side_effect=lambda: view("pip_view"))
    api.async_select_media_view = AsyncMock(side_effect=lambda: view("media_view"))

    # AsyncMock does not await a coroutine returned by a synchronous lambda.
    async def pip():
        await view("pip_view")

    async def media():
        await view("media_view")

    api.async_select_pip.side_effect = pip
    api.async_select_media_view.side_effect = media
    player._async_ensure_display_on_after_power_restore = AsyncMock()
    return player


@pytest.mark.parametrize("view", [None, "dashboard", "pip_view", "media_view"])
@pytest.mark.parametrize("sound", ["music", "tv", "htastream", "unavailable", "paused"])
def test_cover_title_position_and_transport_follow_audible_player(audio, view, sound):
    audio._lg_display.active_view = view
    audio._lg_display.presentation_active = view is not None
    old = audio._test_states["media_player.sonos"]
    attrs = dict(old.attributes)
    if sound == "tv":
        attrs.update(source="TV", media_content_type="music")
    if sound == "htastream":
        attrs.update(
            source="Something", media_content_id="x-sonos-htastream:RINCON:spdif"
        )
    audio._test_states[old.entity_id] = State(
        old.entity_id, sound if sound in ["unavailable", "paused"] else "playing", attrs
    )
    use_sonos = sound in ["music", "paused"]
    assert audio._playback_target == (
        "media_player.sonos" if use_sonos else "media_player.apple_tv"
    )
    assert audio.media_title == ("Song" if use_sonos else "Film")
    assert audio.media_image_url.endswith("sonos" if use_sonos else "apple")
    assert audio.media_position == (12 if use_sonos else None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        "HDMI 1",
        "Dashboard",
        "Dashboard PiP",
        "Mediaplayer",
        "Sonos",
        "PiP Sonos",
        "Netflix",
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
async def test_only_explicit_hdmi_can_switch_tv_audio(audio, source, enabled):
    audio._config_entry.options["sonos_select_tv_source"] = enabled
    audio._linked_source_list = ["Netflix"]
    audio._async_call_volume_service = AsyncMock(return_value=True)
    await audio.async_select_source(source)
    if source == "HDMI 1" and enabled:
        audio._async_call_volume_service.assert_awaited_once_with(
            "select_source", source="TV"
        )
    else:
        audio._async_call_volume_service.assert_not_awaited()
    if source in ["Sonos", "PiP Sonos"]:
        assert audio.source == source
        assert audio.state == "playing"
        audio._async_call_linked_service.assert_not_awaited()
        audio._lg_display.async_set_input.assert_not_awaited()


@pytest.mark.asyncio
async def test_power_on_does_not_select_tv_audio(audio):
    audio._config_entry.options["sonos_select_tv_source"] = True
    audio._async_call_volume_service = AsyncMock()
    await audio.async_turn_on()
    audio._async_call_volume_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_music_transport_reaches_sonos_and_tv_transport_reaches_apple(audio):
    await audio.async_media_pause()
    audio.hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "media_pause",
        {"entity_id": "media_player.sonos"},
        blocking=True,
    )
    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos", "playing", {"source": "TV"}
    )
    await audio.async_media_pause()
    audio._async_call_linked_service.assert_awaited_once_with("media_pause")


@pytest.mark.asyncio
async def test_artwork_uses_original_entity_without_recursive_proxy(audio):
    entity = SimpleNamespace(
        async_get_media_image=AsyncMock(return_value=(b"jpeg", "image/jpeg"))
    )
    component = Mock()
    component.get_entity.return_value = entity
    audio.hass.data["media_player"] = component
    assert await audio.async_get_media_image() == (b"jpeg", "image/jpeg")
    component.get_entity.assert_called_once_with("media_player.sonos")
    component.get_entity.return_value = audio
    assert await audio.async_get_media_image() == (None, None)


@pytest.mark.asyncio
async def test_failed_sonos_does_not_undo_hdmi_selection(audio):
    audio._config_entry.options["sonos_select_tv_source"] = True
    audio._async_call_volume_service = AsyncMock(return_value=False)
    await audio.async_select_source("HDMI 1")
    assert audio.source == "HDMI 1"


def test_unique_names_and_optional_sources(audio):
    audio._sources["Sonos"] = 0x91
    audio._lg_display.view_sources["custom"] = "PiP Sonos"
    audio._linked_source_list = ["Sonos (Audio)", "PiP Sonos"]
    sources = audio.source_list
    assert len(sources) == len(set(sources))
    assert "Sonos (Audio)" in sources and "PiP Sonos" in sources
    audio._lg_display.pip_available = False
    assert "pip_view" not in audio.audio_sources
    audio._config_entry.options.pop("linked_volume_media_player_entity_id")
    assert not audio.audio_sources


@pytest.mark.asyncio
async def test_external_view_change_clears_visible_sonos_alias(audio):
    await audio.async_select_source("PiP Sonos")
    audio._lg_display.active_view = "dashboard"
    assert audio.source == "Dashboard"


def test_no_signal_never_stops_sonos_music_on_hdmi(audio):
    assert not audio._standby_eligible()
    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos", "playing", {"source": "TV"}
    )
    assert audio._standby_eligible()


@pytest.mark.asyncio
async def test_countdown_names_actual_hdmi_player(audio):
    from test_power_state_alert import poll

    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos", "playing", {"source": "TV"}
    )
    audio.hass.config.language = "de"
    audio._config_entry.options["standby_notice_text"] = (
        "Kein HDMI-Signal. {action} in {seconds} Sekunden."
    )
    await poll(audio, 1000)
    assert (
        "Wohnzimmer Apple TV" in audio._lg_display.set_standby_notice.call_args.args[0]
    )


def test_temporary_presentations_suppress_transport(audio):
    audio._lg_display.presentation_active = True
    assert audio._playback_target is None
    audio._lg_display.active_view = "pip_view"
    audio._presentation_active = True
    assert audio._playback_target is None


@pytest.mark.asyncio
async def test_sonos_play_media_does_not_change_display_input(audio):
    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos",
        "playing",
        {"source": "Music", "supported_features": int(F.PLAY_MEDIA)},
    )
    audio._async_resolve_media = AsyncMock(
        return_value=("http://ha/music.mp3", "audio/mpeg")
    )
    await audio.async_play_media("music", "media-source://media_source/music.mp3")
    audio.hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.sonos",
            "media_content_type": "audio/mpeg",
            "media_content_id": "http://ha/music.mp3",
        },
        blocking=True,
    )
    audio._lg_display.async_set_input.assert_not_awaited()
    audio._async_call_linked_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_sonos_pause_keeps_resume_routed_to_same_player(audio):
    await audio.async_media_pause()
    old = audio._test_states["media_player.sonos"]
    audio._test_states[old.entity_id] = State(
        old.entity_id, "paused", dict(old.attributes)
    )
    await audio.async_media_play()
    assert [
        call.args[1] for call in audio.hass.services.async_call.await_args_list
    ] == ["media_pause", "media_play"]
    audio._async_call_linked_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_sound_failure_alert_names_device(audio):
    alerts = LGDisplayAlertState("test")
    audio.hass.data["av_companion"]["test"]["alert_state"] = alerts
    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos", "unavailable", {"friendly_name": "Wohnzimmer Sonos"}
    )
    await audio._async_call_volume_service("volume_set", volume_level=0.2)
    assert "Wohnzimmer Sonos" in alerts.attributes["active_issues"][0]["message"]


@pytest.mark.asyncio
async def test_separate_sonos_pip_view_follows_stable_id_and_deletion(audio):
    audio._lg_display.view_sources["view_sonos"] = "Music PiP"
    audio._config_entry.options["sonos_pip_view"] = "view_sonos"
    await audio.async_select_source("PiP Sonos")
    audio._lg_display.async_select_view.assert_awaited_once_with("view_sonos")
    assert audio.source == "PiP Sonos"
    assert "Music PiP" not in audio.source_list
    audio._audio_view = (
        None  # Direct selection/reload still identifies the assigned custom view.
    )
    assert audio.source == "PiP Sonos"
    audio._lg_display.view_sources.pop("view_sonos")
    await audio.async_select_source("PiP Sonos")
    audio._lg_display.async_select_pip.assert_awaited_once()
    assert audio.source == "PiP Sonos"


@pytest.mark.asyncio
async def test_apple_metadata_events_update_app_views_without_power_actions(audio):
    audio._test_states["media_player.sonos"] = State(
        "media_player.sonos", "playing", {"source": "TV"}
    )
    audio._lg_display.active_view = "media_view"
    audio._lg_display.presentation_active = True
    old = audio._test_states["media_player.apple_tv"]
    new = State(
        old.entity_id, "playing", {**dict(old.attributes), "media_title": "New movie"}
    )
    audio._test_states[old.entity_id] = new
    await audio._async_handle_linked_state_change(
        SimpleNamespace(data={"old_state": old, "new_state": new})
    )
    audio.async_write_ha_state.assert_called_once()
    assert audio.media_title == "New movie"
    audio._start_display_wake_task.assert_not_called()
    audio._lg_display.async_power_off.assert_not_awaited()
