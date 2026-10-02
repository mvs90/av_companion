# AV Companion controls

The LG display remains the main device. Every link is optional. Install the official integrations for your linked devices first. Configure links under **Settings → Devices & services → AV Companion → Configure**. Do not select another entity belonging to this integration as a target; circular links are rejected.

## Remote and HomeKit

Select the Apple TV `remote` entity and choose **apple_tv** for remote power commands. Explicit TV on/off then uses `wakeup`/`suspend`. With a different remote, choose **generic** for `remote.turn_on`/`remote.turn_off`. Without a remote, the previous linked media-player power actions remain the fallback.

HomeKit `homekit_tv_remote_key_pressed` events are accepted only for this TV's entity ID. Arrows, select, back, exit and track/skip keys go to the linked remote when its HDMI input is active. On other inputs, supported navigation keys go to the LG panel. Playback controls follow the active media player. Unsupported controls are not advertised; next/previous track no longer masquerade as LG direction keys.

For automations:

```yaml
action: av_companion.send_remote_command
target:
  entity_id: media_player.living_room_av
data:
  command: home
```

The HomeKit setup remains accessory mode with only the combined TV selected. Device-specific remote commands and app behaviour still depend on the target device.

## Media, deep links and cameras

Standard `media_player.play_media` now forwards to the configured **content player**, or to the linked player if no separate content player is configured. Select the physical HDMI input for a separate content player. The display is powered on and its input selected before playback. HA media-source IDs are resolved and local HA URLs are processed for device access; application deep links are preserved.

```yaml
action: media_player.play_media
target:
  entity_id: media_player.living_room_av
data:
  media_content_type: url
  media_content_id: youtube://watch/VIDEO_ID
```

This is normal playback, with no timed restoration. Seek, repeat and shuffle are passed through when the active player supports them. A separate content player supplies playback state and metadata while its input is active.

A URL alone does not make a player a web browser. Apple TV cannot display an arbitrary HA dashboard through `play_media`. Web pages require a browser-capable target; images, camera streams and videos require a target supporting their format. Camera media-source URLs can be resolved through HA, but the target must support the resulting stream. Use an explicit media URL or a media-source ID supported by your HA installation.

## Temporary content and queue

```yaml
action: av_companion.show_content
target:
  entity_id: media_player.living_room_av
data:
  media_id: media-source://media_source/local/doorbell.mp4
  media_type: video
  duration: 30
  priority: normal
```

- Requests are queued (maximum 10 pending). An `urgent` request goes next; it does not interrupt the current presentation.
- The current display input is captured before playback and restored after the duration. The duration starts once content submission completes.
- Display wake is **disabled by default** for temporary content and notifications. Enable it explicitly if required. Normal `play_media` is an explicit playback request and can wake the display.
- Quiet hours use HA's local timezone, support overnight intervals and are checked both when queued and when started. `urgent` bypasses quiet hours, but never the disabled-wake setting.
- While a temporary presentation is active, linked standby automation is suspended. Afterwards its evidence is reset.
- A manual command through the combined TV cancels the presentation before performing the new command. If the physical input changed externally, automatic restoration does not overwrite that input.
- Failures are reported through `presentation_error`; queued actions return when accepted, not when playback finishes.

```yaml
action: av_companion.clear_content
target:
  entity_id: media_player.living_room_av
```

This clears the queue and ends the current presentation. Restoration concerns the **display input and any display power enabled for that presentation**. It does not reconstruct a movie's playback position, DRM session or app state. Reusing Apple TV for temporary content can replace its previous playback. A separate content player is preferable when the original movie should continue independently. The integration does not alter Sonos volume for visual presentations. If a source was changed and changed back externally between observations, ownership of that change cannot be determined perfectly.

## Custom screen notifications: renderer interface

Configure **Notification renderer script** only when you have a working on-screen backend. The integration provides queuing, quiet hours, wake policy, duration, cleanup and `overlay`/`fullscreen` selection. It does **not** implement an undocumented UH5C overlay API, install an LG app or turn Apple TV into an arbitrary notification renderer. Without a renderer, `show_notification` returns an explicit error.

```yaml
action: av_companion.show_notification
target:
  entity_id: media_player.living_room_av
data:
  message: Someone is at the front door
  title: Doorbell
  mode: overlay
  duration: 15
  priority: normal
```

The selected script is called directly as `script.<your_script>` with these variables:

