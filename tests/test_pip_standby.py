"""Explicit PiP policy, independent of unreliable linked-player power states."""

from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.exceptions import HomeAssistantError


@pytest.fixture
def pip(player):
    player._lg_display.presentation_active = True
    player._lg_display.hdmi_context = dict(
        mode="pip", input_id=0x90, signal=False, view="pip_view"
    )
    player._lg_display.no_signal_views = {"dashboard": "Dashboard"}
    player._lg_display.async_select_view = AsyncMock()
    player._config_entry.options.update(
        pip_no_signal_action="view", pip_no_signal_seconds=30
    )
    return player


async def poll(player, now):
    with patch(
        "custom_components.av_companion.media_player.time.monotonic", return_value=now
    ):
        await player.async_update()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["keep", "view", "turn_off"])
async def test_pip_policy_after_continuous_signal_loss(pip, action):
    pip._config_entry.options["pip_no_signal_action"] = action
    for now in (1000, 1029):
        await poll(pip, now)
        pip._lg_display.async_select_view.assert_not_awaited()
        pip._lg_display.async_power_off.assert_not_awaited()
    await poll(pip, 1030)
    assert pip._lg_display.async_select_view.await_count == (action == "view")
    assert pip._lg_display.async_power_off.await_count == (action == "turn_off")
    pip._lg_display.async_set_input.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "signal",
        "unknown",
        "input",
        "view",
        "lock",
        "startup",
        "pending",
        "temporary",
        "stopping",
        "disabled",
        "power_off",
        "deleted_target",
    ],
)
async def test_pip_guards_and_final_revalidation(pip, change):
    await poll(pip, 1000)
    if change in {"signal", "unknown"}:
        pip._lg_display.hdmi_context["signal"] = True if change == "signal" else None
    elif change == "input":
        pip._lg_display.hdmi_context["input_id"] = 0x91
    elif change == "view":
        pip._lg_display.hdmi_context["view"] = "custom_pip"
    elif change == "lock":
        pip.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
    elif change == "startup":
        pip._startup_off_guard_until = 9999
    elif change == "pending":
        pip._pending_source_until = 9999
    elif change == "temporary":
        pip._presentation_active = True
    elif change == "stopping":
        pip._ha_stopping = True
    elif change == "disabled":
        pip._config_entry.options["pip_no_signal_seconds"] = 0
    elif change == "power_off":
        pip._lg_display.async_get_power_status.return_value = False
    elif change == "deleted_target":
        pip._lg_display.no_signal_views = {}
    await poll(pip, 1031)
    pip._lg_display.async_select_view.assert_not_awaited()
    pip._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["signal", "input", "view", "context", "lock"])
async def test_change_during_power_query_aborts_pip_action(pip, change):
    await poll(pip, 1000)

    async def power(**kw):
        if change == "signal":
            pip._lg_display.hdmi_context["signal"] = True
        elif change == "input":
            pip._lg_display.hdmi_context["input_id"] = 0x91
        elif change == "view":
            pip._lg_display.hdmi_context["view"] = "other_pip"
        elif change == "context":
            pip._lg_display.hdmi_context = None
        else:
            pip.hass.data["av_companion"]["test"]["sync_automation_enabled"] = False
        return True

    pip._lg_display.async_get_power_status.side_effect = power
    await poll(pip, 1031)
    pip._lg_display.async_select_view.assert_not_awaited()
    pip._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_view_switch_never_falls_back_to_power_off(pip):
    pip._lg_display.async_select_view.side_effect = HomeAssistantError("disconnected")
    await poll(pip, 1000)
    await poll(pip, 1031)
    pip._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_pip_shutdown_does_not_claim_success_or_cut_socket(pip):
    pip._config_entry.options["pip_no_signal_action"] = "turn_off"
    pip._lg_display.async_power_off.return_value = False
    await poll(pip, 1000)
    await poll(pip, 1031)
    assert pip._last_standby_reason is None
    assert pip.state != "off"
    pip.hass.services.async_call.assert_not_awaited()
