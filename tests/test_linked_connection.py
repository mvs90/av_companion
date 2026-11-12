"""Native connection recovery must never imply a power or playback request."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from pyatv.const import Protocol


def prepare(
    player, *, reason="Protocol(s) RAOP not yet found for TV, waiting for discovery."
):
    entry = SimpleNamespace(
        entry_id="apple",
        domain="apple_tv",
        reason=reason,
        data={
            "address": "192.0.2.1",
            "name": "TV",
            "credentials": {
                str(Protocol.AirPlay.value): "test-airplay",
                str(Protocol.Companion.value): "test-companion",
                str(Protocol.RAOP.value): "test-raop",
            },
        },
    )
    player._state = "off"
    player._apple_tv_entry = Mock(return_value=entry)
    player.hass.config_entries = SimpleNamespace(
        async_reload=AsyncMock(return_value=True), async_update_entry=Mock()
    )
    player._clear_issue = Mock()
    player._report_issue = Mock()
    return entry


def no_output(player):
    player.hass.services.async_call.assert_not_awaited()
    player._lg_display.async_power_on.assert_not_awaited()
    player._lg_display.async_power_off.assert_not_awaited()
    player._start_display_wake_task.assert_not_called()


async def test_explicit_missing_raop_repair_preserves_identifiers_and_other_credentials(
    player,
):
    entry = prepare(player)
    store = SimpleNamespace(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock()
    )
    with patch(
        "custom_components.av_companion.linked_connection.Store", return_value=store
    ):
        await player.async_refresh_linked_connection(repair_missing_raop=True)
    saved = store.async_save.call_args.args[0]["credentials"]
    assert str(Protocol.RAOP.value) in saved
    data = player.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data["address"] == entry.data["address"]
    assert data["credentials"] == {
        str(Protocol.AirPlay.value): "test-airplay",
        str(Protocol.Companion.value): "test-companion",
    }
    player.hass.config_entries.async_reload.assert_awaited_once_with("apple")
    assert "test-" not in str(player._linked_connection_health)
    no_output(player)


async def test_plain_reconnect_never_modifies_pairing(player):
    prepare(player)
    await player.async_refresh_linked_connection()
    player.hass.config_entries.async_update_entry.assert_not_called()
    no_output(player)


@pytest.mark.parametrize(
    "reason",
    [
        "",
        "Timeout",
        "Protocol(s) Companion not yet found",
        "Protocol(s) RAOP, AirPlay not yet found",
    ],
)
async def test_never_remove_unknown_or_required_protocols(player, reason):
    prepare(player, reason=reason)
    with pytest.raises(HomeAssistantError):
        await player.async_refresh_linked_connection(repair_missing_raop=True)
    player.hass.config_entries.async_update_entry.assert_not_called()
    player.hass.config_entries.async_reload.assert_not_awaited()
    no_output(player)


async def test_missing_companion_pairing_is_not_repaired(player):
    entry = prepare(player)
    entry.data["credentials"].pop(str(Protocol.Companion.value))
    with pytest.raises(HomeAssistantError):
        await player.async_refresh_linked_connection(repair_missing_raop=True)
    player.hass.config_entries.async_update_entry.assert_not_called()


async def test_original_backup_is_never_overwritten(player):
    prepare(player)
    store = SimpleNamespace(
        async_load=AsyncMock(return_value={"credentials": {"old": "backup"}}),
        async_save=AsyncMock(),
    )
    with patch(
        "custom_components.av_companion.linked_connection.Store", return_value=store
    ):
        await player.async_refresh_linked_connection(repair_missing_raop=True)
    store.async_save.assert_not_awaited()


async def test_maintenance_events_never_wake_display(player):
    prepare(player)

    async def reload(_entry):
        state = State("media_player.apple_tv", "playing")
        player._test_states[state.entity_id] = state
        await player._async_handle_linked_state_change(
            SimpleNamespace(
                data={
                    "old_state": State(state.entity_id, "off"),
                    "new_state": state,
                }
            )
        )
        return True

    player.hass.config_entries.async_reload.side_effect = reload
    await player.async_refresh_linked_connection()
    assert not player._linked_connection_refreshing
    no_output(player)


@pytest.mark.parametrize(
    "guard",
    [
        "watchdog_off",
        "playing",
        "display_on",
        "lock",
        "fresh",
        "restored",
        "cooldown",
        "stopping",
    ],
)
async def test_watchdog_guards(player, guard):
    prepare(player)
    player._config_entry.options["linked_connection_watchdog"] = guard != "watchdog_off"
    state = SimpleNamespace(
        state="playing" if guard == "playing" else "paused",
        attributes={"restored": guard == "restored"},
        last_updated=datetime.now(timezone.utc)
        - timedelta(seconds=10 if guard == "fresh" else 7200),
    )
    player._test_states["media_player.apple_tv"] = state
    if guard == "display_on":
        player._state = "on"
    if guard == "lock":
        player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
    if guard == "cooldown":
        import time

        player._linked_connection_attempt = time.monotonic()
    if guard == "stopping":
        player._ha_stopping = True
    await player._async_check_linked_connection()
    player.hass.config_entries.async_reload.assert_not_awaited()
    no_output(player)


async def test_stale_paused_watchdog_reconnects_only_once(player):
    prepare(player)
    player._config_entry.options["linked_connection_watchdog"] = True
    player._test_states["media_player.apple_tv"] = SimpleNamespace(
        state="paused",
        attributes={},
        last_updated=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    await player._async_check_linked_connection()
    await player._async_check_linked_connection()
    player.hass.config_entries.async_reload.assert_awaited_once()
    player.hass.config_entries.async_update_entry.assert_not_called()
    no_output(player)


async def test_failed_refresh_is_diagnosed_and_rate_limited(player):
    prepare(player)
    player.hass.config_entries.async_reload.side_effect = TimeoutError
    with pytest.raises(TimeoutError):
        await player.async_refresh_linked_connection()
    assert player._linked_connection_health["action"] == "failed"
    assert not player._linked_connection_refreshing
    player._report_issue.assert_called_once()
    no_output(player)
