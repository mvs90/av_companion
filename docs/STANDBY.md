# Standby and display power


Apple TV can incorrectly remain `idle` after going to sleep, or report `off`/`standby` while HDMI playback is still active. This integration does not treat a repeated `idle` update or a polled active state as a reason to wake the display.

1. Player `off`/`standby` reports never trigger shutdown on their own. Both state events and polling use the same independent **HDMI signal query** (`sv <set-id> 02 ff`). A present signal protects the display, including when an active HDMI extractor keeps the link present. Unknown or unsupported signal status does not confirm player-off reports.
2. Continuous no-signal observations for **120 seconds**, followed by a fresh power/input/signal confirmation, trigger shutdown on the linked HDMI input even if the player remains stuck at `off`, `standby`, `idle` or `playing`. A new player event is not required. Signal return or unknown status resets signal-loss evidence. Checks are serialized with explicit controls and recheck the automation lock, startup/source/wake guards and presentation ownership after device queries.
3. If signal status is unsupported or unknown, **900 seconds of continuous `idle`** is a configurable fallback. An optional, fresh display power measurement can provide an additional 120-second idle/low-consumption confirmation. A detected signal blocks this fallback; `playing`, `paused`, `buffering`, `unknown` and `unavailable` do not count as idle.
4. Automatic shutdown cannot be reversed by polling stale Apple TV state. Explicit turn-on or a genuine active state transition can wake again. After an automatic shutdown, an `idle` transition alone stays blocked; start playback or use the combined TV's turn-on command.

Signal checking and both timeouts are configurable. Disabling signal checking or setting the no-signal timeout to 0 also disables automatic shutdown based on `off`/`standby`; an unverified player state is never used as a shortcut. Explicit user turn-off still works with a present or unknown signal. Set a timeout to **0** to disable that layer. The idle fallback is a heuristic: on a panel without signal-status support it can also shut down an Apple TV menu after 15 minutes. Increase or disable it if that is undesirable. Delays start at the first valid observation and can overshoot by a polling interval. Startup, source changes, power transitions and interrupted evidence reset the check. Restarting Home Assistant starts a new confirmation period.

The TV's attributes expose `signal_present`, `standby_candidate`, `standby_samples`, `last_standby_reason` and `automatic_wake_blocked`. Unknown/unsupported responses never mean “no signal.” LG's built-in No Signal Power Off (`fg`, often 15 minutes) can provide an additional hardware fallback on supported panels; enable it deliberately in the panel settings or the integration's Auto Sleep control.


Only the display may be on the controlled socket. Keep the FeinTech AX310 powered. [Wiring reference](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/devices/FEINTECH-AX310.md).
