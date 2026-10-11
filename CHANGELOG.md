# Changelog

## 1.5.0

- Default to configurable 15-second no-signal delays for fullscreen and PiP (5–86400 seconds; 0 disables). Add an editable countdown notice in the connected app, rendered locally each second without input switching. One deadline callback rechecks safety conditions independently of regular polling.

- With LG Professional Display 2.33.0 or later, correctly detect loss of the embedded HDMI signal in app fullscreen instead of treating the active SI app as HDMI video. Freshness and input/request correlation are enforced by LG; unknown values cannot authorize shutdown.
- Add an independent persistent-PiP policy: keep the current view (default), switch to a saved view without HDMI, or turn the display off. Configure the delay (default 15 seconds, 0 disables) and target in AV options. Keep normal dashboards/media views and temporary notifications protected. Honour automation lock and revalidate context/power/signal before acting.

- Show a confirmed player-off/HDMI-present contradiction in Alert Status after 120 seconds, including with power automation locked. Expose `linked_power_state_conflict` for automations/diagnostics, deduplicate repeated warnings and clear them when no longer confirmable. Distinguish an observed status conflict from a proven player API failure, since HDMI extractors may retain a signal.

- Prevent false Apple TV `off`/`standby` reports from switching off a display with an active HDMI signal. State events and polling now share continuous no-signal confirmation (default 15 seconds); unknown signal status never confirms a player-off report.
- Still shut down on sustained, freshly confirmed HDMI loss while the player remains stuck off. Returning signal resets evidence; disabling signal checking or the no-signal timer does not fall back to trusting player-off reports. Explicit user shutdown remains available.
- Serialize standby checks with controls and recheck automation lock, source, startup, wake and presentation protection after I/O. Update the reported signal to the final confirmation result.
- Expand unit regressions and the existing Docker acceptance harness for false-off events, stuck-off polling, unknown/returning signal and confirmed display-before-socket shutdown.

## 1.4.1

- Classify each combined AV system as a device integration so AV Companion appears in the normal Integrations overview and Add integration flow. It was previously categorized as a helper.
- Preserve existing config entries, device/entity IDs and settings. Restart Home Assistant after updating; no reconfiguration is required.

## 1.4.0

- Consume LG 2.14 dynamic Studio sources through the optional public API v1 extension. Expose fixed Dashboard, Dashboard PiP and Mediaplayer plus each saved custom view on the combined player and HomeKit source list.
- Route stable view IDs, follow direct LG selection and renames, avoid source-name collisions, leave custom views for linked HDMI selections and preserve standby guards. Remain compatible with earlier LG API v1 installations.

## 1.3.0

- Expose the optional LG 2.12 Mediaplayer source on the combined player and its HomeKit input list. Select it through public API v1 without starting a linked player.
- Follow direct LG music-view selection and leave the view when choosing a linked HDMI source, even when the cached input already matches. Preserve presentation/standby guards and compatibility with older LG API v1 installations.

## 1.2.0

- Expose the optional LG 2.10 PiP source alongside Dashboard, including unique labels and direct-source reflection.
- Select the persistent LG PiP view through the public API after supply/display readiness checks, without waking the linked player. Linked player source selection leaves PiP even when the cached HDMI input matches.
- Retain compatibility with older LG API v1 versions where PiP is unavailable. Persistent-view standby protection remains provided by the LG public API.

## 1.1.0

- Expose the optional LG Dashboard source in the combined AV media player's source list, including unique naming when an input/app uses the same label.
- Route selection through the LG public API after the usual display/supply wake checks, without waking a linked television player. Linked app selection explicitly leaves Dashboard even with a matching cached HDMI input.
- Follow Dashboard selection made directly on the LG entity and preserve automatic standby protection. Requires LG 2.7.0 for Dashboard; older LG API v1 installations retain their existing behavior.

## 1.0.0

Initial independent AV extension for LG Professional Display 2.0/API v1. Optional player, remote, sound system, socket and power-sensor links; combined TV/HomeKit routing; staged standby confirmation; temporary content, announcements and native LG delegation. Includes presentation ownership, guarded socket cuts, entity rename handling and isolated Docker acceptance tests. No migration required.
