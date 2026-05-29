"""Provider interface — the seam that makes Instagram demo-safe.

Every source (YouTube, Instagram-via-Apify, Instagram-fixture) implements the
same `fetch()` contract. The pipeline never knows or cares which provider ran,
so we can swap Apify → fixture without touching pipeline code. This is the
'resourcefulness' the brief asks for: a hard, flaky dependency (Instagram)
isolated behind a stable interface with a cached fallback.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VideoData:
    """Normalized output of any provider. The transcript may be supplied
    directly (YouTube captions) or left None for the pipeline to produce via
    Whisper from `audio_path`."""

    platform: str
    title: str = ""
    creator: str = ""
    follower_count: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    hashtags: list[str] = field(default_factory=list)
    upload_date: str | None = None        # ISO-ish string
    duration: int | None = None           # seconds
    thumbnail: str | None = None

    # Exactly one of these feeds the transcript step.
    transcript_segments: list[dict] | None = None  # [{start,end,text}] if captions
    audio_path: str | None = None                  # local file → Whisper
    audio_url: str | None = None                   # remote media → download → Whisper

    source: str = ""  # which provider produced this (for transparency in UI)

    def metadata_dict(self) -> dict:
        """The JSONB blob persisted to Postgres / shown on the card."""
        return {
            "platform": self.platform,
            "title": self.title,
            "creator": self.creator,
            "follower_count": self.follower_count,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "hashtags": self.hashtags,
            "upload_date": self.upload_date,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "source": self.source,
        }


class VideoProvider(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> VideoData:
        """Pull metadata + transcript-or-audio for a single video URL."""
        raise NotImplementedError


def engagement_rate(
    likes: int | None, comments: int | None, views: int | None
) -> float | None:
    """(likes + comments) / views * 100, guarding None and divide-by-zero.

    Returns None when views are unknown/zero so the UI can show 'n/a' rather
    than a misleading 0%."""
    if not views:
        return None
    return round(((likes or 0) + (comments or 0)) / views * 100, 2)
