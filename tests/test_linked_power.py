from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from homeassistant.core import State
from pyatv.const import FeatureState, PowerState
from custom_components.av_companion.linked_power import confirmed_power


def event(player, old='playing', new='off', **attrs):
    before=State('media_player.apple_tv',old)
    after=State('media_player.apple_tv',new,attrs)
    player._test_states[after.entity_id]=after
    return SimpleNamespace(data={'old_state':before,'new_state':after})


@pytest.mark.asyncio
async def test_confirmed_power_off_is_immediate_and_on_wakes_without_countdown(player):
    player._lg_display.async_get_signal_status.return_value=True
    with patch('custom_components.av_companion.linked_power.confirmed_power',return_value=True):
        await player._async_handle_linked_state_change(event(player))
        player._lg_display.async_power_off.assert_awaited_once()
        player._async_call_linked_service.assert_not_awaited()
        player._lg_display.async_get_signal_status.assert_not_awaited()
        assert player._last_standby_reason=='linked_power_off'
        assert player._linked_off_confirmed
        player._lg_display.async_get_power_status.return_value=False
        await player._async_handle_linked_state_change(event(player,'off','idle'))
        player._start_display_wake_task.assert_called_once()
        assert not player._linked_off_confirmed


@pytest.mark.asyncio
@pytest.mark.parametrize('guard',['unconfirmed','other_input','restored','unavailable','baseline','disabled','stopping'])
async def test_only_trusted_power_transition_bypasses_signal_delay(player,guard):
    e=event(player)
    if guard=='other_input':player._current_input_id=0x91
    if guard=='restored':e=event(player,restored=True)
    if guard=='unavailable':e=event(player,'unavailable')
    if guard=='baseline':e.data['old_state']=None
    if guard=='disabled':player.hass.data['av_companion']['test']['sync_automation_enabled']=False
    if guard=='stopping':player._ha_stopping=True
    with patch('custom_components.av_companion.linked_power.confirmed_power',return_value=guard!='unconfirmed'):
        await player._async_handle_linked_state_change(e)
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_wake_supersedes_queued_power_off(player):
    e=event(player)
    class Lock:
        async def __aenter__(self):event(player,'off','playing')
        async def __aexit__(self,*args):pass
    player._control_lock=Lock()
    with patch('custom_components.av_companion.linked_power.confirmed_power',return_value=True):
        assert not await player._async_confirmed_linked_off(e)
    player._lg_display.async_power_off.assert_not_awaited()


@pytest.mark.parametrize('feature,power,expected',[(FeatureState.Available,PowerState.Off,True),(FeatureState.Unavailable,PowerState.Off,False),(FeatureState.Available,PowerState.Unknown,False),(FeatureState.Available,PowerState.On,False)])
def test_requires_connected_apple_tv_power_protocol(feature,power,expected):
    registry=Mock();registry.async_get.return_value=SimpleNamespace(platform='apple_tv',config_entry_id='apple')
    atv=SimpleNamespace(features=SimpleNamespace(get_feature=lambda _:SimpleNamespace(state=feature)),power=SimpleNamespace(power_state=power))
    entry=SimpleNamespace(domain='apple_tv',runtime_data=SimpleNamespace(atv=atv))
    hass=SimpleNamespace(config_entries=SimpleNamespace(async_get_entry=lambda _:entry))
    with patch('custom_components.av_companion.linked_power.er.async_get',return_value=registry):
        assert confirmed_power(hass,'media_player.apple_tv',False) is expected
        entry.runtime_data.atv=None
        assert not confirmed_power(hass,'media_player.apple_tv',False)
