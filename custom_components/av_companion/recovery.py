"""Remember runtime reconnects without turning stale HA state into wake intent."""

import time


class RestartRecovery:
    def _init_recovery(self):
        self._auto_standby_until = 0.0
        self._linked_reconnect_until = 0.0
        self._wake_generation = 0

    def _clear_restart_recovery(self):
        self._auto_standby_until = 0.0
        self._linked_reconnect_until = 0.0
        self._wake_generation += 1

    def _observe_linked_reconnect(self, old, new):
        now = time.monotonic()
        if (
            self._sync_automation_enabled
            and now >= self._startup_off_guard_until
            and old is not None
            and not old.attributes.get("restored")
            and not new.attributes.get("restored")
            and new.state in {"unknown", "unavailable"}
            and old.state not in {"unknown", "unavailable"}
            and (
                (self._state != "off" and not self._standby_latched)
                or now < self._auto_standby_until
            )
        ):
            # One bounded reconnect window, never extended by repeated errors.
            self._linked_reconnect_until = now + 180
        return now < self._linked_reconnect_until

    async def _async_linked_wake(self, event_state):
        generation = self._wake_generation
        # Explicit off keeps its echo suppression. Only automatic signal-loss
        # standby may be undone by a genuine return during the off transaction.
        if (
            self._linked_power_on_suppressed
            and time.monotonic() >= self._auto_standby_until
        ):
            return
        async with self._control_lock:
            current = self.hass.states.get(self._linked_entity_id)
            if (
                generation != self._wake_generation
                or self._ha_stopping
                or not self._sync_automation_enabled
                or self._any_presentation_active
                or current is None
                or current.state not in {"on", "playing", "paused", "idle", "buffering"}
                or current.attributes.get("restored")
                # A later event supersedes this queued intent.
                or current.last_changed != event_state.last_changed
            ):
                return
            power = await self._lg_display.async_get_power_status(use_cache=False)
            latest = self.hass.states.get(self._linked_entity_id)
            if (
                generation != self._wake_generation
                or self._ha_stopping
                or not self._sync_automation_enabled
                or self._any_presentation_active
                or latest is None
                or latest.last_changed != current.last_changed
                or latest.state != current.state
                or latest.attributes.get("restored")
            ):
                return
            self._clear_restart_recovery()
            self._standby_latched = False
            self._standby_guard.reset()
            self._cancel_power_supply_off_task()
            self._suppress_linked_power_on_until = 0.0
            if power is not True:
                self._state = "on"
                self._pending_state = "on"
                self._pending_state_until = (
                    time.monotonic() + self._pending_power_seconds
                )
                self._start_display_wake_task("linked playback/reconnect event")
