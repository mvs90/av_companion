# Changelog

## 1.6.3

- Maintenance release verified with LG Professional Display 2.33.2 and Display Studio 1.2.2 on Home Assistant 2025.3.4 and 2026.9.4.
- Source selection, audio routing and power coordination are unchanged.

## 1.6.2

- Make a single source selection cancel pending socket-off immediately and retain its target across display startup. Expose `source_selection_pending` and keep the requested source visible while it is being applied; newer source/on/off commands supersede older intent.
- Read back a lost power-on acknowledgement before retrying. Never silently claim a failed HDMI or linked-app selection, and never trust a cached HDMI input from the previous power cycle when launching a player app.
- With LG Professional Display 2.33.1, source selection also waits for resident SI readiness through the corrected public API instead of falling back to native HDMI during app boot. Existing audio-routing and presentation protections remain.

## 1.6.1

- Recover a recently disconnected player after automatic signal-loss standby, including `off → unknown → idle` during an Apple TV reboot. Serialize genuine wake events behind an in-flight off command; cancel superseded intent on explicit controls, lock, stop, changed playback or protected presentations. Startup/attribute-only/stale polling cannot wake the display.
- Automatic confirmed no-signal shutdown no longer suspends a rebooting player or forwards a duplicate off on subsequent polls. Keep explicit user shutdown and unknown-signal protections.
- Independently fall back to the current app name and App Store icon when title/artwork are absent. Include the reported playback state when metadata is incomplete, preserve real artists and immediately prefer real metadata when it returns. Artwork follows the audible player, including Sonos TV/music routing.
- Fetch icons on demand by exact public bundle ID, cache up to 32 small icons across restarts, and use a neutral app badge when unavailable. No viewing titles, account data or device credentials leave HA.

## 1.6.0

- Add Sonos and PiP Sonos sources, route music metadata, artwork and transport to the sound-system player across HDMI and persistent app views; use Apple TV metadata for Sonos TV audio. Preserve pause/resume routing and authenticated artwork retrieval.
- Restrict optional TV-audio selection to explicit HDMI choices. Default remains disabled for Sonos TV Autoplay; power-on and all app views leave audio unchanged. Audio playback does not change the LG input.
- Include concrete player names in alerts and `{player}` in editable countdowns. Preserve custom messages and stable alert codes.
- Protect ongoing Sonos music from HDMI-only no-signal shutdown without bypassing explicit PiP policies.

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
