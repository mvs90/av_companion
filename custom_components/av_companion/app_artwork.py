"""On-demand App Store icons; bounded local cache, no media history sent online."""

from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from io import BytesIO
import json
import re
import time
from urllib.parse import urlsplit

from aiohttp import ClientError
from PIL import Image, ImageDraw, ImageFont
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

_MAX_ICONS = 32
_MAX_IMAGE = 2 * 1024 * 1024
_CACHE_KEY = "av_companion_app_artwork"


def _png(data: bytes) -> bytes:
    with Image.open(BytesIO(data)) as image:
        if (
            image.format not in {"PNG", "JPEG", "WEBP"}
            or image.width * image.height > 4_194_304
        ):
            raise ValueError("Unsupported app icon")
        image.thumbnail((256, 256))
        output = BytesIO()
        image.convert("RGBA").save(output, "PNG")
        return output.getvalue()


def _badge(name: str) -> bytes:
    image = Image.new("RGB", (256, 256), "#202938")
    draw = ImageDraw.Draw(image)
    text = "".join(c for c in name if c.isascii() and c.isalnum())[:2].upper() or "TV"
    draw.text(
        (128, 128),
        text,
        fill="#ffffff",
        font=ImageFont.load_default(size=80),
        anchor="mm",
    )
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _icon_url(value):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if (
            url.scheme == "https"
            and host.endswith(".mzstatic.com")
            and not url.username
            and not url.password
            and url.port in {None, 443}
        ):
            return value
    except ValueError:
        pass
    return None


class AppArtwork:
    def __init__(self, hass):
        self.hass = hass
        self._store = Store(hass, 1, _CACHE_KEY)
        self._loaded = False
        self._icons = OrderedDict()
        self._failed = OrderedDict()
        self._lock = asyncio.Lock()

    async def _read(self, url, limit, **kwargs):
        async with async_get_clientsession(self.hass).get(
            url, allow_redirects=False, **kwargs
        ) as response:
            if response.status != 200:
                raise ValueError("App artwork unavailable")
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("App artwork too large")
            return bytes(data)

    async def _lookup(self, app_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", app_id):
            return None
        country = getattr(self.hass.config, "country", None)
        if not isinstance(country, str) or not re.fullmatch(r"[a-zA-Z]{2}", country):
            country = "US"
        data = json.loads(
            await self._read(
                "https://itunes.apple.com/lookup",
                512_000,
                params={"bundleId": app_id, "country": country.lower()},
            )
        )
        for result in data.get("results", []):
            if isinstance(result, dict) and result.get("bundleId") == app_id:
                url = _icon_url(result.get("artworkUrl512")) or _icon_url(
                    result.get("artworkUrl100")
                )
                if url:
                    raw = await self._read(url, _MAX_IMAGE)
                    return await self.hass.async_add_executor_job(_png, raw)
        return None

    async def async_image(self, app_id: str, name: str):
        # Serializing the few cache misses also coalesces concurrent HA/Studio
        # requests. Hits need no network, periodic task, or device CPU work.
        async with self._lock:
            if not self._loaded:
                data = await self._store.async_load() or {}
                for key, value in list(data.items())[-_MAX_ICONS:]:
                    try:
                        raw = base64.b64decode(value, validate=True)
                        if len(raw) <= 300_000:
                            self._icons[key] = raw
                    except (ValueError, TypeError):
                        continue
                self._loaded = True
            key = app_id or name
            if key in self._icons:
                self._icons.move_to_end(key)
                return self._icons[key], "image/png"
            if key in self._failed and time.monotonic() < self._failed[key][0]:
                return self._failed[key][1], "image/png"
            icon = None
            try:
                async with asyncio.timeout(6):
                    icon = await self._lookup(app_id)
            except (
                ClientError,
                TimeoutError,
                ValueError,
                OSError,
                TypeError,
                AttributeError,
            ):
                pass
            if icon:
                self._icons[key] = icon
                while len(self._icons) > _MAX_ICONS:
                    self._icons.popitem(last=False)
                self._failed.pop(key, None)
                self._store.async_delay_save(
                    lambda: {
                        k: base64.b64encode(v).decode("ascii")
                        for k, v in self._icons.items()
                    },
                    10,
                )
            else:
                icon = await self.hass.async_add_executor_job(_badge, name)
                self._failed[key] = (time.monotonic() + 3600, icon)
                while len(self._failed) > _MAX_ICONS:
                    self._failed.popitem(last=False)
            return icon, "image/png"


def get_app_artwork(hass):
    if _CACHE_KEY not in hass.data:
        hass.data[_CACHE_KEY] = AppArtwork(hass)
    return hass.data[_CACHE_KEY]
