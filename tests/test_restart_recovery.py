"""Real runtime reconnects and signal-loss off/wake races, not stale polling."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from homeassistant.core import State


def change(player, old, new, **attrs):
    state = State("media_player.apple_tv", new, attrs)
    player._test_states[state.entity_id] = state
    return SimpleNamespace(
        data={
            "old_state": State(state.entity_id, old) if old else None,
            "new_state": state,
        }
    )


@pytest.mark.parametrize("returned", ["idle", "playing", "paused", "on"])
async def test_reboot_off_unknown_active_after_automatic_standby(player, returned):
    with patch("time.monotonic", return_value=1000):
        await player._async_turn_off_locked(no_signal=True)
        player._lg_display.async_get_power_status.return_value = False
        await player._async_handle_linked_state_change(change(player, "off", "unknown"))
        await player._async_handle_linked_state_change(
            change(player, "unknown", returned)
        )
    player._start_display_wake_task.assert_called_once()
    player._async_call_linked_service.assert_not_awaited()
    assert not player._standby_latched


async def test_reconnect_seen_before_signal_shutdown_remembered(player):
    with patch("time.monotonic", return_value=1000):
        await player._async_handle_linked_state_change(
            change(player, "playing", "unavailable")
        )
        await player._async_turn_off_locked(no_signal=True)
    player._lg_display.async_get_power_status.return_value = False
    with patch("time.monotonic", return_value=1020):
        await player._async_handle_linked_state_change(
            change(player, "unavailable", "idle")
        )
    player._start_display_wake_task.assert_called_once()


@pytest.mark.parametrize(
    "guard", ["startup", "expired", "manual_off", "baseline", "restored", "lock"]
)
async def test_unproven_reconnect_never_wakes(player, guard):
    with patch("time.monotonic", return_value=1000):
        if guard != "baseline":
            await player._async_turn_off_locked(no_signal=True)
        if guard == "startup":
            player._startup_off_guard_until = 1100
        if guard == "manual_off":
            await player.async_turn_off()
        if guard == "lock":
            player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
            player._schedule_blocked_linked_turn_off = Mock()
        if guard != "baseline":
            await player._async_handle_linked_state_change(
                change(player, "off", "unknown")
            )
    player._lg_display.async_get_power_status.return_value = False
    with patch("time.monotonic", return_value=2000 if guard == "expired" else 1001):
        await player._async_handle_linked_state_change(
            change(
                player,
                None if guard == "baseline" else "unknown",
                "idle",
                restored=guard == "restored",
            )
        )
    player._start_display_wake_task.assert_not_called()


@pytest.mark.parametrize(
    "cancel", [None, "manual_off", "lock", "inactive", "stopping", "presentation"]
)
async def test_play_event_during_off_is_serialized_and_revalidated(player, cancel):
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_off():
        entered.set()
        await release.wait()
        player._lg_display.async_get_power_status.return_value = False
        return True

    player._lg_display.async_power_off.side_effect = slow_off

    async def shut_down():
        async with player._control_lock:
            await player._async_turn_off_locked(no_signal=True)

    off = asyncio.create_task(shut_down())
    await entered.wait()
    wake = asyncio.create_task(
        player._async_handle_linked_state_change(change(player, "off", "playing"))
    )
    await asyncio.sleep(0)
    player._start_display_wake_task.assert_not_called()
    if cancel == "manual_off":
        player._clear_restart_recovery()
    elif cancel == "lock":
        player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
    elif cancel == "inactive":
        change(player, "playing", "off")
    elif cancel == "stopping":
        player._ha_stopping = True
    elif cancel == "presentation":
        player._lg_display.presentation_active = True
    release.set()
    await asyncio.gather(off, wake)
    assert player._start_display_wake_task.call_count == (cancel is None)
    player._async_call_linked_service.assert_not_awaited()


async def test_automatic_off_not_forwarded_again_by_later_polls(player):
    player._last_display_power = True
    await player._async_turn_off_locked(no_signal=True)
    player._lg_display.async_get_power_status.return_value = False
    for _ in range(3):
        await player.async_update()
    player._async_call_linked_service.assert_not_awaited()
    player._start_display_wake_task.assert_not_called()


async def test_normal_manual_off_still_turns_off_player(player):
    await player.async_turn_off()
    player._async_call_linked_service.assert_awaited_once_with("turn_off")


async def test_metadata_update_during_power_read_keeps_genuine_wake(player):
    event = change(player, "off", "playing")
    current = event.data["new_state"]

    async def power(**kwargs):
        player._test_states[current.entity_id] = State(
            current.entity_id,
            "playing",
            {"media_title": "Movie"},
            last_changed=current.last_changed,
        )
        return False

    player._lg_display.async_get_power_status.side_effect = power
    await player._async_handle_linked_state_change(event)
    player._start_display_wake_task.assert_called_once()


async def test_poll_cannot_forward_off_while_wake_is_pending(player):
    player._last_display_power = True
    player._pending_state = "on"
    player._pending_state_until = float("inf")
    player._lg_display.async_get_power_status.return_value = False
    for _ in range(3):
        await player.async_update()
    player._async_call_linked_service.assert_not_awaited()


async def test_off_cancels_intent_already_waiting_for_power_response(player):
    entered, release = asyncio.Event(), asyncio.Event()

    async def power(**kwargs):
        entered.set()
        await release.wait()
        return False

    player._lg_display.async_get_power_status.side_effect = power
    wake = asyncio.create_task(
        player._async_handle_linked_state_change(change(player, "off", "playing"))
    )
    await entered.wait()
    player._clear_restart_recovery()
    release.set()
    await wake
    player._start_display_wake_task.assert_not_called()
