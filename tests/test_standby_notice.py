"""Countdown deadlines remain independent of polling and never bypass guards."""

from unittest.mock import Mock, patch
import pytest
from test_power_state_alert import poll


@pytest.mark.asyncio
async def test_fifteen_second_default_schedules_once_and_clears_on_signal_return(
    player,
):
    player._config_entry.options.pop("standby_no_signal_seconds")
    player.hass.config.language = "de"
    with patch(
        "custom_components.av_companion.standby_notice.asyncio.get_running_loop"
    ) as loop:
        timer = Mock()
        loop.return_value.call_later.return_value = timer
        await poll(player, 1000)
        assert loop.return_value.call_later.call_args.args[0] == 15
        message, deadline = player._lg_display.set_standby_notice.call_args.args
        assert deadline == 1015 and "{seconds}" in message and "Ausschalten" in message
        await poll(player, 1005)
        loop.return_value.call_later.assert_called_once()
        due = loop.return_value.call_later.call_args.args[1]
        due()
        player.async_schedule_update_ha_state.assert_called_with(True)
        player._lg_display.async_get_signal_status.return_value = True
        await poll(player, 1010)
        player._lg_display.set_standby_notice.assert_called_with()
        assert player._standby_timer is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["lock", "temporary", "stopping", "unknown", "disabled"]
)
async def test_countdown_cancelled_on_invalidated_evidence(player, change):
    await poll(player, 1000)
    handle = player._standby_timer
    if change == "lock":
        player.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
    elif change == "temporary":
        player._lg_display.presentation_active = True
    elif change == "stopping":
        player._ha_stopping = True
    elif change == "unknown":
        player._lg_display.async_get_signal_status.return_value = None
    else:
        player._config_entry.options["standby_no_signal_seconds"] = 0
    await poll(player, 1005)
    assert handle.cancelled()
    assert player._standby_timer is None
    player._lg_display.set_standby_notice.assert_called_with()
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_text_appends_countdown_and_can_hide_without_disabling_timer(
    player,
):
    player._config_entry.options["standby_notice_text"] = "Eigene Nachricht"
    await poll(player, 1000)
    assert (
        player._lg_display.set_standby_notice.call_args.args[0]
        == "Eigene Nachricht ({seconds} s)"
    )
    timer = player._standby_timer
    player._config_entry.options["standby_notice_enabled"] = False
    await poll(player, 1005)
    assert player._standby_timer is timer
    player._lg_display.set_standby_notice.assert_called_with()
