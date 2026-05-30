import pytest

from app.config import settings
from app.ingest.providers.factory import get_provider
from app.ingest.providers.instagram_fixture import (
    InstagramFixtureProvider,
    fixture_exists,
)
from app.ingest.providers.youtube import YouTubeProvider


def test_factory_routes_youtube_to_ytprovider_without_apify(monkeypatch):
    # No Apify (or apify disabled) → the Data API / yt-dlp provider.
    monkeypatch.setattr(settings, "youtube_use_apify", False)
    p = get_provider("https://www.youtube.com/watch?v=abc12345678")
    assert isinstance(p, YouTubeProvider)


def test_factory_routes_youtube_to_apify_when_enabled(monkeypatch):
    from app.ingest.providers.factory import _YouTubeApifyWithFallback

    monkeypatch.setattr(settings, "youtube_use_apify", True)
    monkeypatch.setattr(settings, "apify_token", "fake-token")
    p = get_provider("https://www.youtube.com/watch?v=abc12345678")
    assert isinstance(p, _YouTubeApifyWithFallback)


def test_factory_uses_fixture_for_instagram_in_fixture_mode(monkeypatch):
    monkeypatch.setattr(settings, "use_fixtures", True)
    p = get_provider("https://www.instagram.com/reel/CtjUklXt5Vp/")
    assert isinstance(p, InstagramFixtureProvider)


def test_default_fixture_exists():
    assert fixture_exists("https://www.instagram.com/reel/anything/")


@pytest.mark.asyncio
async def test_fixture_provider_returns_segments_and_metadata():
    data = await InstagramFixtureProvider().fetch(
        "https://www.instagram.com/reel/whatever/"
    )
    assert data.platform == "instagram"
    assert data.creator  # non-empty
    assert data.transcript_segments and len(data.transcript_segments) > 0
    # segments carry timestamps used for citations
    assert "text" in data.transcript_segments[0]
    assert data.views and data.views > 0
