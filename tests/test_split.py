"""Behavior at the boundary between the two independently loaded integrations."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.components.media_player import MediaPlayerState


@pytest.mark.asyncio
async def test_native_presentation_hides_foreign_metadata_and_shutdown(player):
    player._lg_display.presentation_active = True
    assert player.state == MediaPlayerState.ON
    assert player.media_title is None
    assert player._playback_target is None
    assert player.extra_state_attributes["presentation_active"]
    await player._async_check_standby()
    player._lg_display.async_power_off.assert_not_awaited()
    player._lg_display.async_clear_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_off_cancels_native_content_before_power_off(player):
    order = []

    async def clear():
        order.append("clear")

    async def off():
        order.append("off")
        return True

    player._lg_display.async_clear_content.side_effect = clear
    player._lg_display.async_power_off.side_effect = off
    await player.async_turn_off()
    assert order == ["clear", "off"]


@pytest.mark.asyncio
async def test_missing_base_is_unavailable_and_does_not_cut_supply(player):
    player._lg_display.ready = False
    player._lg_display.async_get_power_status.return_value = None
    assert not player.available
    await player.async_update()
    player._lg_display.async_power_off.assert_not_awaited()
    player.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_volume_only_partial_configuration(player):
    from homeassistant.core import State

    player._config_entry.options = {
        "linked_volume_media_player_entity_id": "media_player.sound",
        "linked_volume_sync_mode": "always",
    }
    player._test_states["media_player.sound"] = State(
        "media_player.sound", "on", {"supported_features": 4}
    )
    await player.async_set_volume_level(0.42)
    call = player.hass.services.async_call.call_args
    assert call.args[:2] == ("media_player", "volume_set")
    assert call.args[2]["entity_id"] == "media_player.sound"


@pytest.mark.asyncio
async def test_rename_rewrites_optional_entity_reference(player):
    from custom_components.av_companion import async_setup_entry

    entry = SimpleNamespace(
        entry_id="new",
        title="AV",
        data={"lg_entry_id": "display"},
        options={"linked_media_player_entity_id": "media_player.old"},
        async_on_unload=Mock(),
        add_update_listener=Mock(),
    )
    player.hass.data = {}
    player.hass.config_entries.async_forward_entry_setups = AsyncMock()
    with patch(
        "custom_components.av_companion.get_display_api",
        return_value=player._lg_display,
    ):
        await async_setup_entry(player.hass, entry)
    callback = player.hass.bus.async_listen.call_args.args[1]
    callback(
        SimpleNamespace(
            data={"old_entity_id": "media_player.old", "entity_id": "media_player.new"}
        )
    )
    player.hass.config_entries.async_update_entry.assert_called_once_with(
        entry, options={"linked_media_player_entity_id": "media_player.new"}
    )


@pytest.mark.asyncio
async def test_lg_status_event_stays_on_ha_event_loop(tmp_path, player):
    import threading
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(str(tmp_path))
    player.hass = hass
    player._config_entry = SimpleNamespace(
        entry_id="test", data={"lg_entry_id": "lg"}, options={}
    )
    hass.data["av_companion"] = {"test": {"sync_automation_enabled": True}}
    observed = []
    player.async_schedule_update_ha_state = lambda *args: observed.append(
        threading.get_ident()
    )
    player.async_on_remove = Mock()
    await player.async_added_to_hass()
    observed.clear()
    try:
        hass.bus.async_fire("lg_rs232_ip_status", {"entry_id": "other"})
        await hass.async_block_till_done()
        assert observed == []
        hass.bus.async_fire("lg_rs232_ip_status", {"entry_id": "lg"})
        await hass.async_block_till_done()
        assert observed == [threading.get_ident()]
    finally:
        await player.async_will_remove_from_hass()
        for call in player.async_on_remove.call_args_list:
            call.args[0]()
        await hass.async_stop(force=True)
