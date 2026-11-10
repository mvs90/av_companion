"""Exercise real HAP characteristics with service dispatchers mocked, never devices."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.core import State
from pyhap.loader import get_loader

from custom_components.av_companion.homekit_volume import (
    HomeKitVolumeAdapter, level_to_percent, percent_to_level,
)


@pytest.mark.parametrize(('percent', 'level'), [(0, 0), (1, .01), (39, .39), (99, .99), (100, 1)])
def test_percent_normalization(percent, level):
    assert percent_to_level(percent) == level


@pytest.mark.parametrize('value', [None, True, False, '39', -1, 101, float('nan'), float('inf')])
def test_invalid_client_percent_is_rejected(value):
    assert percent_to_level(value) is None


@pytest.mark.parametrize(('level', 'percent'), [(0, 0), (.01, 1), (.39, 39), (.395, 40), (1, 100)])
def test_actual_level_feedback(level, percent):
    assert level_to_percent(level) == percent


@pytest.mark.parametrize('value', [None, True, '0.39', -1, 1.01, float('nan'), float('inf')])
def test_unknown_or_invalid_feedback_is_not_silently_zero(value):
    assert level_to_percent(value) is None


def accessory(entity_id='media_player.av'):
    char=get_loader().get_char('Volume')
    char.broker=Mock()  # HAP notifications remain in memory, never a network driver.
    return SimpleNamespace(
        entity_id=entity_id,
        char_volume=char,
        async_call_service=Mock(),
    )


@pytest.fixture
def setup(monkeypatch):
    states={'media_player.av': State('media_player.av', 'on', {'volume_level': .39})}
    target=accessory()
    callbacks=[]
    entry=SimpleNamespace(entry_id='hk', runtime_data=SimpleNamespace(
        homekit=SimpleNamespace(driver=SimpleNamespace(accessory=target))),
        async_on_state_change=Mock(side_effect=lambda f: callbacks.append(f) or Mock()))
    entries=[entry]
    hass=Mock()
    hass.config_entries.async_entries.side_effect=lambda domain: entries
    hass.states.get.side_effect=states.get
    state_unsub, timer_unsub = Mock(), Mock()
    monkeypatch.setattr('custom_components.av_companion.homekit_volume.async_track_state_change_event', lambda *args: state_unsub)
    monkeypatch.setattr('custom_components.av_companion.homekit_volume.async_track_time_interval', lambda *args: timer_unsub)
    adapter=HomeKitVolumeAdapter(hass, 'media_player.av')
    yield SimpleNamespace(adapter=adapter, hass=hass, states=states, target=target,
                          entries=entries, entry=entry, callbacks=callbacks,
                          state_unsub=state_unsub, timer_unsub=timer_unsub)
    adapter.stop()


def test_attaching_and_feedback_publish_no_device_commands(setup):
    s=setup
    original=s.target.char_volume.setter_callback
    s.adapter.start()
    assert s.target.char_volume.value == 39
    s.target.async_call_service.assert_not_called()
    s.states['media_player.av']=State('media_player.av', 'playing', {'volume_level': .65})
    s.adapter._changed()
    assert s.target.char_volume.value == 65
    s.target.async_call_service.assert_not_called()
    s.adapter.stop()
    assert s.target.char_volume.setter_callback is original
    s.state_unsub.assert_called_once()
    s.timer_unsub.assert_called_once()


@pytest.mark.parametrize(('percent', 'level'), [(0, 0), (1, .01), (39, .39), (100, 1)])
def test_client_write_uses_normalized_service_payload_only(setup, percent, level):
    s=setup
    s.adapter.start()
    s.target.char_volume.client_update_value(percent)
    s.target.async_call_service.assert_called_once_with(
        'media_player', 'volume_set', {'entity_id':'media_player.av', 'volume_level':level})
    s.hass.services.async_call.assert_not_called()


def test_ignores_other_players_and_accessories_without_absolute_volume(setup):
    s=setup
    other=accessory('media_player.other')
    other_original=other.char_volume.setter_callback
    unsupported=SimpleNamespace(entity_id='media_player.av', async_call_service=Mock())
    s.entry.runtime_data.homekit.driver.accessory=SimpleNamespace(
        accessories={2:s.target, 3:other, 4:unsupported})
    s.adapter.start()
    assert s.adapter.diagnostics['accessories']==1
    assert other.char_volume.setter_callback is other_original
    assert other.char_volume.value==0
    other.async_call_service.assert_not_called()
    unsupported.async_call_service.assert_not_called()


def test_homekit_reload_rebinds_new_instance_and_restores_old_callback(setup):
    s=setup
    old_original=s.target.char_volume.setter_callback
    s.adapter.start()
    stale_callback=s.target.char_volume.setter_callback
    new=accessory()
    s.entry.runtime_data.homekit.driver.accessory=new
    s.callbacks[0]()
    assert s.target.char_volume.setter_callback is old_original
    assert new.char_volume.value==39
    stale_callback(100)  # A detached accessory cannot dispatch through a stale closure.
    new.char_volume.client_update_value(1)
    new.async_call_service.assert_called_once_with(
        'media_player', 'volume_set', {'entity_id':'media_player.av', 'volume_level':.01})
    s.target.async_call_service.assert_not_called()


def test_unload_disarms_captured_callback_and_preserves_other_extensions(setup):
    s=setup
    s.adapter.start()
    captured=s.target.char_volume.setter_callback
    external=Mock()
    s.target.char_volume.setter_callback=external
    s.adapter.stop()
    assert s.target.char_volume.setter_callback is external
    captured(100)
    s.target.async_call_service.assert_not_called()
    assert s.adapter.diagnostics=={'active':False,'accessories':0}


def test_missing_unknown_and_unavailable_state_never_invents_a_volume(setup):
    s=setup
    s.adapter.start()
    for state in [None, State('media_player.av','unavailable',{'volume_level':0}),
                  State('media_player.av','on',{}), State('media_player.av','on',{'volume_level':float('nan')})]:
        s.states['media_player.av']=state
        s.adapter._changed()
        assert s.target.char_volume.value==39
    s.target.async_call_service.assert_not_called()


def test_invalid_client_write_resyncs_feedback_without_service(setup):
    s=setup
    s.adapter.start()
    s.target.char_volume.setter_callback(float('nan'))
    s.target.async_call_service.assert_not_called()
    assert s.target.char_volume.value==39


def test_homekit_loaded_later_is_discovered_and_unloaded_entry_is_removed(setup):
    s=setup
    s.entries.clear()
    s.adapter.start()
    assert s.adapter.diagnostics['accessories']==0
    s.entries.append(s.entry)
    s.adapter._changed()
    assert s.adapter.diagnostics['accessories']==1
    original=s.adapter._bindings[id(s.target)][1]
    s.entries.clear()
    s.adapter._changed()
    assert s.target.char_volume.setter_callback is original
    assert s.adapter.diagnostics['accessories']==0


def test_no_homekit_driver_is_harmless(setup):
    s=setup
    s.entry.runtime_data=None
    s.adapter.start()
    assert s.adapter.diagnostics['accessories']==0
    s.target.async_call_service.assert_not_called()
