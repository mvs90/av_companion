"""One source request must survive display/app boot; newer intent wins."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.parametrize(
    "source,method,arg",
    [
        ("HDMI 1", "async_set_input", 0x90),
        ("HDMI 2", "async_set_input", 0x91),
        ("HDMI 3", "async_set_input", 0x92),
        ("Dashboard", "async_select_view", "dashboard"),
        ("Dashboard PiP", "async_select_view", "pip_view"),
        ("Mediaplayer", "async_select_view", "media_view"),
        ("Custom", "async_select_view", "custom"),
        ("Sonos", "async_select_media_view", None),
        ("PiP Sonos", "async_select_view", "custom_pip"),
    ],
)
async def test_one_selection_waits_for_boot_and_applies_every_source(
    player, source, method, arg
):
    api = player._lg_display
    api.dashboard_available = api.pip_available = api.media_view_available = True
    api.view_sources = {
        "dashboard": "Dashboard",
        "pip_view": "Dashboard PiP",
        "media_view": "Mediaplayer",
        "custom": "Custom",
        "custom_pip": "Music PiP",
    }
    api.active_view = None
    api.dashboard_active = api.pip_active = api.media_view_active = False
    for name in [
        "async_select_view",
        "async_select_dashboard",
        "async_select_pip",
        "async_select_media_view",
    ]:
        setattr(api, name, AsyncMock())
    player._config_entry.options.update(
        linked_volume_media_player_entity_id="media_player.sonos",
        sonos_pip_view="custom_pip",
    )
    player._state = "off"
    supply_off = asyncio.create_task(asyncio.Event().wait())
    player._power_supply_off_task = supply_off
    entered, release = asyncio.Event(), asyncio.Event()

    async def boot(_):
        entered.set()
        await release.wait()
        assert player._power_supply_off_task is None

    player._async_ensure_display_on_after_power_restore = AsyncMock(side_effect=boot)
    task = asyncio.create_task(player.async_select_source(source))
    await asyncio.wait_for(entered.wait(), 2)
    assert supply_off.cancelling()
    assert player.source == source
    assert player.available
    assert player.extra_state_attributes["source_selection_pending"]
    assert player.extra_state_attributes["source"] == source
    getattr(api, method).assert_not_awaited()
    release.set()
    await task
    if arg is None:
        getattr(api, method).assert_awaited_once_with()
    else:
        getattr(api, method).assert_awaited_once_with(arg)
    assert not player.extra_state_attributes["source_selection_pending"]
    assert player._source == source
    assert player._state == "on"
    player._async_call_linked_service.assert_not_awaited()
    await asyncio.gather(supply_off, return_exceptions=True)


@pytest.mark.parametrize("replacement", ["HDMI 3", "off", "on", "stopping"])
async def test_newer_intent_replaces_selection_during_power_start(player, replacement):
    entered, release = asyncio.Event(), asyncio.Event()

    async def boot(_):
        entered.set()
        await release.wait()

    player._async_ensure_display_on_after_power_restore = AsyncMock(side_effect=boot)
    first = asyncio.create_task(player.async_select_source("HDMI 2"))
    await asyncio.wait_for(entered.wait(), 2)
    if replacement == "stopping":
        player._ha_stopping = True
        second = None
    elif replacement == "off":
        second = asyncio.create_task(player.async_turn_off())
    elif replacement == "on":
        second = asyncio.create_task(player.async_turn_on())
    else:
        second = asyncio.create_task(player.async_select_source(replacement))
    await asyncio.sleep(0)
    release.set()
    await first
    if second:
        await second
    if replacement == "HDMI 3":
        player._lg_display.async_set_input.assert_awaited_once_with(0x92)
        assert player._source == replacement
    else:
        player._lg_display.async_set_input.assert_not_awaited()
    assert not player._source_selection_pending


async def test_invalid_source_does_not_cancel_supply_shutdown_or_wake(player):
    player._cancel_power_supply_off_task = Mock()
    with pytest.raises(HomeAssistantError, match="Unknown source"):
        await player.async_select_source("not configured")
    player._cancel_power_supply_off_task.assert_not_called()
    player._lg_display.async_get_power_status.assert_not_awaited()


async def test_input_failure_is_reported_without_claiming_selected_source(player):
    before = player.source
    player._lg_display.async_set_input.return_value = False
    with pytest.raises(HomeAssistantError, match="confirm source"):
        await player.async_select_source("HDMI 2")
    assert player.source == before
    assert not player._source_selection_pending
    player._async_call_linked_service.assert_not_awaited()


async def test_player_app_never_trusts_cached_input_after_boot(player):
    player._linked_source_list = ["Netflix"]
    player._current_input_id = player._linked_input_id
    player._lg_display.active_view = None
    player._lg_display.dashboard_active = player._lg_display.pip_active = (
        player._lg_display.media_view_active
    ) = False
    await player.async_select_source("Netflix")
    player._lg_display.async_set_input.assert_awaited_once_with(player._linked_input_id)
    player._async_call_linked_service.assert_awaited_once_with(
        "select_source", source="Netflix"
    )


async def test_old_api_lost_power_ack_is_confirmed_without_second_selection(player):
    player._state = "off"
    player._lg_display.async_get_power_status.side_effect = [False, True, True]
    player._lg_display.async_power_on.return_value = False
    with patch(
        "custom_components.av_companion.media_player.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        await player.async_select_source("HDMI 2")
    player._lg_display.async_power_on.assert_awaited_once()
    player._lg_display.async_set_input.assert_awaited_once_with(0x91)


async def test_power_timeout_does_not_select_any_input(player):
    now = [0.0]

    async def advance(seconds):
        now[0] += seconds

    player._config_entry.options["display_wake_timeout"] = 6
    player._lg_display.async_get_power_status.return_value = None
    player._lg_display.async_power_on.return_value = False
    with (
        patch(
            "custom_components.av_companion.media_player.time.monotonic",
            side_effect=lambda: now[0],
        ),
        patch(
            "custom_components.av_companion.media_player.asyncio.sleep",
            side_effect=advance,
        ),
    ):
        with pytest.raises(HomeAssistantError, match="did not become ready"):
            await player.async_select_source("HDMI 2")
    assert now[0] == 6
    assert player._lg_display.async_power_on.await_count == 2
    player._lg_display.async_set_input.assert_not_awaited()
    assert not player._source_selection_pending


async def test_real_power_wait_stops_retrying_when_new_off_supersedes_it(player):
    entered, release = asyncio.Event(), asyncio.Event()

    async def start():
        entered.set()
        await release.wait()
        return False

    player._lg_display.async_get_power_status.return_value = False
    player._lg_display.async_power_on.side_effect = start
    first = asyncio.create_task(player.async_select_source("HDMI 2"))
    await asyncio.wait_for(entered.wait(), 2)
    off = asyncio.create_task(player.async_turn_off())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, off)
    player._lg_display.async_power_on.assert_awaited_once()
    player._lg_display.async_set_input.assert_not_awaited()
    assert not player._source_selection_pending
