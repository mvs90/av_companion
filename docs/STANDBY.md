# Standby and display power


Apple TV can incorrectly remain `idle` after going to sleep, or report `off`/`standby` while HDMI playback is still active. This integration does not treat a repeated `idle` update or a polled active state as a reason to wake the display.

1. Player `off`/`standby` reports never trigger shutdown on their own. Both state events and polling use the same independent **HDMI signal check** (hardware `sv <set-id> 02 ff` on native inputs; fresh embedded-video telemetry in the resident app with LG 2.33.0+). A present signal protects the display, including when an active HDMI extractor keeps the link present. Unknown or unsupported signal status does not confirm player-off reports.
2. Continuous no-signal observations for **15 seconds**, followed by a fresh power/input/signal confirmation, trigger shutdown on the linked HDMI input even if the player remains stuck at `off`, `standby`, `idle` or `playing`. A new player event is not required. Signal return or unknown status resets signal-loss evidence. Checks are serialized with explicit controls and recheck the automation lock, startup/source/wake guards and presentation ownership after device queries.
3. If signal status is unsupported or unknown, **900 seconds of continuous `idle`** is a configurable fallback. An optional, fresh display power measurement can provide an additional 120-second idle/low-consumption confirmation. A detected signal blocks this fallback; `playing`, `paused`, `buffering`, `unknown` and `unavailable` do not count as idle.
4. Automatic shutdown cannot be reversed by polling stale Apple TV state. Explicit turn-on or a genuine active state transition can wake again. After an automatic shutdown, an `idle` transition alone stays blocked; start playback or use the combined TV's turn-on command.

Signal checking and both timeouts are configurable. Disabling signal checking or setting the no-signal timeout to 0 also disables automatic shutdown based on `off`/`standby`; an unverified player state is never used as a shortcut. Explicit user turn-off still works with a present or unknown signal. Set a timeout to **0** to disable that layer. The idle fallback is a heuristic: on a panel without signal-status support it can also shut down an Apple TV menu after 15 minutes. Increase or disable it if that is undesirable. Delays start at the first valid observation and can overshoot by a polling interval. Startup, source changes, power transitions and interrupted evidence reset the check. Restarting Home Assistant starts a new confirmation period.

The **Alert Status** sensor reports `linked_power_state_conflict` after at least two observations spanning **120 seconds** of player `off`/`standby` plus a present HDMI signal. Monitoring remains active with the automation lock enabled, provided HDMI signal checking is enabled and the linked input is active. Details include the linked state, signal and input; the combined TV and diagnostics expose a `linked_power_state_conflict` boolean. Repeated unchanged observations do not create new alert-history entries.

This confirms a contradictory status, not a proven Apple TV API defect: an active HDMI extractor can also retain a signal. The warning therefore asks to check the player integration and lists both possible causes. It clears when the conflict is no longer confirmable (active player state, absent/unknown signal, another input, presentation, display off or unreachable), without claiming that the API itself was repaired. Startup and transitions restart confirmation. Monitoring does not override the automation lock.

The TV's attributes expose `signal_present`, `standby_candidate`, `standby_samples`, `last_standby_reason` and `automatic_wake_blocked`. Unknown/unsupported responses never mean “no signal.” LG's built-in No Signal Power Off (`fg`, often 15 minutes) can provide an additional hardware fallback on supported panels; enable it deliberately in the panel settings or the integration's Auto Sleep control.


Only the display may be on the controlled socket. Keep the FeinTech AX310 powered. [Wiring reference](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/devices/FEINTECH-AX310.md).

## PiP without HDMI signal

AV options provide **PiP without HDMI signal**, **PiP no-signal delay**, and **PiP fallback view without HDMI**. Default: keep the view. Optionally select a saved HDMI-free view (such as Dashboard or Mediaplayer) or turn the display off after confirmed continuous signal loss. The independent delay defaults to 15 seconds; 0 disables the action. A polling interval can add latency. The automation lock, source/startup guards and final fresh power/signal/context checks apply. Signal return or unknown data resets the timer.

This requires LG 2.33.0 and connected display app 1.22.1. It covers the fixed Dashboard PiP and custom persistent views containing HDMI, even without a linked player. The view fallback changes the in-app layout through the existing OSD-protected transaction. No hardware input switch is needed. Temporary notifications, timed views and external presentation ownership are excluded. Deleted/HDMI-containing targets produce an alert instead of shutting down as a fallback. Older LG versions retain protected PiP with no automatic action.

### Countdown message

Signal-loss delays accept 5–86400 seconds (0 disables), default **15 seconds** for fullscreen and PiP. A single deadline callback triggers final revalidation even when the regular polling interval is longer. Countdown text and visibility are configurable in AV options. `{seconds}` is replaced locally each second and `{action}` names the planned shutdown/view change. The app draws this notice over the current HDMI/PiP view without acquiring a presentation lease or changing input. Signal return, unknown signal, automation lock, temporary content, unload and lost connection cancel/hide it. Native HDMI without a connected app still observes the delay but cannot display this app overlay.
