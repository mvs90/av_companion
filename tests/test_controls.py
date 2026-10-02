import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.core import State
from homeassistant.components.media_player import MediaPlayerEntityFeature as F
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from custom_components.av_companion.controls import in_quiet_hours
from homeassistant.util import dt as dt_util


@pytest.mark.parametrize("condition", ["missing", "restored", "unavailable"])
def test_unavailable_volume_target_clears_cached_values(player, condition):
    entity_id = "media_player.sonos"
    player._config_entry.options["linked_volume_media_player_entity_id"] = entity_id
    player._test_states[entity_id] = State(
        entity_id, "playing", {"volume_level": 0.4, "is_volume_muted": False}
    )
    player._update_volume_cache_from_state()
    assert player.volume_level == 0.4
    if condition == "missing":
        del player._test_states[entity_id]
    else:
        player._test_states[entity_id] = State(
            entity_id,
            "unavailable" if condition == "unavailable" else "idle",
            {"restored": condition == "restored"},
        )
    player._update_volume_cache_from_state()
    assert player.volume_level is None
    assert player.is_volume_muted is None


@pytest.mark.asyncio
async def test_turn_off_cancels_pending_wake(player):
    started = asyncio.Event()

    async def wake():
        started.set()
        await asyncio.sleep(3600)
        await player._lg_display.async_power_on()

    task = asyncio.create_task(wake())
    player._display_wake_task = task
    await started.wait()
    await player.async_turn_off()
    assert task.cancelled()
    player._lg_display.async_power_off.assert_awaited_once()
    player._lg_display.async_power_on.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("on", "command"), [(True, "wakeup"), (False, "suspend")])
async def test_apple_remote_power(player, on, command):
    player._config_entry.options.update(
        linked_remote_entity_id="remote.apple_tv", linked_remote_power_mode="apple_tv"
    )
    player._test_states["remote.apple_tv"] = State("remote.apple_tv", "on")
    await player._async_remote_power(on)
    player.hass.services.async_call.assert_awaited_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.apple_tv", "command": command},
        blocking=True,
    )
    player._async_call_linked_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_homekit_ignores_other_tv_and_routes_active_input(player):
    player._config_entry.options["linked_remote_entity_id"] = "remote.apple_tv"
    player._test_states["remote.apple_tv"] = State("remote.apple_tv", "on")
    await player._async_homekit_key(
        SimpleNamespace(
            data={"entity_id": "media_player.other", "key_name": "arrow_up"}
        )
    )
    player.hass.services.async_call.assert_not_awaited()
    await player._async_homekit_key(
        SimpleNamespace(data={"entity_id": player.entity_id, "key_name": "arrow_up"})
    )
    assert player.hass.services.async_call.await_args.args[2]["command"] == "up"
    player.hass.services.async_call.reset_mock()
    player._lg_display.async_get_input.return_value = 0x91
    await player.async_send_remote_command("left")
    player.hass.services.async_call.assert_not_awaited()
    player._lg_display.async_send_remote_key.assert_awaited_once_with(0x07)


@pytest.mark.asyncio
async def test_features_never_advertise_fake_tracks_or_missing_volume(player):
    player._current_input_id = 0x91
    assert not player.supported_features & F.NEXT_TRACK
    player._current_input_id = 0x90
    player._config_entry.options["linked_volume_media_player_entity_id"] = (
        "media_player.missing"
    )
    assert not player.supported_features & F.VOLUME_SET
    with pytest.raises(ServiceValidationError):
        await player.async_media_previous_track()


@pytest.mark.asyncio
async def test_media_source_resolved_for_target_and_forwarded(player):
    player._async_prepare_content = AsyncMock()
    with (
        patch(
            "custom_components.av_companion.controls.media_source.async_resolve_media",
            new_callable=AsyncMock,
        ) as resolve,
        patch(
            "custom_components.av_companion.controls.async_process_play_media_url",
            return_value="http://example.test/signed.mp4",
        ),
    ):
        resolve.return_value = SimpleNamespace(
            url="/media/file.mp4", mime_type="video/mp4"
        )
        await player.async_play_media(
            "video", "media-source://media_source/local/file.mp4"
        )
        resolve.assert_awaited_once_with(
            player.hass,
            "media-source://media_source/local/file.mp4",
            "media_player.apple_tv",
        )
    args = player.hass.services.async_call.await_args.args
    assert args[2]["media_content_type"] == "video/mp4"
    assert args[2]["media_content_id"] == "http://example.test/signed.mp4"


@pytest.mark.asyncio
async def test_deep_link_untouched(player):
    player._async_prepare_content = AsyncMock()
    await player.async_play_media("url", "youtube://watch/example")
    assert (
        player.hass.services.async_call.await_args.args[2]["media_content_id"]
        == "youtube://watch/example"
    )


