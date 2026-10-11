"""One deadline callback and a locally rendered countdown; no per-second I/O."""

import asyncio
import time


def default_notice(hass):
    return (
        "Kein HDMI-Signal von {player}. {action} in {seconds} Sekunden."
        if getattr(hass.config, "language", "en") == "de"
        else "No HDMI signal from {player}. {action} in {seconds} seconds."
    )


class StandbyCountdown:
    def _init_standby_countdown(self):
        self._standby_timer = None
        self._standby_deadline = None

    def _cancel_standby_countdown(self):
        if self._standby_timer is not None:
            self._standby_timer.cancel()
        self._standby_timer = self._standby_deadline = None
        setter = getattr(self._lg_display, "set_standby_notice", None)
        if callable(setter):
            setter()

    def _sync_standby_countdown(self):
        options = self._config_entry.options
        pip = self._pip_signal_context()
        guard = self._pip_standby_guard if pip else self._standby_guard
        eligible = self._pip_standby_eligible() if pip else self._standby_eligible()
        action = options.get("pip_no_signal_action", "keep") if pip else "turn_off"
        delay = options.get(
            "pip_no_signal_seconds" if pip else "standby_no_signal_seconds", 15
        )
        if (
            not eligible
            or guard.reason != "no_signal"
            or guard.since is None
            or delay <= 0
            or action not in {"view", "turn_off"}
        ):
            if not eligible:
                guard.reset()
            self._cancel_standby_countdown()
            return
        deadline = guard.since + delay
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self._cancel_standby_countdown()
            return
        if self._standby_deadline != deadline:
            self._cancel_standby_countdown()
            self._standby_deadline = deadline

            def due():
                self._standby_timer = self._standby_deadline = None
                if not self._ha_stopping:
                    self.async_schedule_update_ha_state(True)

            self._standby_timer = asyncio.get_running_loop().call_later(remaining, due)
        setter = getattr(self._lg_display, "set_standby_notice", None)
        if not callable(setter):
            return
        if not options.get("standby_notice_enabled", True):
            setter()
            return
        de = getattr(self.hass.config, "language", "en") == "de"
        label = (
            ("Ansichtswechsel" if de else "Changing view")
            if action == "view"
            else ("Ausschalten" if de else "Turning off")
        )
        message = options.get("standby_notice_text") or default_notice(self.hass)
        # Upgrade only the previous built-in default, preserving custom text.
        if message in (
            "Kein HDMI-Signal. {action} in {seconds} Sekunden.",
            "No HDMI signal. {action} in {seconds} seconds.",
        ):
            message = default_notice(self.hass)
        message = message.replace("{player}", self._signal_player_name)
        message = message.replace("{action}", label)[:250]
        if "{seconds}" not in message:
            message += " ({seconds} s)"
        setter(message, deadline)
