"""Instagram provider via Apify — the make-or-break source.

Instagram in 2026 blocks anonymous scraping and yt-dlp does NOT return the
creator's follower count. Apify is the reliable path:

  1. apify/instagram-scraper  → reel metrics + a direct media URL (for Whisper)
  2. apify/instagram-profile-scraper → the owner's follower count

Two calls because the reel scraper gives engagement metrics but not the
creator's follower count; the profile scraper fills that gap. If anything here
fails, the factory falls back to the cached fixture so the demo survives.
"""
from __future__ import annotations

import asyncio
from typing import Any

from apify_client import ApifyClient

from ...config import settings
from .base import VideoData, VideoProvider


def _run_actor(actor: str, run_input: dict) -> list[dict[str, Any]]:
    client = ApifyClient(settings.apify_token)
    run = client.actor(actor).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return items


def _hashtags_from_caption(caption: str) -> list[str]:
    return [w[1:] for w in (caption or "").split() if w.startswith("#")][:30]


class InstagramApifyProvider(VideoProvider):
    async def fetch(self, url: str) -> VideoData:
        if not settings.apify_token:
            raise RuntimeError("APIFY_TOKEN not set")

        items = await asyncio.to_thread(
            _run_actor,
            "apify/instagram-scraper",
            {"directUrls": [url], "resultsType": "posts", "resultsLimit": 1,
             "addParentData": False},
        )
        if not items:
            raise RuntimeError("Apify returned no items for reel")
        it = items[0]

        creator = it.get("ownerUsername") or ""
        caption = it.get("caption") or ""
        data = VideoData(
            platform="instagram",
            title=(caption[:80] or "Instagram Reel"),
            creator=creator,
            views=it.get("videoViewCount") or it.get("videoPlayCount"),
            likes=it.get("likesCount"),
            comments=it.get("commentsCount"),
            hashtags=it.get("hashtags") or _hashtags_from_caption(caption),
            # Apify returns a full ISO timestamp (2026-04-05T18:03:53.000Z);
            # trim to YYYY-MM-DD for consistency with the YouTube provider.
            upload_date=(it.get("timestamp") or "")[:10] or None,
            duration=int(it["videoDuration"]) if it.get("videoDuration") else None,
            thumbnail=it.get("displayUrl"),
            audio_url=it.get("videoUrl"),  # direct CDN media → Whisper
            source="instagram:apify",
        )

        # Second call: creator follower count.
        if creator:
            try:
                profs = await asyncio.to_thread(
                    _run_actor, "apify/instagram-profile-scraper",
                    {"usernames": [creator]},
                )
                if profs:
                    data.follower_count = profs[0].get("followersCount")
            except Exception:
                pass  # follower count is nice-to-have; don't fail the whole fetch
        return data
