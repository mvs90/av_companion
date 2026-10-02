from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from custom_components.av_companion.config_flow import AVOptionsFlow


@pytest.fixture
def flow():
    f = AVOptionsFlow(SimpleNamespace(entry_id="display", options={}))
    f.hass = Mock()
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
