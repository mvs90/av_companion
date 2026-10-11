# Split release acceptance — 2026-10-02

## 1.6.1 restart recovery and app metadata — 2026-10-12

**290 tests pass** on HA 2026.9.4/Python 3.14, HA 2025.3.4/Python 3.13, and the minimum LG 2.0 API. Added coverage includes observed runtime reconnect before/after automatic shutdown, queued wake during an in-flight off, explicit-off supersession, startup/restored/expired/locked/stop/presentation guards, later inactive state, attribute updates during power I/O, duplicate-off prevention, pending wake polling, independent title/artwork combinations, reported status, Sonos target changes, late logo responses, real-cover recovery and bounded persistent/negative artwork caching.

Seven focused acceptance checks passed in the **existing HA 2026.9.4 Docker instance** using actual config flows, registered fixture services and a TCP LG simulator: Netflix app name/status and real 256 px App Store icon through HA's authenticated artwork proxy; immediate replacement by a real title/cover; honest idle status; 15-second no-signal shutdown without suspending the rebooting source; `off → unknown → idle` restoring socket/display during suppression; a playing event during a two-second OFF acknowledgement; and explicit-off echo protection. The retrieved Netflix icon was visually inspected. Temporary lab entries and the fixture were removed afterward.

The user's recorded reboot sequence was player off at 23:48:44, display off at 23:49:11, then player unknown → idle at 23:49:40 (local time, 2026-10-11). This exact event pattern is now covered. The real Apple TV was **not rebooted again** for acceptance. Read-only verification after installation confirmed real programme title/artwork and playing state still flow through the combined AV entity, Sonos remains on TV audio, the resident app displays HDMI 1 fullscreen and Alert Status is OK. LG 2.33.0, Studio 1.4.0 and their saved settings remain unchanged.

## 1.6.0 audio routing and named notices — 2026-10-11

226 tests pass on HA 2026.9.4/Python 3.14. The same suite is exercised on HA 2025.3.4 and against the minimum LG 2.0 API. Coverage adds Sonos music/TV/HTA-stream/paused/unavailable across HDMI and every persistent view; metadata, authenticated art, controls, pause/resume, audio play_media without input switching, optional TV selection on HDMI only, independent PiP view selection/deletion, source collisions, named alerts/countdowns, and presentation power protection with live Apple TV metadata.

On the existing HA 2026.9.4 Docker instance, the actual Wohnzimmer Sonos played an existing music favorite under a saved/restored snapshot and mute. **Sonos, PiP Sonos, Dashboard, Mediaplayer and HDMI 1** all retained the music source, routed current title/artwork through the combined player, and returned a valid JPEG from its camera-independent artwork proxy. Pause/resume reached Sonos; restoring TV audio immediately selected Apple TV metadata. Display scene telemetry confirmed each view. Sonos TV source, 19% volume, mute-off, HDMI 1 and the previous automation lock were restored.

The observed Apple TV fault was traced to a discovery helper still running in an obsolete Docker network namespace after HA recreation. Sonos event callbacks were bound only to loopback by a temporary away-from-home override. Recreating the **existing** HA and discovery services together using the original LAN port binding restored discovery; Apple TV changed from false off to playing and Sonos callbacks resumed. This repairs this local installation; it is not a claim to repair every upstream tvOS/pyatv defect. The HDMI-confirmation safety logic remains active.

