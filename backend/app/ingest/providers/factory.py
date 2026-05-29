"""Provider selection + Instagram fallback policy.

Routing:
  youtube.com / youtu.be      → YouTubeProvider
  instagram.com               → Apify, with automatic fixture fallback
                                 (or fixtures directly when USE_FIXTURES=true)
"""
from __future__ import annotations

import logging

from ...config import settings
from ...urls import canonical_url, detect_platform  # noqa: F401 (re-exported)
from .base import VideoData, VideoProvider
from .instagram_apify import InstagramApifyProvider
from .instagram_fixture import InstagramFixtureProvider, fixture_exists
from .youtube import YouTubeProvider
from .youtube_apify import YouTubeApifyProvider

log = logging.getLogger("creatorrag.providers")


class _ApifyWithFixtureFallback(VideoProvider):
    """Try Apify; on any failure, fall back to a cached fixture if one exists.
    Keeps a live demo alive when Instagram blocks the scraper."""

    async def fetch(self, url: str) -> VideoData:
        try:
            return await InstagramApifyProvider().fetch(url)
        except Exception as e:  # noqa: BLE001 — fallback is the whole point
            log.warning("Apify failed (%s); falling back to fixture", e)
            if fixture_exists(url):
                return await InstagramFixtureProvider().fetch(url)
            raise


class _YouTubeApifyWithFallback(VideoProvider):
    """Apify-first YouTube; fall back to the Data API / yt-dlp path on failure."""

    async def fetch(self, url: str) -> VideoData:
        try:
            return await YouTubeApifyProvider().fetch(url)
        except Exception as e:  # noqa: BLE001
            log.warning("Apify YouTube failed (%s); falling back to Data API/yt-dlp", e)
            return await YouTubeProvider().fetch(url)


def get_provider(url: str, youtube_exact: bool = False) -> VideoProvider:
    platform = detect_platform(url)
    if platform == "youtube":
        # youtube_exact forces the SRT actor (exact timestamps, slower).
        use_apify = settings.has_apify and (settings.youtube_use_apify or youtube_exact)
        if use_apify:
            return _YouTubeApifyWithFallback()
        return YouTubeProvider()
    # instagram
    if settings.use_fixtures or not settings.has_apify:
        return InstagramFixtureProvider()
    return _ApifyWithFixtureFallback()