| Variable | Meaning |
| --- | --- |
| `action` | `show` or `clear` |
| `session_id` | Unique identifier, identical for both calls |
| `message`, `title` | Content to render |
| `mode` | `overlay` or `fullscreen` |
| `duration` | Requested duration in seconds |

The renderer must perform a short show/clear operation and return, not wait out the duration. Each call has a 15-second timeout. It must validate the requested mode, reject unsupported overlays and clear only the matching session. It must not override a newer user-selected view. A backend that supports neither clear nor session ownership should implement those semantics itself before use. For the verified LG-native actions below, no renderer script is needed.

The backend may manage its own content layout. When it changes HDMI input, the integration records the resulting input and restores the original one only if it still owns the selection. This script's overlay support depends on its backend. Native LG text overlays use `lg_rs232_ip.show_toast` on the LG entity. Web credentials belong only to LG Professional Display.

## Sonos / sound-system options

Select the separate volume player as before. Optionally choose existing Sonos **Night Sound** and **Speech Enhancement** switch entities. They remain Sonos-owned controls; this integration forwards actions instead of duplicating Sonos device discovery.

```yaml
action: av_companion.set_sound_mode
target:
  entity_id: media_player.living_room_av
data:
  mode: night  # or speech
  enabled: true
```

Enable **Select sound system TV input on explicit turn-on** only for a device whose source list contains the configured source name (default `TV`). No sound-system power-off or grouping is inferred. This keeps independently playing music separate from display standby.

```yaml
action: av_companion.announce
target:
  entity_id: media_player.living_room_av
data:
  media_id: media-source://media_source/local/chime.mp3
  media_type: music
  volume: 35
```

The target must advertise announcement support. This sends `announce: true` with a temporary announcement volume; persistent volume is not changed by this integration. Sonos mixing/restoration is delegated to the official integration. TTS can be sent using an appropriate HA-generated media-source URL. Announcement calls obey normal quiet hours and do not power the display on. Sonos groups, favourites, alarms and equalizer controls remain available through the official Sonos integration rather than being copied into the TV entity.

## Standby, power and reduced polling

Startup timeout and the wait after switching on the power socket are configurable. Off cancels a pending wake task. Socket actions must reach the requested on/off state before the integration treats them as confirmed. Socket shutdown requires a fresh physical display-off query. A socket manually switched off cancels a pending wake.

Optionally select a **display-only power sensor** reporting W or kW and configure a measured standby threshold. Idle plus low consumption can confirm standby over 120 seconds when HDMI signal status is unknown. A valid HDMI signal, active playback, invalid units/numbers and measurements older than 180 seconds prevent this evidence from being used. Do not use a sensor measuring the combined display/Apple TV/Sonos load. It is supplementary evidence, never a shutdown trigger on its own. A sensor whose HA `last_updated` does not advance for identical readings is treated conservatively as stale.

Repeated read queries share a short cache; fresh shutdown confirmations bypass it. Writes invalidate the cache. Optional queries rejected with `NG` are suppressed for five minutes; timeouts do not permanently mark features unsupported. Advanced settings/diagnostic entities are disabled by default on new installations to avoid polling every model-specific command. Existing registry choices are preserved. Enable only the controls your panel supports. Commands and value maps are not automatically certified for every LG model.

Download integration diagnostics for connection and decision information without device addresses, entity names, media URLs or message text. Runtime attributes include `presentation_active`, `presentation_queue_size`, `presentation_error`, and `notification_backend_configured`.



## Native LG content from the combined player

`av_companion.show_display_content` accepts `kind: image|video|website|stream`, `media_id`, `duration` (1–3600 seconds), and `muted` for streams. This is an explicit playback request: it can restore the display socket and wake the LG, then delegates playback to the native LG queue. Configure native web access in the LG integration first. Normal quiet hours in both integrations apply. Use the LG actions directly if the base integration's disabled-wake policy should apply.

```yaml
action: av_companion.show_display_content
target:
  entity_id: media_player.living_room_av
data:
  kind: website
  media_id: https://example.org
  duration: 60
```

While LG native content is queued, downloading or playing, the combined entity suppresses Apple TV playback metadata and automatic standby. Native content uses LG audio outputs; it is not automatically routed back to Sonos through the AX310. Explicit off or source selection cancels native content with LG-owned cleanup first.

`av_companion.clear_content` clears both queues. Timed external presentations reserve the LG before starting; concurrent native queue requests are rejected while this reservation is held. A failed/unloaded LG makes the AV entity unavailable, never a confirmed standby.
