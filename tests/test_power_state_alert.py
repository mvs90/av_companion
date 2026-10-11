"""Confirmed source/HDMI conflicts surface through the actual alert sensor."""

from unittest.mock import patch
import pytest
from homeassistant.core import State
from custom_components.av_companion.alerts import LGDisplayAlertState
from custom_components.av_companion.sensor import LGDisplayAlertSensor


@pytest.fixture
def alerted_player(player):
    alerts = LGDisplayAlertState("test")
    player.hass.data["av_companion"]["test"]["alert_state"] = alerts
    player._lg_display.async_get_signal_status.return_value = True
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "off", {"friendly_name": "Wohnzimmer Apple TV"}
    )
    player.hass.config.language = "de"
    return player, LGDisplayAlertSensor(alerts, "Test AV", "test")


async def poll(player, now):
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=now
    ):
        await player.async_update()


@pytest.mark.asyncio
@pytest.mark.parametrize("locked", [True, False])
async def test_conflict_alert_confirmed_with_or_without_automation_lock(
    alerted_player, locked
):
    player, sensor = alerted_player
    player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = not locked
    for now in (1000, 1059, 1119):
        await poll(player, now)
        assert sensor.state == "OK"
        assert not player.extra_state_attributes["linked_power_state_conflict"]
    await poll(player, 1120)
    assert (
        sensor.state
        == "Wohnzimmer Apple TV meldet aus/Standby trotz HDMI-Signal: Player-Integration prüfen"
    )
    assert sensor.icon == "mdi:alert"
    assert player.extra_state_attributes["linked_power_state_conflict"]
    issues = sensor.extra_state_attributes["active_issues"]
    assert len(issues) == 1
    assert issues[0]["code"] == "linked_power_state_conflict"
    assert issues[0]["source"] == "media_player.apple_tv"
    assert issues[0]["details"]["confirmation_seconds"] == 120
    assert "hdmi_extractor_retains_signal" in issues[0]["details"]["possible_causes"]
    history = sensor.extra_state_attributes["history"]
    for now in (1200, 1300):
        await poll(player, now)
    assert sensor.extra_state_attributes["history"] == history
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "signal_loss",
        "unknown_signal",
        "playing",
        "unavailable",
        "other_input",
        "presentation",
        "display_off",
        "unreachable",
        "disabled_query",
    ],
)
async def test_conflict_warning_clears_when_no_longer_confirmable(
    alerted_player, change
):
    player, sensor = alerted_player
    await poll(player, 1000)
    await poll(player, 1120)
    assert sensor.state != "OK"
    if change == "signal_loss":
        player._lg_display.async_get_signal_status.return_value = False
    elif change == "unknown_signal":
        player._lg_display.async_get_signal_status.return_value = None
    elif change in {"playing", "unavailable"}:
        player._test_states["media_player.apple_tv"] = State(
            "media_player.apple_tv", change
        )
    elif change == "other_input":
        player._lg_display.async_get_input.return_value = 0x91
    elif change == "presentation":
        player._lg_display.presentation_active = True
    elif change == "display_off":
        player._lg_display.async_get_power_status.return_value = False
    elif change == "unreachable":
        player._lg_display.async_get_power_status.return_value = None
    elif change == "disabled_query":
        player._config_entry.options["standby_signal_check"] = False
    await poll(player, 1130)
    assert not player.extra_state_attributes["linked_power_state_conflict"]
    assert not any(
        issue["code"] == "linked_power_state_conflict"
        for issue in sensor.extra_state_attributes["active_issues"]
    )
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_signal_gap_restarts_conflict_confirmation(alerted_player):
    player, sensor = alerted_player
    await poll(player, 1000)
    player._lg_display.async_get_signal_status.return_value = None
    await poll(player, 1119)
    player._lg_display.async_get_signal_status.return_value = True
    await poll(player, 1120)
    await poll(player, 1239)
    assert sensor.state == "OK"
    await poll(player, 1240)
    assert player.extra_state_attributes["linked_power_state_conflict"]


@pytest.mark.asyncio
async def test_startup_and_restored_player_do_not_confirm_conflict(alerted_player):
    player, sensor = alerted_player
    player._startup_off_guard_until = 9999
    for now in (1000, 1120):
        await poll(player, now)
        assert sensor.state == "OK"
    player._startup_off_guard_until = 0
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "off", {"restored": True}
    )
    for now in (2000, 2120):
        await poll(player, now)
    assert not player.extra_state_attributes["linked_power_state_conflict"]
