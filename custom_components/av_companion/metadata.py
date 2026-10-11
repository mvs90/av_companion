"""Independent app-name/artwork fallbacks for the actually selected player."""

from hashlib import sha256

from .app_artwork import get_app_artwork


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


class PlaybackMetadata:
    @property
    def _app_metadata(self):
        target = self._playback_target
        state = self.hass.states.get(target) if target else None
        if (
            not state
            or self._state == "off"
            or state.state not in {"on", "playing", "paused", "idle", "buffering"}
            or state.attributes.get("restored")
        ):
            return None
        name = _text(state.attributes.get("app_name"))
        app_id = _text(state.attributes.get("app_id"))
        if not (name or app_id):
            return None
        return target, app_id or "", name or app_id, state

    @property
    def app_name(self):
        app = self._app_metadata
        return app[2] if app else None

    @property
    def app_id(self):
        app = self._app_metadata
        return app[1] or None if app else None

    @property
    def media_title(self):
        return _text(self._playback_attribute("media_title")) or self.app_name

    @property
    def media_artist(self):
        artist = _text(self._playback_attribute("media_artist"))
        app = self._app_metadata
        if artist or not app:
            return artist
        if _text(self._playback_attribute("media_title")) and _text(
            self._playback_attribute("entity_picture")
        ):
            return None
        # Keep the reported state: Netflix idle is not proof of pause/playback.
        de = str(getattr(self.hass.config, "language", "")).startswith("de")
        labels = {
            "playing": ("Wiedergabe", "Playing"),
            "paused": ("Pausiert", "Paused"),
            "idle": ("Leerlauf", "Idle"),
            "buffering": ("Lädt", "Buffering"),
            "on": ("Eingeschaltet", "On"),
        }
        return labels[app[3].state][0 if de else 1]

    @property
    def media_image_url(self):
        if image := _text(self._playback_attribute("entity_picture")):
            return image
        if app := self._app_metadata:
            key = sha256("|".join(app[:3]).encode()).hexdigest()[:24]
            # Used only as HA image identity. The proxy below supplies the bytes.
            return f"av-companion-app://{key}"
        return None

    async def async_get_media_image(self):
        target_id = self._playback_target
        if _text(self._playback_attribute("entity_picture")):
            component = self.hass.data.get("media_player")
            target = (
                component.get_entity(target_id) if component and target_id else None
            )
            if target is None or target is self:
                return None, None
            return await target.async_get_media_image()
        app = self._app_metadata
        if not app:
            return None, None
        result = await get_app_artwork(self.hass).async_image(app[1], app[2])
        current = self._app_metadata
        if not current or current[:3] != app[:3]:
            return None, None
        if _text(self._playback_attribute("entity_picture")):
            # Real artwork arrived during the lookup; never return the old icon.
            return await self.async_get_media_image()
        return result
