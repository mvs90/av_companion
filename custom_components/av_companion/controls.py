"""Optional remote, media and presentation controls without model assumptions."""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import math
import uuid

from homeassistant.components import media_source
from homeassistant.components.media_player import MediaPlayerEntityFeature as Feature
from homeassistant.components.media_player import (
    async_process_play_media_url,
    MediaPlayerState,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import INPUT_SOURCES

_LOGGER = logging.getLogger(__name__)
REMOTE_KEYS = {
    "arrow_up": "up",
    "arrow_down": "down",
    "arrow_left": "left",
    "arrow_right": "right",
    "select": "select",
    "back": "menu",
    "exit": "home",
    "rewind": "skip_backward",
    "fast_forward": "skip_forward",
    "next_track": "next",
    "previous_track": "previous",
    "play_pause": "play_pause",
}
LG_KEYS = {
    "up": 0x40,
    "down": 0x41,
    "left": 0x07,
    "right": 0x06,
    "select": 0x44,
    "menu": 0x28,
    "home": 0x43,
    "information": 0xAA,
}


def in_quiet_hours(start: str, end: str) -> bool:
    """Use Home Assistant's local timezone, including overnight ranges."""
    now = dt_util.now().time()
    first, last = dt_util.parse_time(start), dt_util.parse_time(end)
    if first is None or last is None or first == last:
        return False
    return first <= now < last if first < last else now >= first or now < last


class ExtendedControls:
    """Mixin for explicit, capability-aware optional controls."""

    def _init_controls(self):
        self._control_lock = asyncio.Lock()
        self._presentation_task = None
        self._presentation_active = False
        self._presentation_queue = deque()
        self._presentation_error = None

    def _option_entity(self, key):
        value = self._config_entry.options.get(key)
        return value if isinstance(value, str) and value else None

    def _features_for(self, entity_id):
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {"unavailable", "unknown"}:
            return Feature(0)
        return Feature(state.attributes.get("supported_features", 0))

    @property
    def _content_target(self):
        return (
            self._option_entity("content_media_player_entity_id")
            or self._linked_entity_id
        )

    @property
    def _content_input(self):
        if self._option_entity("content_media_player_entity_id"):
            return INPUT_SOURCES[
                self._config_entry.options.get("content_player_input", "HDMI 2")
            ]
        return self._linked_input_id

    async def _required_call(self, domain, service, entity_id, **kwargs):
        if not entity_id or entity_id == self.entity_id:
            raise ServiceValidationError("Configure an external target entity first")
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unavailable", "unknown"}:
            raise HomeAssistantError(f"Target {entity_id} is unavailable")
        await self.hass.services.async_call(
            domain, service, {"entity_id": entity_id, **kwargs}, blocking=True
        )

    async def _async_remote_power(self, on):
        remote = self._option_entity("linked_remote_entity_id")
        if not remote:
            return await self._async_call_linked_service(
                "turn_on" if on else "turn_off"
            )
        if (
            self._config_entry.options.get("linked_remote_power_mode", "generic")
            == "apple_tv"
        ):
            await self._required_call(
                "remote", "send_command", remote, command="wakeup" if on else "suspend"
            )
        else:
            await self._required_call("remote", "turn_on" if on else "turn_off", remote)
        return True

    async def async_send_remote_command(self, command):
        """Send navigation only to the device on the currently selected input."""
        input_id = await self._lg_display.async_get_input(use_cache=False)
        if input_id is None:
            raise HomeAssistantError("Cannot determine the active display input")
        self._current_input_id = input_id
        remote = self._option_entity("linked_remote_entity_id")
        if self._is_linked_input_active and remote:
            await self._required_call("remote", "send_command", remote, command=command)
        elif command in LG_KEYS:
            if not await self._lg_display.async_send_remote_key(LG_KEYS[command]):
                raise HomeAssistantError("Display rejected the remote command")
        else:
            raise ServiceValidationError("Command is unavailable on the active input")

    async def _async_homekit_key(self, event):
        if event.data.get("entity_id") != self.entity_id or self._ha_stopping:
            return
        key = event.data.get("key_name")
        command = REMOTE_KEYS.get(key, "information" if key == "information" else None)
        if command:
            try:
                if command == "play_pause":
                    await self.async_media_play_pause()
                else:
                    await self.async_send_remote_command(command)
            except HomeAssistantError as err:
                self._report_issue(
                    "remote_command_failed", str(err), trigger="homekit remote"
                )

    async def _async_resolve_media(self, media_id, media_type, target):
        if media_source.is_media_source_id(media_id):
            item = await media_source.async_resolve_media(self.hass, media_id, target)
            media_id, media_type = item.url, item.mime_type
        # Deep links are passed through. Local HA paths/HTTP media get usable URLs.
        if media_id.startswith(("/", "http://", "https://")):
            media_id = async_process_play_media_url(self.hass, media_id)
        return media_id, media_type

    async def _async_prepare_content(self):
        self._cancel_power_supply_off_task()
        self._standby_guard.reset()
        await self._async_ensure_display_on_after_power_restore("content playback")
        if await self._lg_display.async_get_power_status(use_cache=False) is not True:
            raise HomeAssistantError("Display did not become ready")
        if not await self._lg_display.async_set_input(self._content_input):
            raise HomeAssistantError("Display rejected the content input")
        self._current_input_id = self._content_input
        self._source = self._resolve_source_name(self._current_input_id)

    async def _async_play_content(self, media_type, media_id, **kwargs):
        target = self._content_target
        if not self._features_for(target) & Feature.PLAY_MEDIA:
            raise ServiceValidationError("Content player does not support play_media")
        media_id, media_type = await self._async_resolve_media(
            media_id, media_type, target
        )
        await self._async_cancel_wake()
        await self._async_prepare_content()
        if target == self._linked_entity_id and self._option_entity(
            "linked_remote_entity_id"
        ):
            await self._async_remote_power(True)
        elif self._features_for(target) & Feature.TURN_ON:
            await self._required_call("media_player", "turn_on", target)
        await self._required_call(
            "media_player",
            "play_media",
            target,
            media_content_type=media_type,
            media_content_id=media_id,
            **kwargs,
        )
        self.async_write_ha_state()

    async def async_play_media(self, media_type, media_id, **kwargs):
        await self._async_cancel_presentations()
        async with self._control_lock:
            await self._async_play_content(media_type, media_id, **kwargs)

    async def async_media_seek(self, position):
        await self._async_playback_action(
            "media_seek", Feature.SEEK, seek_position=position
        )

    async def async_set_shuffle(self, shuffle):
        await self._async_playback_action(
            "shuffle_set", Feature.SHUFFLE_SET, shuffle=shuffle
        )

    async def async_set_repeat(self, repeat):
        await self._async_playback_action(
            "repeat_set", Feature.REPEAT_SET, repeat=repeat
        )

    def _playback_attribute(self, name):
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        return (
            state.attributes.get(name)
            if state and state.state not in {"unknown", "unavailable"}
            else None
        )

    @property
    def media_duration(self):
        return self._playback_attribute("media_duration")

    @property
    def media_position(self):
        return self._playback_attribute("media_position")

    @property
    def media_position_updated_at(self):
        value = self._playback_attribute("media_position_updated_at")
        return dt_util.parse_datetime(value) if isinstance(value, str) else value

    @property
    def shuffle(self):
        return self._playback_attribute("shuffle")

    @property
    def repeat(self):
        return self._playback_attribute("repeat")

    async def async_media_play_pause(self):
        state = (
            self.hass.states.get(self._playback_target)
            if self._playback_target
            else None
        )
        playing = state is not None and state.state == "playing"
        await self._async_playback_action(
            "media_pause" if playing else "media_play",
            Feature.PAUSE if playing else Feature.PLAY,
        )

    @property
    def _playback_target(self):
        if self._lg_display.presentation_active:
            return None
        if (
            self._option_entity("content_media_player_entity_id")
            and self._current_input_id == self._content_input
        ):
            return self._content_target
        return self._linked_entity_id if self._is_linked_input_active else None

    async def _async_playback_action(self, service, feature, **kwargs):
        target = self._playback_target
        if not target or not self._features_for(target) & feature:
            raise ServiceValidationError(
                "Playback action is unavailable on the active input"
            )
        if target == self._linked_entity_id:
            if not await self._async_call_linked_service(service, **kwargs):
                raise HomeAssistantError("Linked player rejected the playback action")
        else:
            await self._required_call("media_player", service, target, **kwargs)

    async def async_set_sound_mode(self, mode, enabled):
        key = {
            "night": "sonos_night_sound_entity_id",
            "speech": "sonos_speech_enhancement_entity_id",
        }[mode]
        await self._required_call(
            "switch", "turn_on" if enabled else "turn_off", self._option_entity(key)
        )

    async def async_announce(
        self, media_id, media_type="music", volume=40, priority="normal"
    ):
        """Use Sonos announcement mixing; never change persistent volume ourselves."""
        self._check_presentation_policy(priority)
        target = self._volume_entity_id
        if not self._features_for(target) & Feature.MEDIA_ANNOUNCE:
            raise ServiceValidationError("Sound system does not support announcements")
        media_id, media_type = await self._async_resolve_media(
            media_id, media_type, target
        )
        await self._required_call(
            "media_player",
            "play_media",
            target,
            media_content_id=media_id,
            media_content_type=media_type,
            announce=True,
            extra={"volume": volume},
        )

    def _power_sensor_in_standby(self):
        """Optional supplementary evidence; a measurement alone never powers off."""
        entity_id = self._option_entity("power_sensor_entity_id")
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.attributes.get("unit_of_measurement") not in {
            "W",
            "kW",
        }:
            return False
        if (dt_util.utcnow() - state.last_updated).total_seconds() > 180:
            return False
        try:
            watts = float(state.state) * (
                1000 if state.attributes["unit_of_measurement"] == "kW" else 1
            )
            return math.isfinite(
                watts
            ) and 0 <= watts <= self._config_entry.options.get(
                "standby_power_threshold", 0
            )
        except (ValueError, TypeError):
            return False

    def _check_presentation_policy(self, priority):
        options = self._config_entry.options
        if (
            priority != "urgent"
            and options.get("quiet_hours_enabled", False)
            and in_quiet_hours(
                options.get("quiet_hours_start", "22:00"),
                options.get("quiet_hours_end", "07:00"),
            )
        ):
            raise ServiceValidationError("Presentation blocked by quiet hours")

    async def async_show_content(
        self, media_id, media_type="video", duration=30, priority="normal"
    ):
        if not self._features_for(self._content_target) & Feature.PLAY_MEDIA:
            raise ServiceValidationError(
                "Configure a content player supporting play_media"
            )
        await self._enqueue_presentation(
            dict(
                kind="content",
                media_id=media_id,
                media_type=media_type,
                duration=duration,
                priority=priority,
            )
        )

    async def async_show_notification(
        self, message, title="", duration=10, priority="normal", mode="overlay"
    ):
        if not self._option_entity("notification_script_entity_id"):
            raise ServiceValidationError(
                "No notification renderer configured; use show_toast for native LG text overlays"
            )
        await self._enqueue_presentation(
            dict(
                kind="notification",
                message=message,
                title=title,
                duration=duration,
                priority=priority,
                mode=mode,
            )
        )

    async def _enqueue_presentation(self, request):
        self._check_presentation_policy(request["priority"])
        if self._ha_stopping:
            raise HomeAssistantError("Integration is stopping")
        if len(self._presentation_queue) >= 10:
            raise ServiceValidationError("Presentation queue is full (10 requests)")
        if request["priority"] == "urgent":
            self._presentation_queue.appendleft(request)
        else:
            self._presentation_queue.append(request)
        if self._presentation_task is None or self._presentation_task.done():
            self._presentation_task = self.hass.async_create_task(
                self._async_presentations()
            )
        self.async_write_ha_state()

    async def _async_notification_renderer(self, request, action, token):
        script = self._option_entity("notification_script_entity_id")
        # Calling the script's own service waits for rendering/cleanup completion.
        await self.hass.services.async_call(
            "script",
            script.split(".", 1)[1],
            {
                "action": action,
                "session_id": token,
                "message": request["message"],
                "title": request["title"],
                "duration": request["duration"],
                "mode": request["mode"],
            },
            blocking=True,
        )

    async def _async_presentations(self):
        try:
            while self._presentation_queue and not self._ha_stopping:
                request = self._presentation_queue.popleft()
                try:
                    await self._async_present_one(request)
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    self._presentation_error = str(err)
                    _LOGGER.warning("Presentation failed: %s", err)
                    self.async_write_ha_state()
        finally:
            self._presentation_active = False
            self._presentation_task = None

    async def _async_present_one(self, request):
        token = await self._lg_display.async_begin_external_presentation()
        try:
            await self._async_present_external_one(request)
        finally:
            await self._lg_display.async_end_external_presentation(token)

    async def _async_present_external_one(self, request):
        token = uuid.uuid4().hex
        snapshot = None
        renderer_started = False
        presentation_input = None
        self._presentation_error = None
        try:
            async with self._control_lock:
                self._check_presentation_policy(request["priority"])
                power = await self._lg_display.async_get_power_status(use_cache=False)
                if power is None:
                    raise HomeAssistantError("Display power is unknown")
                if not power and not self._config_entry.options.get(
                    "notification_wake_display", False
                ):
                    raise HomeAssistantError(
                        "Display is off and notification wake is disabled"
                    )
                previous_input = (
                    await self._lg_display.async_get_input(use_cache=False)
                    if power
                    else None
                )
                if power and previous_input is None:
                    raise HomeAssistantError("Cannot preserve the current input")
                snapshot = (power, previous_input)
                self._presentation_active = True
                self._standby_guard.reset()
                await self._async_cancel_wake()
                self._cancel_power_supply_off_task()
                if request["kind"] == "content":
                    await self._async_play_content(
                        request["media_type"], request["media_id"]
                    )
                else:
                    if not power:
                        await self._async_ensure_display_on_after_power_restore(
                            "notification"
                        )
                        if (
                            await self._lg_display.async_get_power_status(
                                use_cache=False
                            )
                            is not True
                        ):
                            raise HomeAssistantError("Display did not become ready")
                    renderer_started = True
                    async with asyncio.timeout(15):
                        await self._async_notification_renderer(request, "show", token)
                presentation_input = (
                    await self._lg_display.async_get_input(use_cache=False)
                    if request["kind"] == "notification"
                    else self._content_input
                )
                self.async_write_ha_state()
            await asyncio.sleep(request["duration"])
        finally:
            # Cleanup also runs when cancelled during startup or media submission.
            async with self._control_lock:
                if renderer_started:
                    try:
                        async with asyncio.timeout(15):
                            await self._async_notification_renderer(
                                request, "clear", token
                            )
                    except Exception as err:
                        self._presentation_error = str(err)
                        _LOGGER.warning("Notification cleanup failed: %s", err)
                try:
                    if snapshot and not self._ha_stopping:
                        power, previous_input = snapshot
                        if (
                            await self._lg_display.async_get_power_status(
                                use_cache=False
                            )
                            is True
                        ):
                            current = await self._lg_display.async_get_input(
                                use_cache=False
                            )
                            expected = (
                                self._content_input
                                if request["kind"] == "content"
                                else presentation_input
                            )
                            if previous_input is not None and current == expected:
                                if not await self._lg_display.async_set_input(
                                    previous_input
                                ):
                                    raise HomeAssistantError(
                                        "Could not restore display input"
                                    )
                                self._current_input_id = previous_input
                                self._source = self._resolve_source_name(previous_input)
                            elif (
                                not power
                                and expected is not None
                                and current == expected
                            ):
                                if await self._lg_display.async_power_off():
                                    self._state = MediaPlayerState.OFF
                                    self._last_display_power = False
                                    self._schedule_power_supply_off(
                                        "presentation complete"
                                    )
                except Exception as err:
                    self._presentation_error = str(err)
                    _LOGGER.warning("Presentation restoration failed: %s", err)
                finally:
                    self._presentation_active = False
                    self._standby_guard.reset()
                    self.async_write_ha_state()

    async def _async_cancel_presentations(self):
        self._presentation_queue.clear()
        task = self._presentation_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            if not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._presentation_task = None

    async def async_clear_content(self):
        await self._async_cancel_presentations()
        await self._lg_display.async_clear_content()

    async def async_show_display_content(self, kind, media_id, duration=60, muted=True):
        self._check_presentation_policy("normal")
        await self._async_cancel_presentations()
        async with self._control_lock:
            self._cancel_power_supply_off_task()
            await self._async_cancel_wake()
            if not self._lg_display.presentation_active:
                await self._async_ensure_display_on_after_power_restore(
                    "native display content"
                )
            actions = {
                "image": "show_native_image",
                "video": "show_native_video",
                "stream": "show_stream",
                "website": "show_website",
            }
            values = {
                "url" if kind == "website" else "media_id": media_id,
                "duration": duration,
            }
            if kind == "stream":
                values["muted"] = muted
            await self._lg_display.async_present(actions[kind], **values)
