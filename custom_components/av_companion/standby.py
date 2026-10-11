"""Conservative, monotonic standby evidence independent of Home Assistant."""

from dataclasses import dataclass


@dataclass
class StandbyGuard:
    """Require continuous evidence over time and at least two observations."""

    reason: str | None = None
    since: float | None = None
    samples: int = 0
    idle_since: float | None = None
    idle_samples: int = 0

    def reset(self) -> None:
        self.reason = None
        self.since = None
        self.samples = 0
        self.idle_since = None
        self.idle_samples = 0

    def observe(
        self,
        now: float,
        state: str | None,
        signal: bool | None,
        *,
        eligible: bool,
        no_signal_seconds: int = 15,
        idle_seconds: int = 900,
        low_power: bool = False,
    ) -> str | None:
        if eligible and state == "idle" and signal is not True:
            if self.idle_since is None:
                self.idle_since = now
            self.idle_samples += 1
        else:
            self.idle_since = None
            self.idle_samples = 0
        reason = None
        delay = 0
        if eligible:
            # Player power reports can be stale in either direction. Even an
            # explicit off/standby event needs independent HDMI-loss evidence.
            if signal is False and no_signal_seconds > 0:
                reason, delay = "no_signal", no_signal_seconds
            elif state == "idle" and signal is None and low_power:
                reason, delay = "idle_low_power", 120
            elif state == "idle" and signal is None and idle_seconds > 0:
                reason, delay = "idle_timeout", idle_seconds
        if reason is None:
            self.reset()
            return None
        if reason != self.reason:
            self.reason = reason
            self.since = self.idle_since if reason == "idle_timeout" else now
            self.samples = self.idle_samples if reason == "idle_timeout" else 1
        else:
            self.samples += 1
        if self.samples >= 2 and self.since is not None and now - self.since >= delay:
            return reason
        return None


@dataclass
class PowerStateConflict:
    """Confirm a contradictory player-off/HDMI-present observation, not its cause."""

    since: float | None = None
    samples: int = 0
    confirmed: bool = False

    def reset(self) -> None:
        self.since = None
        self.samples = 0
        self.confirmed = False

    def observe(
        self, now: float, state: str | None, signal: bool | None, *, eligible: bool
    ) -> bool:
        if not eligible or state not in {"off", "standby"} or signal is not True:
            self.reset()
            return False
        if self.since is None:
            self.since = now
        self.samples += 1
        self.confirmed = self.samples >= 2 and now - self.since >= 120
        return self.confirmed
