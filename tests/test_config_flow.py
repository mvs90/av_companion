from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from custom_components.av_companion.config_flow import AVOptionsFlow


@pytest.fixture
def flow():
    f = AVOptionsFlow(SimpleNamespace(entry_id="display", options={}))
    f.hass = Mock()
    f.hass.data = {}
    f.hass.states.get.return_value = None
    f.async_show_form = lambda **kw: kw
    f.async_create_entry = lambda **kw: kw
    return f


@pytest.mark.asyncio
async def test_standalone_form_has_no_none_entity_defaults(flow):
    form = await flow.async_step_init()
    values = form["data_schema"]({})
    assert "linked_media_player_entity_id" not in values
    assert values["standby_idle_seconds"] == 900
    assert values["standby_signal_check"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 1, 29, 86401, True, "900"])
async def test_invalid_standby_timeout(flow, value):
    with patch("homeassistant.helpers.entity_registry.async_get") as registry:
        registry.return_value.async_get.return_value = None
        form = await flow.async_step_init({"standby_idle_seconds": value})
    assert form["errors"]["standby_idle_seconds"] == "invalid_standby_timeout"


@pytest.mark.asyncio
async def test_self_link_is_rejected(flow):
    with patch("homeassistant.helpers.entity_registry.async_get") as registry:
        registry.return_value.async_get.return_value = SimpleNamespace(
            config_entry_id="display"
        )
        form = await flow.async_step_init(
            {"linked_media_player_entity_id": "media_player.display"}
        )
    assert form["errors"]["linked_media_player_entity_id"] == "self_reference"


@pytest.mark.asyncio
async def test_links_can_be_cleared_and_fallback_disabled(flow):
    flow._config_entry.options = {
        "linked_media_player_entity_id": "media_player.apple_tv"
    }
    with patch("homeassistant.helpers.entity_registry.async_get"):
        result = await flow.async_step_init({"standby_idle_seconds": 0})
    assert "linked_media_player_entity_id" not in result["data"]
    assert result["data"]["standby_idle_seconds"] == 0


@pytest.mark.asyncio
async def test_pip_defaults_translated_choices_and_available_non_hdmi_targets(flow):
    with patch(
        "custom_components.lg_rs232_ip.api.get_display_api",
        return_value=SimpleNamespace(
            no_signal_views={"dashboard": "Dashboard", "music": "Music"}
        ),
    ):
        form = await flow.async_step_init()
    values = form["data_schema"]({})
    assert values["pip_no_signal_action"] == "keep"
    assert values["pip_no_signal_seconds"] == 15
    assert values["pip_no_signal_view"] == "dashboard"
    choices = {str(k): v for k, v in form["data_schema"].schema.items()}
    assert (
        choices["pip_no_signal_action"].config["translation_key"]
        == "pip_no_signal_action"
    )
    assert choices["pip_no_signal_view"].config["options"] == [
        {"value": "dashboard", "label": "Dashboard"},
        {"value": "music", "label": "Music"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,key",
    [
        ({"pip_no_signal_action": "invalid"}, "pip_no_signal_action"),
        ({"pip_no_signal_seconds": 4}, "pip_no_signal_seconds"),
    ],
)
async def test_invalid_pip_policy_is_rejected(flow, values, key):
    with patch("homeassistant.helpers.entity_registry.async_get"):
        form = await flow.async_step_init(values)
    assert key in form["errors"]