@pytest.mark.asyncio
async def test_sonos_announcement_preserves_persistent_volume(player):
    player._config_entry.options["linked_volume_media_player_entity_id"] = (
        "media_player.sonos"
    )
    player._test_states["media_player.sonos"] = State(
        "media_player.sonos", "playing", {"supported_features": int(F.MEDIA_ANNOUNCE)}
    )
    player._async_resolve_media = AsyncMock(
        return_value=("http://example.test/chime.mp3", "music")
    )
    await player.async_announce("http://example.test/chime.mp3", volume=30)
    call = player.hass.services.async_call.await_args
    assert call.args[:2] == ("media_player", "play_media")
    assert call.args[2]["announce"] is True
    assert call.args[2]["extra"] == {"volume": 30}
    assert player.hass.services.async_call.await_count == 1


@pytest.mark.asyncio
async def test_optional_sonos_switch(player):
    with pytest.raises(ServiceValidationError):
        await player.async_set_sound_mode("night", True)
    player._config_entry.options["sonos_night_sound_entity_id"] = "switch.sonos_night"
    player._test_states["switch.sonos_night"] = State("switch.sonos_night", "off")
    await player.async_set_sound_mode("night", True)
    assert player.hass.services.async_call.await_args.args[:2] == ("switch", "turn_on")


@pytest.mark.asyncio
async def test_overlay_requires_real_backend(player):
    with pytest.raises(ServiceValidationError, match="renderer"):
        await player.async_show_notification("Test")
    assert not player._presentation_queue


@pytest.mark.parametrize(
    ("hour", "expected"), [(12, False), (23, True), (6, True), (7, False)]
)
def test_overnight_quiet_hours(hour, expected):
    with patch(
        "custom_components.av_companion.controls.dt_util.now",
        return_value=dt_util.now().replace(hour=hour, minute=0, second=0),
    ):
        assert in_quiet_hours("22:00", "07:00") is expected


def test_power_evidence_requires_valid_units_freshness_and_number(player):
    player._config_entry.options.update(
        power_sensor_entity_id="sensor.watts", standby_power_threshold=5
    )
    for value, unit, expected in [
        ("2", "W", True),
        ("0.002", "kW", True),
        ("nan", "W", False),
        ("2", "kWh", False),
        ("unavailable", "W", False),
        ("10", "W", False),
    ]:
        player._test_states["sensor.watts"] = State(
            "sensor.watts", value, {"unit_of_measurement": unit}
        )
        assert player._power_sensor_in_standby() is expected
    player._test_states["sensor.watts"] = State(
        "sensor.watts",
        "2",
        {"unit_of_measurement": "W"},
        last_updated=dt_util.utcnow() - __import__("datetime").timedelta(seconds=181),
    )
    assert not player._power_sensor_in_standby()


