# Split release acceptance — 2026-10-02

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
