"""Image fetching for thumbnails (proxy + persistence).

CDN images (esp. Instagram) block hotlinking and use time-signed URLs that
expire. We fetch them server-side — for the live proxy and to persist a copy at
ingest so cards keep working after the signed URL dies.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

# Allowlisted CDN hosts (prevents this from becoming an open proxy / SSRF).
IMG_HOSTS = (
    "cdninstagram.com",
    "fbcdn.net",
    "ytimg.com",
    "ggpht.com",
    "googleusercontent.com",
)


def host_allowed(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in IMG_HOSTS)


async def fetch_image(url: str) -> tuple[bytes, str] | None:
    """Return (bytes, content_type) for an allowlisted image URL, or None."""
    if not url or not host_allowed(url):
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"},
            )
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "image/jpeg")
    except Exception:  # noqa: BLE001
        return None
