"""Sanitized AV-only diagnostics."""

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    data = hass.data[DOMAIN][entry.entry_id]
    player = data.get("media_player")
    return {
        "linked_connection_health": player._linked_connection_health if player else {},
        "homekit_volume": (
            player._homekit_volume_adapter.diagnostics
            if player and player._homekit_volume_adapter is not None
            else {"active": False, "accessories": 0}
        ),
        "lg_ready": data["lg_display"].ready,
        "presentation_active": player._any_presentation_active if player else False,
        "standby_reason": player._last_standby_reason if player else None,
        "signal_present": player._signal_present if player else None,
        "linked_power_state_conflict": player._power_state_conflict.confirmed
        if player
        else False,
    }
