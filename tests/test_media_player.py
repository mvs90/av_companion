from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.core import State
from homeassistant.components.media_player import MediaPlayerState


@pytest.mark.asyncio
async def test_idle_no_signal_shutdown_then_no_polling_rewake(player):
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1000
    ):
        await player.async_update()
    player._lg_display.async_power_off.assert_not_awaited()
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1121
    ):
        await player.async_update()
    player._lg_display.async_power_off.assert_awaited_once()
    assert player.state == MediaPlayerState.OFF
    assert player._last_standby_reason == "no_signal"
    player._lg_display.async_get_power_status.return_value = False
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=2000
    ):
        await player.async_update()
    player._start_display_wake_task.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["idle", "playing", "paused"])
async def test_attribute_updates_do_not_wake(player, state):
    player._lg_display.async_get_power_status.return_value = False
    event = SimpleNamespace(
        data={
            "old_state": State("media_player.apple_tv", state),
            "new_state": State(
                "media_player.apple_tv", state, {"media_title": "changed"}
            ),
        }
    )
    await player._async_handle_linked_state_change(event)
    player._start_display_wake_task.assert_not_called()


@pytest.mark.asyncio
async def test_real_play_transition_can_wake(player):
    player._lg_display.async_get_power_status.return_value = False
    event = SimpleNamespace(
        data={
            "old_state": State("media_player.apple_tv", "idle"),
            "new_state": State("media_player.apple_tv", "playing"),
        }
    )
    await player._async_handle_linked_state_change(event)
    player._start_display_wake_task.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "other_input",
        "startup",
        "disabled",
        "signal_returns",
        "playing_unknown",
        "unavailable_unknown",
    ],
)
async def test_shutdown_guards(player, mode):
    if mode == "other_input":
        player._current_input_id = 0x91
    if mode == "startup":
        player._startup_off_guard_until = 9999
    if mode == "disabled":
        player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
    if mode.endswith("_unknown"):
        state = mode.removesuffix("_unknown")
        player._test_states["media_player.apple_tv"] = State(
            "media_player.apple_tv", state
        )
        player._lg_display.async_get_signal_status.return_value = None
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1000
    ):
        await player._async_check_standby()
    if mode == "signal_returns":
        player._lg_display.async_get_signal_status.side_effect = [False, True]
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=3000
    ):
        await player._async_check_standby()
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_player_clears_cached_playing(player):
    player._linked_state = "playing"
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "unavailable"
    )
    player._update_linked_cache_from_state()
    assert player._linked_state is None


@pytest.mark.asyncio
async def test_power_socket_not_cut_on_unknown_status(player):
    player._config_entry.options["power_supply_off_delay_seconds"] = 0
    player._lg_display.async_get_power_status.return_value = None
    player._async_call_power_supply_service = AsyncMock()
    await player._async_delayed_power_supply_off("test")
    player._async_call_power_supply_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_shutdown_when_signal_unsupported(player):
    player._lg_display.async_get_signal_status.return_value = None
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1000
    ):
        await player._async_check_standby()
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1900
    ):
        await player._async_check_standby()
    player._lg_display.async_power_off.assert_awaited_once()
    assert player._last_standby_reason == "idle_timeout"


@pytest.mark.asyncio
async def test_input_changed_during_confirmation_cancels_shutdown(player):
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1000
    ):
        await player._async_check_standby()
    player._lg_display.async_get_input.return_value = 0x91
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=1121
    ):
        await player._async_check_standby()
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_playback_and_volume_routing(player):
    player._config_entry.options["linked_volume_media_player_entity_id"] = (
        "media_player.soundbar"
    )
    player._async_call_volume_service = AsyncMock(return_value=True)
    await player.async_media_play()
    await player.async_media_pause()
    await player.async_set_volume_level(0.4)
    assert [c.args[0] for c in player._async_call_linked_service.await_args_list] == [
        "media_play",
        "media_pause",
    ]
    player._async_call_volume_service.assert_awaited_once_with(
        "volume_set", volume_level=0.4
    )


@pytest.mark.asyncio
async def test_extractor_retained_signal_does_not_veto_confirmed_player_standby(player):
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "standby"
    )
    player._lg_display.async_get_signal_status.return_value = True
    for now in (1000, 1011):
        with patch(
            "custom_components.av_companion.media_player.time.monotonic",
            return_value=now,
        ):
            await player._async_check_standby()
    player._lg_display.async_power_off.assert_awaited_once()
    assert player._last_standby_reason == "linked_standby"


@pytest.mark.asyncio
async def test_display_socket_cut_targets_only_display_not_active_hdmi_chain(player):
    player._config_entry.options.update(
        power_supply_switch_entity_id="switch.display_socket",
        power_supply_off_delay_seconds=0,
        linked_volume_media_player_entity_id="media_player.sonos",
    )
    player._lg_display.async_get_power_status.return_value = False
    player._async_call_switch_service = AsyncMock(return_value=True)
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "standby"
    )
    await player._async_delayed_power_supply_off("display standby confirmed")
    player._async_call_switch_service.assert_awaited_once_with(
        "switch.display_socket", "turn_off"
    )
    player._async_call_linked_service.assert_not_awaited()
    player.hass.services.async_call.assert_not_awaited()
    player._start_display_wake_task.assert_not_called()


@pytest.mark.asyncio
async def test_player_remaining_in_standby_after_display_socket_off_never_wakes(player):
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "standby"
    )
    player._lg_display.async_get_power_status.return_value = False
    await player._async_handle_power_supply_state_change(
        SimpleNamespace(
            data={
                "new_state": State("switch.display_socket", "off"),
            }
        )
    )
    await player._async_handle_linked_state_change(
        SimpleNamespace(
            data={
                "old_state": State("media_player.apple_tv", "standby"),
                "new_state": State(
                    "media_player.apple_tv", "standby", {"app_name": "Apple TV"}
                ),
            }
        )
    )
    await player.async_update()
    player._start_display_wake_task.assert_not_called()
    player._async_call_linked_service.assert_not_awaited()
    player.hass.services.async_call.assert_not_awaited()
