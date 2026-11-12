"""Exercise the executable safety conditions of the optional standby blueprint."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest
import yaml


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor('!input', lambda loader, node: loader.construct_scalar(node))
BLUEPRINT = yaml.load(
    (Path(__file__).parents[1] / 'blueprints/automation/no_signal_apple_tv_standby.yaml').read_text(),
    Loader=Loader,
)


def context():
    def state(value, changed=0, **attrs):
        return SimpleNamespace(state=value, last_changed=changed, last_reported=599, attributes=attrs)
    return {
        'av': state('off', last_standby_reason='no_signal'),
        'display': state('off'), 'supply': state('off'),
        'source': state('paused', app_id='tv', media_title='episode'),
        'lock': state('off'), 'remote': state('on'),
    }


def render(phase, data):
    class States:
        def __getitem__(self, key):
            return data.get(key)
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals.update(
        states=States(),
        is_state=lambda key, value: data.get(key) is not None and data[key].state == value,
        as_timestamp=lambda value: value.timestamp() if isinstance(value, datetime) else float(value),
        now=lambda: datetime.fromtimestamp(600, timezone.utc),
    )
    template = (BLUEPRINT['conditions'][0]['value_template'] if phase == 'initial'
                else BLUEPRINT['actions'][3]['value_template'])
    return env.from_string(template).render(
        av_player='av', display_player='display', display_supply='supply',
        source_player='source', automation_lock='lock', source_remote='remote',
        trigger=SimpleNamespace(to_state=SimpleNamespace(last_changed=0)),
        source_fingerprint=['paused', 'tv', None, 'episode'], refresh_started=598,
    ).strip() == 'True'


@pytest.mark.parametrize('phase', ['initial', 'final'])
@pytest.mark.parametrize('change', [
    ('source', 'state', 'playing'), ('source', 'state', 'buffering'),
    ('source', 'state', 'unavailable'), ('source', 'state', 'off'),
    ('av', 'state', 'on'), ('display', 'state', 'on'), ('supply', 'state', 'on'),
    ('lock', 'state', 'on'), ('remote', 'state', 'unavailable'),
    ('av', 'last_changed', 1), ('display', 'last_changed', 1),
    ('supply', 'last_changed', 1),
])
def test_activity_disconnect_lock_or_power_change_prevents_suspend(phase, change):
    data = context()
    assert render(phase, data)
    key, attr, value = change
    setattr(data[key], attr, value)
    assert not render(phase, data)


@pytest.mark.parametrize('key', ['av', 'display', 'supply', 'source'])
@pytest.mark.parametrize('phase', ['initial', 'final'])
def test_missing_or_restored_state_is_not_evidence(phase, key):
    data = context()
    data[key].attributes['restored'] = True
    assert not render(phase, data)
    del data[key]
    assert not render(phase, data)


def test_reboot_or_recent_source_transition_cannot_be_suspended():
    data = context()
    data['source'].last_changed = 1
    assert not render('initial', data)


@pytest.mark.parametrize('reported', [597, 560])
def test_final_source_report_must_be_fresh_from_maintenance(reported):
    data = context()
    data['source'].last_reported = reported
    assert not render('final', data)


def test_new_content_or_shutdown_reason_cancels_standby():
    data = context()
    data['source'].attributes['media_title'] = 'different'
    assert not render('final', data)
    data = context()
    data['av'].attributes['last_standby_reason'] = 'idle'
    assert not render('initial', data)
    assert not render('final', data)


def test_trigger_is_future_power_off_only_and_commands_are_scoped():
    trigger = BLUEPRINT['triggers']
    assert len(trigger) == 1
    assert trigger[0]['from'] == 'on' and trigger[0]['to'] == 'off'
    assert trigger[0]['for'] == {'minutes': 5}
    actions = deepcopy(BLUEPRINT['actions'])
    assert [a['action'] for a in actions if 'action' in a] == [
        'av_companion.refresh_linked_connection', 'remote.send_command'
    ]
    assert actions[4]['data'] == {'command': 'suspend'}
    assert actions[-1]['continue_on_timeout'] is False
