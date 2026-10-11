"""Separate the display view from the currently audible player's controls and art."""


class AudioRouting:
    def _player_name(self, entity_id):
        state = self.hass.states.get(entity_id) if entity_id else None
        return (
            str(state.attributes.get("friendly_name") or entity_id)[:160]
            if state
            else entity_id or "HDMI"
        )

    @property
    def _sound_player(self):
        target = self._option_entity("linked_volume_media_player_entity_id")
        return target if target != self._linked_entity_id else None

    @property
    def audio_sources(self):
        if not self._sound_player:
            return {}
        used = set(self._sources)
        result = {}
        # Stable labels for automation/HomeKit, distinct from editable Studio labels.
        for key, label in (("media_view", "Sonos"), ("pip_view", "PiP Sonos")):
            if (
                key == "pip_view"
                and getattr(self._lg_display, "pip_available", False) is not True
            ):
                continue
            while label in used:
                label += " (Audio)"
            used.add(label)
            result[key] = label
        return result

    @property
    def _sonos_pip_view(self):
        selected = self._config_entry.options.get("sonos_pip_view", "pip_view")
        views = getattr(self._lg_display, "view_sources", None)
        return selected if isinstance(views, dict) and selected in views else "pip_view"

    @property
    def _audio_view_active(self):
        view = self._audio_view
        if view not in self.audio_sources:
            return False
        active = getattr(self._lg_display, "active_view", None)
        if isinstance(active, str):
            return active == (self._sonos_pip_view if view == "pip_view" else view)
        if view == "pip_view":
            return getattr(self._lg_display, "pip_active", False) is True
        if self.media_view_source:
            return getattr(self._lg_display, "media_view_active", False) is True
        return True  # Audio-only selection on LG API versions without app views.

    @property
    def _sound_state(self):
        state = self.hass.states.get(self._sound_player) if self._sound_player else None
        if not state or state.state in {"unknown", "unavailable", "off", "standby"}:
            return None
        # Sonos labels TV as media_content_type=music too; never use that alone.
        attrs = state.attributes
        source = str(attrs.get("source") or "").strip().casefold()
        tv_source = (
            str(self._config_entry.options.get("sonos_tv_source", "TV"))
            .strip()
            .casefold()
        )
        content = str(attrs.get("media_content_id") or "").casefold()
        if source in {"tv", tv_source} or content.startswith("x-sonos-htastream:"):
            return None
        return state

    @property
    def _sound_music_active(self):
        state = self._sound_state
        return bool(state and state.state in {"playing", "buffering"})

    @property
    def _playback_target(self):
        view = getattr(self._lg_display, "active_view", None)
        persistent = isinstance(view, str) or any(
            getattr(self._lg_display, key, False) is True
            for key in ("dashboard_active", "pip_active", "media_view_active")
        )
        if self._presentation_active or (
            self._lg_display.presentation_active and not persistent
        ):
            return None
        sound = self._sound_state
        if sound and (
            self._sound_music_active
            or sound.state == "paused"
            or self._audio_view_active
            or persistent
        ):
            return self._sound_player
        if (
            self._option_entity("content_media_player_entity_id")
            and self._current_input_id == self._content_input
        ):
            return self._content_target
        if persistent or self._is_linked_input_active:
            return self._linked_entity_id
        return None

    @property
    def _default_media_target(self):
        if self._audio_view_active or self._playback_target == self._sound_player:
            return self._sound_player or self._content_target
        return self._content_target

    @property
    def _signal_player_name(self):
        context = self._pip_signal_context()
        input_id = context.get("input_id") if context else self._current_input_id
        if input_id == self._linked_input_id:
            return self._player_name(self._linked_entity_id)
        if input_id == self._content_input and self._option_entity(
            "content_media_player_entity_id"
        ):
            return self._player_name(self._content_target)
        return self._source_names_by_id.get(input_id, "HDMI")

    async def _async_select_tv_audio(self):
        """Only explicit HDMI selection can request TV audio; disabled by default."""
        if (
            not self._config_entry.options.get("sonos_select_tv_source", False)
            or not self._sound_player
        ):
            return
        # A sound-system failure must not roll back a successful HDMI selection.
        await self._async_call_volume_service(
            "select_source",
            source=self._config_entry.options.get("sonos_tv_source", "TV"),
        )
