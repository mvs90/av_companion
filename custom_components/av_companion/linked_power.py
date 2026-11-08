"""Distinguish an Apple TV power acknowledgement from lost HDMI/metadata."""
from homeassistant.helpers import entity_registry as er


def confirmed_power(hass, entity_id, on):
    if not entity_id or hass.config_entries is None:
        return False
    entity = er.async_get(hass).async_get(entity_id)
    if not entity or entity.platform != "apple_tv":
        return False
    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if not entry or entry.domain != "apple_tv":
        return False
    atv = getattr(getattr(entry, "runtime_data", None), "atv", None)
    if atv is None:
        return False
    from pyatv.const import FeatureName, FeatureState, PowerState
    from pyatv.exceptions import BlockedStateError
    try:
        return (atv.features.get_feature(FeatureName.PowerState).state is FeatureState.Available
                and atv.power.power_state is (PowerState.On if on else PowerState.Off))
    except BlockedStateError:
        return False