def content_request(**kwargs):
    return dict(
        kind="content",
        media_id="test",
        media_type="video",
        duration=1,
        priority="normal",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_presentation_restores_original_input(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._lg_display.async_get_input.side_effect = [0x90, 0x91]
    player._async_play_content = AsyncMock()
    with patch(
        "custom_components.av_companion.controls.asyncio.sleep", new_callable=AsyncMock
    ):
        await player._async_present_one(content_request())
    player._lg_display.async_set_input.assert_awaited_once_with(0x90)
    assert not player._presentation_active


@pytest.mark.asyncio
async def test_presentation_does_not_override_manual_input_change(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._lg_display.async_get_input.side_effect = [0x90, 0x92]
    player._async_play_content = AsyncMock()
    with patch(
        "custom_components.av_companion.controls.asyncio.sleep", new_callable=AsyncMock
    ):
        await player._async_present_one(content_request())
    player._lg_display.async_set_input.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_during_content_startup_restores_input(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._lg_display.async_get_input.side_effect = [0x90, 0x91]
    started = asyncio.Event()

    async def play(*_):
        started.set()
        await asyncio.sleep(3600)

    player._async_play_content = play
    player._presentation_queue.append(content_request())
    player._presentation_task = asyncio.create_task(player._async_presentations())
    await started.wait()
    await player._async_cancel_presentations()
    player._lg_display.async_set_input.assert_awaited_once_with(0x90)
    assert not player._presentation_active
    assert not player._presentation_queue


@pytest.mark.asyncio
async def test_standby_and_linked_events_ignored_during_presentation(player):
    player._presentation_active = True
    await player._async_check_standby()
    await player.async_update()
    await player._async_handle_linked_state_change(
        SimpleNamespace(
            data={
                "old_state": State("media_player.apple_tv", "playing"),
                "new_state": State("media_player.apple_tv", "off"),
            }
        )
    )
    player._lg_display.async_power_off.assert_not_awaited()
    player._start_display_wake_task.assert_not_called()


@pytest.mark.asyncio
async def test_presentations_do_not_wake_by_default(player):
    player._lg_display.async_get_power_status.return_value = False
    player._async_play_content = AsyncMock()
    with pytest.raises(HomeAssistantError, match="wake is disabled"):
        await player._async_present_one(content_request())
    player._async_play_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_renderer_receives_show_and_clear_same_token(player):
    player._config_entry.options["notification_script_entity_id"] = "script.screen"
    with patch(
        "custom_components.av_companion.controls.asyncio.sleep", new_callable=AsyncMock
    ):
        await player._async_present_one(
            dict(
                kind="notification",
                message="Hello",
                title="Test",
                duration=5,
                priority="normal",
                mode="overlay",
            )
        )
    calls = player.hass.services.async_call.await_args_list
    assert [c.args[2]["action"] for c in calls] == ["show", "clear"]
    assert calls[0].args[2]["session_id"] == calls[1].args[2]["session_id"]


@pytest.mark.asyncio
async def test_queue_is_bounded_and_urgent_goes_next(player):
    player._presentation_task = Mock()
    player._presentation_task.done.return_value = False
    await player.async_show_content("first")
    await player.async_show_content("urgent", priority="urgent")
    assert player._presentation_queue[0]["media_id"] == "urgent"
    for i in range(8):
        await player.async_show_content(str(i))
    with pytest.raises(ServiceValidationError, match="full"):
        await player.async_show_content("overflow")


@pytest.mark.asyncio
async def test_socket_requires_actual_target_state(player):
    player._test_states["switch.socket"] = State("switch.socket", "on")
    with patch(
        "custom_components.av_companion.media_player.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        assert not await player._async_call_switch_service("switch.socket", "turn_off")
    player._test_states["switch.socket"] = State("switch.socket", "off")
    assert await player._async_call_switch_service("switch.socket", "turn_off")


@pytest.mark.asyncio
async def test_presentation_failure_restores_input(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._lg_display.async_get_input.side_effect = [0x90, 0x91]
    player._async_play_content = AsyncMock(
        side_effect=HomeAssistantError("playback failed")
    )
    with pytest.raises(HomeAssistantError):
        await player._async_present_one(content_request())
    player._lg_display.async_set_input.assert_awaited_once_with(0x90)
    assert not player._presentation_active


@pytest.mark.asyncio
async def test_quiet_hours_reject_normal_but_accept_urgent(player):
    player._config_entry.options["quiet_hours_enabled"] = True
    player._presentation_task = Mock()
    player._presentation_task.done.return_value = False
    with patch(
        "custom_components.av_companion.controls.in_quiet_hours", return_value=True
    ):
        with pytest.raises(ServiceValidationError, match="quiet"):
            await player.async_show_content("normal")
        await player.async_show_content("urgent", priority="urgent")
    assert len(player._presentation_queue) == 1


@pytest.mark.asyncio
async def test_unload_cancels_presentation_and_clears_renderer(player):
    started = asyncio.Event()
    player._config_entry.options["notification_script_entity_id"] = "script.screen"

    async def render(request, action, token):
        if action == "show":
            started.set()

    player._async_notification_renderer = AsyncMock(side_effect=render)
    player._presentation_queue.append(
        dict(
            kind="notification",
            message="Test",
            title="",
            duration=3600,
            priority="normal",
            mode="overlay",
        )
    )
    player._presentation_task = asyncio.create_task(player._async_presentations())
    await started.wait()
    await player.async_will_remove_from_hass()
    assert [c.args[1] for c in player._async_notification_renderer.await_args_list] == [
        "show",
        "clear",
    ]
    assert player._presentation_task is None


@pytest.mark.asyncio
async def test_wake_waits_for_fresh_on_confirmation(player):
    player._lg_display.async_get_power_status.side_effect = [False, False, True]
    with patch(
        "custom_components.av_companion.media_player.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        await player._async_ensure_display_on_after_power_restore("test")
    player._lg_display.async_power_on.assert_awaited_once()
    assert player._lg_display.async_get_power_status.await_count == 3
    assert all(
        c.kwargs == {"use_cache": False}
        for c in player._lg_display.async_get_power_status.await_args_list
    )


@pytest.mark.asyncio
async def test_content_target_has_its_own_playback_controls(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._current_input_id = 0x91
    player._test_states["media_player.content"] = State(
        "media_player.content",
        "playing",
        {"supported_features": int(F.PAUSE | F.SEEK), "media_title": "Doorbell"},
    )
    assert player.supported_features & F.PAUSE
    assert player.media_title == "Doorbell"
    assert player.state == "playing"
    await player.async_media_pause()
    assert (
        player.hass.services.async_call.await_args.args[2]["entity_id"]
        == "media_player.content"
    )


@pytest.mark.asyncio
async def test_content_toggle_and_seek_metadata_use_current_player(player):
    player._config_entry.options["content_media_player_entity_id"] = (
        "media_player.content"
    )
    player._current_input_id = 0x91
    player._test_states["media_player.content"] = State(
        "media_player.content",
        "playing",
        {
            "supported_features": int(F.PAUSE | F.SEEK),
            "media_duration": 120,
            "media_position": 30,
            "media_position_updated_at": "2026-10-02T10:00:00+00:00",
            "shuffle": True,
            "repeat": "all",
        },
    )
    await player.async_media_play_pause()
    assert player.hass.services.async_call.await_args.args[1] == "media_pause"
    assert player.media_duration == 120
    assert player.media_position == 30
    assert player.media_position_updated_at is not None
    assert player.shuffle is True and player.repeat == "all"
