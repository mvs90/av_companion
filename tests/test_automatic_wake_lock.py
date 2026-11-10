"""An automation lock must revoke pending intent without blocking manual control."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import State

from custom_components.av_companion.media_player import AVMediaPlayer


async def prepare(player, monkeypatch):
    listeners = {}
    player.hass.bus.async_listen.side_effect = lambda name, callback: (
        listeners.__setitem__(name, callback) or Mock()
    )
    monkeypatch.setattr(
        "custom_components.av_companion.media_player.async_track_time_interval",
        lambda *args: Mock(),
    )
    monkeypatch.setattr(
        "custom_components.av_companion.media_player.async_track_state_change_event",
        lambda *args: Mock(),
    )
    await player.async_added_to_hass()
    player._start_display_wake_task = AVMediaPlayer._start_display_wake_task.__get__(player)
    player._config_entry.options.update(
        power_supply_switch_entity_id="switch.display_only",
        power_supply_startup_delay=5,
    )
    player._async_call_power_supply_service = AsyncMock(return_value=True)
    player._lg_display.async_get_power_status.side_effect = [False, False, True]
    player._async_remote_power = AsyncMock()
    entered, release = asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        if seconds == 5:
            entered.set()
            await release.wait()
        else:
            await real_sleep(0)

    monkeypatch.setattr("custom_components.av_companion.media_player.asyncio.sleep", sleep)
    return listeners["av_companion_automation_changed"], entered, release


def set_lock(player, callback, locked):
    player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = not locked
    callback(SimpleNamespace(data={"entry_id": "test"}))


async def linked_wake(player):
    before = State("media_player.apple_tv", "off")
    after = State("media_player.apple_tv", "idle")
    player._test_states[after.entity_id] = after
    await player._async_handle_linked_state_change(
        SimpleNamespace(data={"old_state": before, "new_state": after})
    )


async def finish(task):
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_lock_during_startup_delay_cancels_automatic_device_commands(player, monkeypatch):
    callback, entered, release = await prepare(player, monkeypatch)
    await linked_wake(player)
    task = player._display_wake_task
    await asyncio.wait_for(entered.wait(), 1)
    # Outlet power must be requested before the configurable device-start delay.
    player._async_call_power_supply_service.assert_awaited_once_with("turn_on")
    player._lg_display.async_power_on.assert_not_awaited()
    set_lock(player, callback, True)
    release.set()
    await finish(task)
    player._lg_display.async_power_on.assert_not_awaited()


@pytest.mark.asyncio
async def test_lock_before_scheduled_automatic_wake_prevents_even_outlet_on(player, monkeypatch):
    callback, _, release = await prepare(player, monkeypatch)
    await linked_wake(player)
    task = player._display_wake_task
    set_lock(player, callback, True)
    release.set()
    await finish(task)
    player._async_call_power_supply_service.assert_not_awaited()
    player._lg_display.async_power_on.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_wake_remains_available_while_automation_is_locked(player, monkeypatch):
    callback, entered, release = await prepare(player, monkeypatch)
    set_lock(player, callback, True)
    player._lg_display.async_get_power_status.side_effect = [False, True]
    player._start_display_wake_task("local media_player turn_on")
    task = player._display_wake_task
    await asyncio.wait_for(entered.wait(), 1)
    set_lock(player, callback, True)
    release.set()
    await finish(task)
    assert not task.cancelled()
    player._lg_display.async_power_on.assert_awaited_once()


@pytest.mark.asyncio
async def test_relocking_does_not_let_old_queued_intent_revive_after_unlock(player, monkeypatch):
    callback, _, release = await prepare(player, monkeypatch)
    state = State("media_player.apple_tv", "idle")
    player._test_states[state.entity_id] = state
    await player._control_lock.acquire()
    task = asyncio.create_task(player._async_linked_wake(state))
    # Wait until the real wake coroutine is queued at the control lock.
    await asyncio.wait_for(asyncio.shield(asyncio.create_task(_yield_once())), 1)
    set_lock(player, callback, True)
    set_lock(player, callback, False)
    player._control_lock.release()
    release.set()
    await task
    await finish(player._display_wake_task)
    player._async_call_power_supply_service.assert_not_awaited()


async def _yield_once():
    future = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


@pytest.mark.asyncio
async def test_manual_wake_supersedes_pending_automatic_wake(player, monkeypatch):
    _, entered, release = await prepare(player, monkeypatch)
    await linked_wake(player)
    old_task = player._display_wake_task
    await asyncio.wait_for(entered.wait(), 1)
    player._control_generation += 1
    player._start_display_wake_task("local media_player turn_on")
    manual_task = player._display_wake_task
    assert manual_task is not old_task
    release.set()
    await finish(old_task)
    await finish(manual_task)
    player._lg_display.async_power_on.assert_awaited_once()
    assert player._display_wake_task is None
    assert not player._display_wake_automatic
