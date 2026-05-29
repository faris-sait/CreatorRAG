"""YouTube provider via Apify (single actor: metadata + transcript).

Uses `streamers/youtube-scraper`, which returns full metadata (views, likes,
comments, subscriber count, duration, hashtags) AND SRT subtitles with real
timestamps — all in one call, running on Apify's IPs so it works from blocked
datacenter IPs. This is the "Apify-only" YouTube path, consistent with how
Instagram is handled.
"""
from __future__ import annotations

import asyncio
import re

from apify_client import ApifyClient

from ...config import settings
from .base import VideoData, VideoProvider

_ACTOR = "streamers/youtube-scraper"


def _hms_to_seconds(s: str | None) -> int | None:
    """'00:02:36' or '2:36' → seconds."""
    if not s:
        return None
    try:
        parts = [int(x) for x in s.split(":")]
    except ValueError:
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _srt_ts(s: str) -> float | None:
    """'00:00:04,980' → 4.98 seconds."""
    s = s.strip().replace(",", ".")
    try:
        h, m, rest = s.split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)
    except (ValueError, AttributeError):
        return None


def _parse_srt(srt: str) -> list[dict]:
    """SRT text → [{start, end, text}] (skips empty/overlap blocks)."""
    segs: list[dict] = []
    for block in re.split(r"\n\s*\n", (srt or "").strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        tline = next((ln for ln in lines if "-->" in ln), None)
        if not tline:
            continue
        text = " ".join(lines[lines.index(tline) + 1 :]).strip()
        if not text:
            continue
        a, _, b = tline.partition("-->")
        segs.append({"start": _srt_ts(a), "end": _srt_ts(b), "text": text})
    return segs


def _pick_subtitles(subs) -> str | None:
    """Choose the best subtitle track's SRT text (prefer English)."""
    if not isinstance(subs, list):
        return None
    tracks = [s for s in subs if s.get("srt")]
    if not tracks:
        return None
    en = [s for s in tracks if (s.get("language") or "").lower().startswith("en")]
    return (en[0] if en else tracks[0]).get("srt")


def _run(url: str) -> dict:
    client = ApifyClient(settings.apify_token)
    run = client.actor(_ACTOR).call(
        run_input={
            "startUrls": [{"url": url}],
            "maxResults": 1,
            "maxResultsShorts": 0,
            "maxResultStreams": 0,
            "subtitles": True,
            "downloadSubtitles": True,
            "saveSubsToKVS": False,
        }
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        raise RuntimeError("Apify youtube-scraper returned no items")
    return items[0]


class YouTubeApifyProvider(VideoProvider):
    async def fetch(self, url: str) -> VideoData:
        if not settings.apify_token:
            raise RuntimeError("APIFY_TOKEN not set")
        it = await asyncio.to_thread(_run, url)

        data = VideoData(
            platform="youtube",
            title=it.get("title") or "",
            creator=it.get("channelName") or "",
            follower_count=it.get("numberOfSubscribers"),
            views=it.get("viewCount"),
            likes=it.get("likes"),
            comments=it.get("commentsCount"),
            hashtags=list(it.get("hashtags") or [])[:30],
            upload_date=(it.get("date") or "")[:10] or None,
            duration=_hms_to_seconds(it.get("duration")),
            thumbnail=it.get("thumbnailUrl"),
            source="youtube:apify",
        )

        srt = _pick_subtitles(it.get("subtitles"))
        segments = _parse_srt(srt) if srt else None
        if segments:
            data.transcript_segments = segments
            data.source += "+srt"
        else:
            # No subtitles available — leave transcript empty; the pipeline will
            # error cleanly rather than fabricate one.
            data.source += "+no-transcript"
        return data
