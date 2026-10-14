# AV Companion

Combine an LG professional display, an optional player such as Apple TV, a sound system such as Sonos, and a display-only power socket into **one Home Assistant TV media player**. Uses the devices' existing HA integrations; it does not implement their network protocols.

Requires [LG Professional Display 2.0.0 or later](https://github.com/mvs90/lg_rs232_ip) (public API v1) and Home Assistant 2025.3 or later. Each LG display can have one AV system. All other devices are optional. Current version: **1.6.0**.

[Deutsche Anleitung](docs/README.de.md) · [Actions and examples](docs/FEATURES.md) · [Standby behavior](docs/STANDBY.md) · [MIT license](LICENSE)

## Installation

1. Install and configure **LG Professional Display** first.
2. In HACS add `https://github.com/mvs90/av_companion` as a custom repository, category **Integration**. Download and restart HA.
3. Add **AV Companion** under Settings → Devices & services; select the LG display entity.
4. Configure optional player/remote, volume player, sound-mode switches, socket and display-only power sensor.

AV Companion appears under **Settings → Devices & services → Integrations**. The **Devices** tab lists each combined AV system under its chosen name, such as “Living room AV”. Updating from 1.4.0 preserves existing entries, device/entity IDs and settings; restart Home Assistant to apply the corrected integration classification.

HACS requires one integration per repository. Both packages must be installed separately; the HA dependency declaration controls loading, not automatic HACS installation. Neither package is currently in the default HACS catalogue. Manual install: copy `custom_components/av_companion` alongside `custom_components/lg_rs232_ip`.

## One TV for the whole system

The combined TV exposes LG inputs, player apps and playback metadata, and routes volume/mute to the chosen sound system. Controls follow the active input and supported device capabilities. HomeKit navigation uses the linked remote on its input and LG navigation on other inputs. Native LG content suppresses player metadata and automatic standby until it finishes. With **LG 2.7.0** and enabled Studio layouts/resident SI mode, **Dashboard** also appears in this combined source list (and its HomeKit inputs). Selecting it restores the configured display supply if needed, then selects the LG dashboard without waking the linked player. Select HDMI or a player app to return. The source follows direct LG selections as well; intentionally selected dashboards are protected from automatic player-idle standby. Configure widgets/backgrounds in LG Display Studio. Older LG API v1 versions remain supported without this source.

Configure a **HomeKit Bridge in accessory mode**, including only the combined TV entity. Keep the individual device integrations installed. [Official HA HomeKit setup](https://www.home-assistant.io/integrations/homekit/).

```yaml
homekit:
  - name: Living room AV
    mode: accessory
    port: 21064
    filter:
      include_entities:
        - media_player.living_room_av
```

Do not configure the same accessory twice through UI and YAML. A real Apple Home pairing is a separate installation acceptance step; automated event-routing tests do not establish iPhone pairing.

## App metadata fallback

When an app such as Netflix supplies no programme title or cover, the combined AV player exposes the current app name and logo instead. Title and artwork are evaluated independently; each genuine value takes precedence as soon as the source integration provides it again. While metadata is incomplete, the artist line shows the reported playback status unless a real artist is available. `idle` remains “Leerlauf”/“Idle”; it is not treated as proof of pause. Existing Display Studio media widgets and the combined HA/HomeKit player receive these values automatically.

App icons are retrieved on demand using the public bundle ID and HA country from Apple's App Store lookup service. Only those public lookup parameters are sent; playback titles, tokens and device credentials are not. Up to 32 icons (256 px) remain cached locally across restarts, with bounded requests and retries. Cached icons work offline. Apps absent from that catalogue or an unsuccessful first lookup receive a neutral badge with initials; no guessed logo is assigned. Sonos music keeps its own title/artwork; Sonos TV audio follows the linked video player.

## Reliable standby and power

False Apple TV `idle` is checked against repeated LG HDMI-signal observations, fresh input/power verification and optional display-only consumption evidence. Unknown status is never confirmed off. Default thresholds are 15 seconds without signal and 900 seconds idle when signal status is unknown. A valid signal blocks the idle fallback. If the extractor preserves a valid signal while Apple TV falsely reports idle, the state remains ambiguous. [All stages, limits and timing](docs/STANDBY.md).

A socket is cut only after a fresh LG-off confirmation. Wake cancels pending shutdown and waits for confirmed socket-on state. Native presentations and queued downloads block automatic shutdown. Base unload makes the AV entity unavailable; AV unload leaves LG device control independent.

For Sonos with the verified LG panel: **Apple TV → FeinTech AX310 → LG HDMI 1**, AX310 eARC → Sonos. **AX310 remains powered; only the LG uses the controlled socket.** The owner observed that this keeps Apple TV asleep across display mains loss. This is installation-specific. Native LG content audio is not automatically returned to Sonos. [Wiring reference](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/devices/FEINTECH-AX310.md).

## Actions

`send_remote_command`, `show_content`, `show_notification`, `show_display_content`, `clear_content`, `set_sound_mode`, and `announce` belong to `av_companion`. Native overlays, uploads, boot logo and screenshots belong to `lg_rs232_ip`. [Examples and precise behavior](docs/FEATURES.md).

One HDMI playback player, one audio player/volume target and an optional separate content player are supported. Arbitrary multi-player input matrices, Sonos group management and a new Apple TV API are not included. Linked entities are owned by their original integrations. Optional entity renames are followed; removed devices must be reconfigured.

## Development

Checkout LG Professional Display 2.0.0 beside this repository and add both roots to `PYTHONPATH` for tests:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
PYTHONPATH="$PWD:$PWD/../lg_rs232_ip" .venv/bin/python -m pytest -q
.venv/bin/ruff check custom_components tests
```

[Test report and Docker acceptance procedure](docs/TESTING.md) · [LG API contract](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/ARCHITECTURE.md).

With **LG 2.10.0** and **AV Companion 1.2.0**, **PiP** also appears as a persistent source. It uses the last HDMI input inside its separately assigned Studio view. HDMI selections always return to full-screen video in the resident app. PiP selection does not wake a linked player; selecting a player app explicitly leaves PiP. Dashboard remains protected from automatic HDMI standby. PiP stays protected by default; AV 1.5.0 with LG 2.33.0 adds an optional, separately timed no-signal view fallback or shutdown. The optional source is absent with older LG versions.

### Full-screen media source

AV Companion 1.3.0 exposes **Mediaplayer** when LG Professional Display 2.12.0 provides the optional resident music view. Configure its player and design in LG Display Studio. Selecting this source does not start the linked Apple TV/player. Active view protection prevents automatic shutdown based on an idle HDMI source. The input is also exposed through the combined player to HomeKit; older LG versions continue without the additional source.

### All Studio sources (1.4)

With LG 2.14, the combined player automatically includes **Dashboard**, **Dashboard PiP**, **Mediaplayer** and every additional saved Studio view. Renames follow stable view IDs; labels remain unique against HDMI and player apps. Removing an active custom view returns to Dashboard. View selection retains the existing supply, acknowledgement and standby safeguards and does not start a linked player. These sources are exposed to HomeKit through the combined entity; actual Apple Home pairing is an installation acceptance step.

### Sonos, PiP Sonos and current audio (1.6)

A separate configured sound-system player adds **Sonos** and, when supported by the display app, **PiP Sonos**. Sonos opens the saved Mediaplayer view; PiP Sonos opens Dashboard PiP by default, or a separate saved view selected with **View for PiP Sonos**. These are display/transport selections, not commands to start a playlist or interrupt the sound system. Without the optional app, Sonos remains an audio source on the current display input.

Playing/buffering Sonos music, and paused music that can be resumed, supply the combined player's metadata, artwork and transport controls even while HDMI is displayed. Sonos **TV** audio (including `x-sonos-htastream`) uses the linked Apple TV/player's metadata instead. Unavailable Sonos also falls back to the linked player. Source metadata, progress, play/pause, next/previous and artwork use the same player; the `playback_entity_id` attribute identifies it. Album art is fetched through the original HA entity, supporting authenticated Apple TV artwork. An upstream app that supplies no artwork remains without artwork.

Select the **combined AV entity** for media widgets and cover backgrounds in Display Studio to use this automatic routing on screen. A separate PiP Sonos layout can contain its own HDMI and media widgets. Deleted assigned views fall back to Dashboard PiP. Existing views and their widget bindings are preserved by integration updates.

**Switch sound system to TV audio when selecting HDMI** is disabled by default. Leave it off to use Sonos's own TV Autoplay. When enabled, only an explicit HDMI input selection requests the configured TV source. Power-on, player apps, Sonos, Dashboard, Mediaplayer and all PiP views leave the audio source alone. Explicitly selecting HDMI still opens full-screen HDMI in the resident app. Sonos music protects an HDMI-only display from the Apple TV no-signal shutdown; separately configured PiP no-signal actions remain applicable.

Alert Status identifies the affected player's friendly name. Countdown messages support `{player}`, `{action}` and `{seconds}`; the previous built-in text automatically gains the HDMI player name, while custom text remains editable.

### Select a source to start the display

With AV Companion **1.6.2** and LG Professional Display **2.33.1**, one source selection restores the configured supply, waits for confirmed power and, when enabled, the resident app, then applies the requested HDMI, Dashboard, PiP, media or custom view. The requested source stays visible while `source_selection_pending` is true. A newer selection or power command supersedes the older request. Failed input/app acknowledgement is reported instead of silently requiring a second selection. Install both updates for the resident-app startup correction; Display Studio does not need an update.
