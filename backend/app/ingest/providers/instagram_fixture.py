"""Instagram fixture provider — the demo kill-switch.

Serves a cached reel (metadata + pre-transcribed segments) from
backend/fixtures/instagram/. Used when USE_FIXTURES=true, or automatically by
the factory when live Apify fails. This guarantees the live demo never hard-
fails on an Instagram block — a deliberate reliability choice for a flaky
third-party dependency.

Fixture file: backend/fixtures/instagram/<shortcode>.json, falling back to
default.json. Shape mirrors VideoData fields plus `transcript_segments`.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...urls import instagram_shortcode as _shortcode
from .base import VideoData, VideoProvider

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "instagram"


def fixture_exists(url: str) -> bool:
    code = _shortcode(url)
    if code and (FIXTURE_DIR / f"{code}.json").exists():
        return True
    return (FIXTURE_DIR / "default.json").exists()


class InstagramFixtureProvider(VideoProvider):
    async def fetch(self, url: str) -> VideoData:
        code = _shortcode(url)
        path = FIXTURE_DIR / f"{code}.json" if code else None
        if not path or not path.exists():
            path = FIXTURE_DIR / "default.json"
        if not path.exists():
            raise RuntimeError(
                "No Instagram fixture available. Add backend/fixtures/instagram/"
                "default.json or set USE_FIXTURES=false with a valid APIFY_TOKEN."
            )
        raw = json.loads(path.read_text())

        data = VideoData(
            platform="instagram",
            title=raw.get("title", "Instagram Reel"),
            creator=raw.get("creator", ""),
            follower_count=raw.get("follower_count"),
            views=raw.get("views"),
            likes=raw.get("likes"),
            comments=raw.get("comments"),
            hashtags=raw.get("hashtags", []),
            upload_date=raw.get("upload_date"),
            duration=raw.get("duration"),
            thumbnail=raw.get("thumbnail"),
            transcript_segments=raw.get("transcript_segments"),
            source=f"instagram:fixture({path.name})",
        )
        # A fixture may instead point at a local audio file for Whisper.
        if not data.transcript_segments and raw.get("audio_file"):
            audio = FIXTURE_DIR.parent / "audio" / raw["audio_file"]
            data.audio_path = str(audio)
        return data
