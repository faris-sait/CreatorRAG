"""URL parsing/canonicalization — single source of truth.

Previously these regexes lived in three files. Centralized so YouTube/Instagram
id extraction and canonicalization behave identically everywhere.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")
IG_CODE_RE = re.compile(r"instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)")


def detect_platform(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "instagram.com" in host:
        return "instagram"
    raise ValueError(f"Unsupported URL host: {host!r}")


def youtube_id(url: str) -> str | None:
    m = YT_ID_RE.search(url)
    return m.group(1) if m else None


def instagram_shortcode(url: str) -> str | None:
    m = IG_CODE_RE.search(url)
    return m.group(1) if m else None


def canonical_url(url: str) -> str:
    """Rebuild a clean URL from the extracted id/shortcode.

    Pasted input is often messy (trailing junk, two URLs glued together,
    tracking params). Scrapers choke on that — so we extract the canonical id and
    reconstruct a pristine URL for dedup, the Data API, and Apify actors.
    """
    url = url.strip()
    platform = detect_platform(url)
    if platform == "youtube":
        vid = youtube_id(url)
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    elif platform == "instagram":
        code = instagram_shortcode(url)
        if code:
            return f"https://www.instagram.com/reel/{code}/"
    return url
