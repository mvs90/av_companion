"""Fallback matrix, automatic recovery and asynchronous artwork races."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.core import State


def source(player, **attributes):
    player.hass.config.language = "de"
    attrs = {"app_name": "Netflix", "app_id": "com.netflix.Netflix", **attributes}
    player._test_states["media_player.apple_tv"] = State(
        "media_player.apple_tv", "playing", attrs
    )


@pytest.mark.parametrize("title", [None, "", "   ", "Film"])
@pytest.mark.parametrize("cover", [None, "", "/api/artwork/real"])
def test_title_and_art_are_independent_and_real_data_always_win(player, title, cover):
    source(player, media_title=title, entity_picture=cover)
    assert player.media_title == ("Film" if title == "Film" else "Netflix")
    assert (
        player.media_image_url == cover
        if cover
        else player.media_image_url.startswith("av-companion-app://")
    )
    assert player.media_artist == (None if title == "Film" and cover else "Wiedergabe")
    assert player.app_name == "Netflix"
    assert player.app_id == "com.netflix.Netflix"
    assert player.media_duration is None
    source(
        player,
        media_title="Real film",
        media_artist="Real artist",
        entity_picture="/real",
    )
    assert (player.media_title, player.media_artist, player.media_image_url) == (
        "Real film",
        "Real artist",
        "/real",
    )


@pytest.mark.parametrize(
    "status,label",
    [
        ("paused", "Pausiert"),
        ("idle", "Leerlauf"),
        ("buffering", "Lädt"),
        ("on", "Eingeschaltet"),
    ],
)
def test_reported_playback_status_not_inferred(player, status, label):
    source(player)
    old = player._test_states["media_player.apple_tv"]
    player._test_states[old.entity_id] = State(
        old.entity_id, status, dict(old.attributes)
    )
    assert player.media_artist == label


@pytest.mark.parametrize(
    "guard",
    [
        "off",
        "standby",
        "unknown",
        "unavailable",
        "restored",
        "display_off",
        "presentation",
    ],
)
def test_no_app_fallback_when_inactive_or_unrelated(player, guard):
    source(player, restored=guard == "restored")
    old = player._test_states["media_player.apple_tv"]
    if guard in {"off", "standby", "unknown", "unavailable"}:
        player._test_states[old.entity_id] = State(
            old.entity_id, guard, dict(old.attributes)
        )
    if guard == "display_off":
        player._state = "off"
    if guard == "presentation":
        player._lg_display.presentation_active = True
    assert player.app_name is None
    assert player.media_title is None
    assert player.media_image_url is None


async def test_artwork_changes_back_to_real_without_reloading(player):
    source(player)
    original = player.media_image_url
    cache = SimpleNamespace(async_image=AsyncMock(return_value=(b"logo", "image/png")))
    with patch(
        "custom_components.av_companion.metadata.get_app_artwork", return_value=cache
    ):
        assert await player.async_get_media_image() == (b"logo", "image/png")
    real = SimpleNamespace(
        async_get_media_image=AsyncMock(return_value=(b"real", "image/jpeg"))
    )
    player.hass.data["media_player"] = SimpleNamespace(get_entity=lambda _: real)
    source(player, media_title="Film", entity_picture="/real")
    assert await player.async_get_media_image() == (b"real", "image/jpeg")
    source(player, app_name="YouTube", app_id="com.google.ios.youtube")
    assert player.media_image_url != original


@pytest.mark.parametrize("change_to", ["other_app", "real_art", "off", "sonos"])
async def test_slow_logo_lookup_cannot_overwrite_new_source_or_cover(player, change_to):
    source(player)
    real = SimpleNamespace(
        async_get_media_image=AsyncMock(return_value=(b"real", "image/jpeg"))
    )
    player.hass.data["media_player"] = SimpleNamespace(get_entity=lambda _: real)

    async def image(*args):
        if change_to == "other_app":
            source(player, app_name="TV", app_id="com.apple.TVWatchList")
        elif change_to == "real_art":
            source(player, media_title="Film", entity_picture="/real")
        elif change_to == "off":
            player._state = "off"
        else:
            player._config_entry.options["linked_volume_media_player_entity_id"] = (
                "media_player.sonos"
            )
            player._test_states["media_player.sonos"] = State(
                "media_player.sonos",
                "playing",
                {"media_title": "Song", "entity_picture": "/sonos"},
            )
        return b"logo", "image/png"

    with patch(
        "custom_components.av_companion.metadata.get_app_artwork",
        return_value=SimpleNamespace(async_image=image),
    ):
        assert await player.async_get_media_image() == (
            (b"real", "image/jpeg") if change_to == "real_art" else (None, None)
        )
    if change_to == "sonos":
        assert player.media_title == "Song"
        assert player.app_name is None
        assert player.media_image_url == "/sonos"


def test_real_artist_never_overwritten(player):
    source(player, media_artist="Artist")
    assert player.media_artist == "Artist"
