"""Small, bounded, persistent icons; untrusted lookup and cache failure handling."""

import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest
from PIL import Image
from custom_components.av_companion.app_artwork import (
    AppArtwork,
    _badge,
    _icon_url,
    _png,
)


@pytest.fixture
def cache():
    hass = Mock(data={})
    hass.config.country = "DE"

    async def executor(fn, *args):
        return fn(*args)

    hass.async_add_executor_job.side_effect = executor
    store = SimpleNamespace(
        async_load=AsyncMock(return_value=None), async_delay_save=Mock()
    )
    with patch("custom_components.av_companion.app_artwork.Store", return_value=store):
        return AppArtwork(hass)


async def test_concurrent_lookup_once_and_persistent_offline_hit(cache):
    logo = _badge("Netflix")
    cache._lookup = AsyncMock(return_value=logo)
    result = await asyncio.gather(
        *(cache.async_image("com.netflix.Netflix", "Netflix") for _ in range(4))
    )
    assert all(r == (logo, "image/png") for r in result)
    cache._lookup.assert_awaited_once()
    save = cache._store.async_delay_save.call_args.args[0]()
    assert base64.b64decode(save["com.netflix.Netflix"]) == logo
    cache._icons.clear()
    cache._loaded = False
    cache._store.async_load.return_value = save
    cache._lookup.reset_mock()
    assert await cache.async_image("com.netflix.Netflix", "Netflix") == (
        logo,
        "image/png",
    )
    cache._lookup.assert_not_awaited()


async def test_failed_lookup_bounded_negative_cache_and_valid_badge(cache):
    cache._lookup = AsyncMock(side_effect=TimeoutError)
    image, kind = await cache.async_image("com.example.App", "Example")
    assert kind == "image/png"
    assert Image.open(BytesIO(image)).size == (256, 256)
    await cache.async_image("com.example.App", "Example")
    cache._lookup.assert_awaited_once()
    for i in range(40):
        await cache.async_image(f"com.app.{i}", str(i))
    assert len(cache._failed) == 32
    cache._store.async_delay_save.assert_not_called()


async def test_positive_cache_bounded(cache):
    cache._lookup = AsyncMock(return_value=_badge("App"))
    for i in range(40):
        await cache.async_image(f"com.app.{i}", str(i))
    assert len(cache._icons) == 32


@pytest.mark.parametrize(
    "url",
    [
        "http://is1-ssl.mzstatic.com/a",
        "https://evil.test/logo",
        "https://mzstatic.com.evil.test/a",
        "https://evil@is1-ssl.mzstatic.com/a",
        "https://is1-ssl.mzstatic.com:8000/a",
        "https://is1-ssl.mzstatic.com:invalid/a",
        None,
    ],
)
def test_only_https_apple_cdn(url):
    assert _icon_url(url) is None


async def test_lookup_exact_bundle_match_not_first_search_result(cache):
    import json

    logo = _badge("Netflix")
    cache._read = AsyncMock(
        side_effect=[
            json.dumps(
                {
                    "results": [
                        {
                            "bundleId": "com.fake.App",
                            "artworkUrl512": "https://is1-ssl.mzstatic.com/wrong",
                        },
                        {
                            "bundleId": "com.netflix.Netflix",
                            "artworkUrl512": "https://is1-ssl.mzstatic.com/right",
                        },
                    ]
                }
            ).encode(),
            logo,
        ]
    )
    assert await cache._lookup("com.netflix.Netflix") == _png(logo)
    assert cache._read.await_args_list[1].args[0].endswith("/right")
    assert cache._read.await_args_list[0].kwargs["params"] == {
        "bundleId": "com.netflix.Netflix",
        "country": "de",
    }


async def test_no_match_does_not_download_other_apps(cache):
    cache._read = AsyncMock(
        return_value=b'{"results": [{"bundleId":"wrong","artworkUrl512":"https://is1-ssl.mzstatic.com/a"}]}'
    )
    assert await cache._lookup("com.netflix.Netflix") is None
    assert cache._read.await_count == 1
    assert await cache._lookup("not a bundle/url") is None
    assert cache._read.await_count == 1


def test_reject_invalid_image():
    with pytest.raises(OSError):
        _png(b"<html>404</html>")
