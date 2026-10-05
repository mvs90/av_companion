# Split release acceptance — 2026-10-02

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
