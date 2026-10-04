# AV Companion

Combine an LG professional display, an optional player such as Apple TV, a sound system such as Sonos, and a display-only power socket into **one Home Assistant TV media player**. Uses the devices' existing HA integrations; it does not implement their network protocols.

Requires [LG Professional Display 2.0.0 or later](https://github.com/mvs90/lg_rs232_ip) (public API v1) and Home Assistant 2025.3 or later. Each LG display can have one AV system. All other devices are optional. Version **1.2.0** is a fresh setup without prototype migration.

[Deutsche Anleitung](docs/README.de.md) · [Actions and examples](docs/FEATURES.md) · [Standby behavior](docs/STANDBY.md) · [MIT license](LICENSE)

## Installation

1. Install and configure **LG Professional Display** first.
2. In HACS add `https://github.com/mvs90/av_companion` as a custom repository, category **Integration**. Download and restart HA.
3. Add **AV Companion** under Settings → Devices & services; select the LG display entity.
4. Configure optional player/remote, volume player, sound-mode switches, socket and display-only power sensor.

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

## Reliable standby and power

False Apple TV `idle` is checked against repeated LG HDMI-signal observations, fresh input/power verification and optional display-only consumption evidence. Unknown status is never confirmed off. Default thresholds are 120 seconds without signal and 900 seconds idle when signal status is unknown. A valid signal blocks the idle fallback. If the extractor preserves a valid signal while Apple TV falsely reports idle, the state remains ambiguous. [All stages, limits and timing](docs/STANDBY.md).

A socket is cut only after a fresh LG-off confirmation. Wake cancels pending shutdown and waits for confirmed socket-on state. Native presentations and queued downloads block automatic shutdown. Base unload makes the AV entity unavailable; AV unload leaves LG device control independent.

For Sonos with the verified LG panel: **Apple TV → FeinTech AX310 → LG HDMI 1**, AX310 eARC → Sonos. **AX310 remains powered; only the LG uses the controlled socket.** The owner observed that this keeps Apple TV asleep across display mains loss. This is installation-specific. Native LG content audio is not automatically returned to Sonos. [Wiring reference](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/devices/FEINTECH-AX310.md).

## Actions

`send_remote_command`, `show_content`, `show_notification`, `show_display_content`, `clear_content`, `set_sound_mode`, and `announce` belong to `av_companion`. Native overlays, uploads, boot logo and screenshots belong to `lg_rs232_ip`. [Examples and precise behavior](docs/FEATURES.md).

One playback player, one volume target and an optional separate content player are supported. Arbitrary multi-player input matrices, Sonos group management and a new Apple TV API are not included. Linked entities are owned by their original integrations. Optional entity renames are followed; removed devices must be reconfigured.

## Development

Checkout LG Professional Display 2.0.0 beside this repository and add both roots to `PYTHONPATH` for tests:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
PYTHONPATH="$PWD:$PWD/../lg_rs232_ip" .venv/bin/python -m pytest -q
.venv/bin/ruff check custom_components tests
```

[Test report and Docker acceptance procedure](docs/TESTING.md) · [LG API contract](https://github.com/mvs90/lg_rs232_ip/blob/main/docs/ARCHITECTURE.md).

With **LG 2.10.0** and **AV Companion 1.2.0**, **PiP** also appears as a persistent source. It uses the last HDMI input inside its separately assigned Studio view. HDMI selections always return to full-screen video in the resident app. PiP selection does not wake a linked player; selecting a player app explicitly leaves PiP. Both Dashboard and PiP remain protected from automatic idle-based standby until explicitly turned off. The optional source is absent with older LG versions.