For Docker Desktop deployments, the Sonos advertised host must be reachable from the speakers on the callback port. Shared-network-namespace discovery helpers must be recreated with their HA service after container replacement. See [HA Sonos network requirements](https://www.home-assistant.io/integrations/sonos/#network-requirements) and [HA Apple TV](https://www.home-assistant.io/integrations/apple_tv/).

## 1.5.0 app HDMI signal, PiP policy and countdown — 2026-10-11

**178 AV tests pass on HA 2025.3.4/Python 3.13 and HA 2026.9.4/Python 3.14.** The suite also passes against LG API v1 from LG 2.0.0. New coverage includes PiP keep/view/off, signal interruption, changed input/view, final power revalidation, automation locks, temporary presentations, missing target views, failed writes, editable notices, cancellation and a single deadline callback independent of normal polling.

The existing **unifi-air-quality-ha-dev / HA 2026.9.4** container and physical **75UH5F-HJ / 04.13.50** verified the corrected signal path: raw SI activity previously reported present while the app's actual HDMI plane reported no signal. Input Signal and AV now report that embedded HDMI loss, and the false status-conflict warning clears. Persistent PiP stayed on with the default keep policy, switched to Dashboard after a configured 30-second loss without leaving the resident app, and powered off with the turn-off policy. Fullscreen HDMI powered off after the configured 120-second loss window; later a 15-second deadline test powered off roughly 17 seconds after the first no-signal observation, without forced entity updates (device commands add a short delay).

A fresh native device capture on the unused HDMI 2 input visibly confirmed “Kein HDMI-Signal. Ausschalten in 2 Sekunden.” before shutdown. The 15-second deadline required no forced HA entity polling. A separate HDMI-1 run with a present signal stayed on beyond the deadline and never displayed a shutdown candidate. Camera preview snapshots can be cached, so the visual acceptance used a fresh native capture.

The local user's fullscreen/PiP delays are now **15 seconds**, as explicitly requested; PiP defaults to keep. Other original AV links/options remain. No new HA instance or permanent test integration was created. Studio 1.4.0, saved layouts and OSD state were preserved. Short connection errors during the deliberate socket-off/start cycle recovered. Playback, Sonos firmware/CEC and HomeKit pairing were not requalified by this test.

## Preliminary 1.4.2 work, included in 1.5.0 — false Apple TV off protection — 2026-10-11

**146 tests pass on HA 2025.3.4/Python 3.13 and HA 2026.9.4/Python 3.14 with LG 2.32.1; Ruff passes.** Both linked state events and polling now require sustained HDMI loss for `off`/`standby`. Regressions cover present/unknown/returning signal, configurable and disabled timers, idle/low-power fallback isolation, final confirmation changes, automation lock, shutdown/unload, source/wake transitions, presentation protection, queued controls and explicit user shutdown. Alert regressions cover confirmation delay, enabled/locked automation, sensor state/icon/details, duplicate suppression, interrupted evidence, restored startup state and recovery/unknown-input conditions.

An initial 146-second physical run and a second 158-second alert run used the raw LG signal query while the resident SI app was foreground. They verified guard/alert behaviour against that reported value, **not the presence of embedded HDMI video**. The user's later no-signal report revealed that SI activity can remain positive without HDMI. The app-aware correction and hardware acceptance below supersede that signal interpretation. No 1.4.2 release was published.

All **19** acceptance scenarios passed in the same container using a separate TCP display simulator, fixture player, sound system and socket. The added cases verify a false-off event and permanently-off polling with valid HDMI, unknown signal protection, reset on returning signal, eventual display/socket shutdown after confirmed loss while the player remains off, and the confirmed Alert Status warning with automation locked plus its removal on unknown signal. Existing idle fallback, source isolation, playback/volume, HomeKit event routing, unload/reload, ownership and rename checks remain successful. Physical HDMI loss and a real socket cut were not induced; those destructive transitions used fixtures. Temporary lab entries and the fixture package were removed afterwards.

## 1.4.1 integration visibility — 2026-10-08

**103 tests pass on HA 2025.3.4 and HA 2026.9.4 with LG 2.31.0; Ruff passes.** This release changes the manifest classification from `helper` to `device` so each combined AV system appears in the normal Integrations overview.

Installed in the existing HA 2026.9.4 Docker instance and verified after restart: AV Companion is visible in the Integrations overview, the existing AV entry loads, and its configuration, device ID and all three entity registry IDs are preserved. All other configured integrations, including Apple TV, remain loaded; the Apple TV discovery helper is healthy. No device or integration was recreated.

## Regression audit — 2026-10-08

**103 tests pass in all four combinations of HA 2025.3.4/2026.9.4 and LG 2.0.0/2.30.2.** CI now retains both the minimum and current LG dependency checks. Six new harness tests require unique reserved lab names, reject missing/duplicate names and exclude unrelated domains/installations. AV runtime code and release version remain 1.4.0.

The existing **unifi-air-quality-ha-dev / HA 2026.9.4** passed all **14** full acceptance-harness scenarios against LG 2.30.2, using the local TCP simulator and fixture player, sound system and display socket. This includes real timer windows for valid-signal idle, stale idle plus no signal, LG-before-socket shutdown, no stale re-wake, explicit wake, source guards, service/HomeKit-event routing, duplicate ownership, unload/reload and entity rename. Entries were selected by their exact lab names before any unload; the harness now enforces this scope itself.

All temporary entries and the copied fixture were removed, and the simulator stopped. After HA restart the original entries and UniFi integration remained loaded. The physical LG's settings and Studio configuration were unchanged, and its Mediaplayer app remained connected. See the LG [test matrix and hardware limits](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/TEST-MATRIX.md). These simulator tests do not pair Apple Home or reproduce physical tvOS/Sonos/AX310 firmware and CEC behaviour.

## AV 1.2.0 / LG 2.10.0 — 2026-10-04

**93 tests pass on HA 2025.3.4/Python 3.13 and HA 2026.9.4/Python 3.14.** Added coverage checks optional PiP availability, non-colliding source names, failure preserving the previous source, selection without waking the linked player, direct LG source reflection, standby protection and leaving PiP for a player app even when its HDMI input is cached. CI retains import compatibility with LG 2.0.0/API v1.

A temporary real AV entry in the existing **unifi-air-quality-ha-dev / HA 2026.9.4** container controlled the existing physical **LG 75UH5F-HJ**. PiP appeared and selected the independent LG composition; HDMI 1 restored full-screen video. Selecting PiP directly on LG propagated to the combined player. The temporary AV entry was removed and the original HDMI 1 source restored. No new HA container, linked player/soundbar/socket configuration or HomeKit pairing was created. The native LG view and restart checks are documented in the LG repository's 2.10.0 acceptance.

## AV 1.1.0 / LG 2.7.0 — 2026-10-04

**91 tests pass on HA 2025.3.4/Python 3.13 and HA 2026.9.4/Python 3.14.** New tests cover optional Dashboard availability, direct LG source reflection, non-colliding labels, display-only wake/selection, failed selection, missing API extensions and leaving Dashboard for a linked player app even when the HDMI cache matches. Existing standby, power-supply, metadata, controls and HomeKit event tests remain successful. CI continues testing import/API compatibility with LG 2.0.0.

In the existing **unifi-air-quality-ha-dev / HA 2026.9.4** container, a temporary AV config entry linked to the already configured physical LG **75UH5F-HJ** verified:

- Dashboard appeared in the combined source list and selecting it changed both the LG and AV source to Dashboard while reporting ON.
- Selecting HDMI 1 through AV returned to television. Selecting Dashboard directly on LG also updated the combined entity.
- Disabling custom Studio layouts removed the optional source; restoring layouts made it available again.
- The temporary AV entry was removed afterwards; the original LG entry and Morgenlicht dashboard remain, with HDMI 1 active. No new HA container, real player/soundbar/socket configuration or Apple Home pairing was created.

The feature adds a normal source to the combined TV entity used by HomeKit. Actual iPhone pairing/input discovery is not part of this acceptance. Player-app return with a matching cached HDMI input and source-label collisions are covered by regression tests.

## Initial split acceptance

Versions: **LG Professional Display 2.0.0**, **AV Companion 1.0.0**. Fresh configuration; no migration. The shared Docker test installation was updated from HA 2026.8.1 to **2026.9.4** after backing up its stopped configuration, components and Compose file. Existing UniFi Air Quality remained loaded and its data was preserved.

## Automated coverage

**144 LG tests + 86 AV tests = 230 tests**, on HA 2025.3.4 / Python 3.13 and HA 2026.9.4 / Python 3.14. Includes actual HA entity-service registration, a real HA event bus, local TCP framing and an HTTP stream view. Tests cover native uploads, cancellation/cleanup, OSD state preservation, URL recovery, camera throttling, boot-image generation, staged standby, volume/remote routing, unavailable devices, fresh confirmed-off power guards, queue/download ownership, external presentation leases, independent controller operation and reload-safe adapter access.

The split uncovered and fixed a forgotten-supply hint that could leave the base marked unpowered, a native-download gap in presentation ownership, a source-select path bypassing cancellation, and a status callback that HA would dispatch to a worker thread. The event-loop regression is tested with the actual HA event bus.

## HA 2026.9.4 container acceptance

The actual config/options flows and registered entity services were exercised with an LG TCP simulator plus separate registered source, sound and socket fixture entities. No physical socket or Apple TV was used for the destructive-transition scenarios.

- Independent LG setup and AV selection; optional device options; duplicate AV ownership rejected.
- Volume/mute/night-mode routing to sound without changing LG volume; play/pause/stop forwarding.
- HomeKit event target filtering and LG remote command delivery.
- Idle plus valid HDMI signal beyond the configured idle timeout leaves LG on.
- Sustained signal loss while the source says idle powers LG off before cutting the socket.
- Repeated stale idle cannot wake it; explicit AV wake restores socket, display and source.
- Another physical HDMI input blocks linked-player standby shutdown.
- LG unload makes AV unavailable without cutting supply; LG reload reconnects the existing adapter.
- AV unload forgets its supply hint; standalone LG power control still works.
- Optional player entity rename updates AV options; playback continues after reload.
- Full container restart reloads both integrations and UniFi successfully.

The simulator and fixture instructions are provided in the AV repository's `dev/` directory. Polling, timer waits and actual socket services are used; HTTP state injection alone is not the test mechanism.

## Physical LG acceptance after the split

On the **75UH5F-HJ / 04.13.50 / webOS 4.0.1-136**, the separate LG integration was configured in the same Docker HA instance. Through its registered HA services:

- The native toast was acknowledged over the authenticated pinned LG connection.
- A PNG was uploaded, shown for five seconds, restored to the original HDMI input and cleaned up without a presentation error.
- The camera API returned an actual 640×360 JPEG capture.

This validates service execution, device responses, state restoration and a captured image. The user had previously visually confirmed overlays, fullscreen return and OSD suppression; this run does not claim a new user visual confirmation. Earlier video/HLS/website hardware evidence remains in [LG NATIVE-MEDIA](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/NATIVE-MEDIA.md) and its device reference.

## Remaining device-dependent limits

A real Apple Home/iPhone pairing, actual tvOS/Sonos service behavior, USB boot-image import and a physical boot with that image were not repeated by these tests. The AX310 standby behavior is the owner's observed wiring behavior; no new mains-loss experiment was performed. Other LG models/firmware require their own acceptance. HDMI signal retained by an extractor plus false player idle is inherently ambiguous; the default policy does not force off a valid signal. Native live video capture and network installation of a custom boot logo are not claimed.

## 1.4.0 dynamic-source acceptance — 2026-10-05

97 tests pass on HA 2025.3.4/Python 3.13 and HA 2026.9.4/Python 3.14. Coverage includes LG 2.14 optional API support, custom-source routing by stable ID, collision-safe labels, direct-source reflection, renamed sources, linked HDMI exit and standby protection.

A temporary AV entry in the existing HA 2026.9.4 container selected a custom Studio view on the physical LG. Renaming updated the combined source live; selection survived a container restart; deleting the active view returned both entities to Dashboard and removed the source. The temporary AV entry/view were removed and the original Dashboard PiP source restored. No Sonos playback command was sent; actual Apple Home pairing was not tested.
