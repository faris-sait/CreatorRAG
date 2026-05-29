"""YouTube provider — deployment-safe.

Cloud/datacenter IPs are blocked by YouTube, so we avoid scraping it directly:

  metadata  → YouTube Data API v3 (official, reliable from any IP, free tier).
              Falls back to yt-dlp when no API key is set (local dev).
  transcript→ youtube-transcript-api through a residential proxy (Webshare or a
              generic proxy URL), falling back to yt-dlp audio + Whisper (also
              proxied). Captions are tried first; Whisper covers caption-less
              videos.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

from ...config import settings
from ...urls import youtube_id as _video_id
from .base import VideoData, VideoProvider

DATA_API = "https://www.googleapis.com/youtube/v3"

TMP_DIR = Path(__file__).resolve().parents[3] / "tmp"
TMP_DIR.mkdir(exist_ok=True)

# Player clients that often get past datacenter-IP bot checks. yt-dlp tries them
# in order; cookies (if provided) are the most reliable bypass.
_PLAYER_CLIENTS = ["tv", "web_safari", "android", "ios", "web"]


def _common_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": _PLAYER_CLIENTS}},
    }
    if settings.ytdlp_cookies_file:
        opts["cookiefile"] = settings.ytdlp_cookies_file
    if settings.youtube_proxy_url:
        opts["proxy"] = settings.youtube_proxy_url
    return opts


def _proxy_config():
    """Proxy for youtube-transcript-api (Webshare preferred, else generic)."""
    if settings.webshare_proxy_username and settings.webshare_proxy_password:
        return WebshareProxyConfig(
            proxy_username=settings.webshare_proxy_username,
            proxy_password=settings.webshare_proxy_password,
        )
    if settings.youtube_proxy_url:
        return GenericProxyConfig(
            http_url=settings.youtube_proxy_url,
            https_url=settings.youtube_proxy_url,
        )
    return None


def _iso8601_to_seconds(s: str | None) -> int | None:
    if not s:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def _metadata_via_data_api(video_id: str) -> dict:
    """Official YouTube Data API v3 — works from any IP, no bot checks.

    Returns a dict shaped like yt-dlp's so the rest of fetch() is unchanged.
    """
    key = settings.youtube_api_key
    with httpx.Client(timeout=20) as c:
        vr = c.get(
            f"{DATA_API}/videos",
            params={"part": "snippet,statistics,contentDetails", "id": video_id, "key": key},
        )
        vr.raise_for_status()
        items = vr.json().get("items") or []
        if not items:
            raise RuntimeError(f"YouTube Data API: video {video_id} not found")
        it = items[0]
        sn, st, cd = it["snippet"], it.get("statistics", {}), it.get("contentDetails", {})

        subs = None
        channel_id = sn.get("channelId")
        if channel_id:
            cr = c.get(
                f"{DATA_API}/channels",
                params={"part": "statistics", "id": channel_id, "key": key},
            )
            if cr.is_success and (citems := cr.json().get("items")):
                sc = citems[0].get("statistics", {}).get("subscriberCount")
                subs = int(sc) if sc is not None else None

    def _int(v):
        return int(v) if v is not None else None

    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    return {
        "id": video_id,
        "title": sn.get("title", ""),
        "channel": sn.get("channelTitle", ""),
        "channel_follower_count": subs,
        "view_count": _int(st.get("viewCount")),
        "like_count": _int(st.get("likeCount")),
        "comment_count": _int(st.get("commentCount")),
        "upload_date": (sn.get("publishedAt") or "")[:10] or None,  # YYYY-MM-DD
        "duration": _iso8601_to_seconds(cd.get("duration")),
        "tags": sn.get("tags", []),
        "thumbnail": thumb,
    }


def _extract_metadata(url: str) -> dict:
    """Data API when a key is configured (deploy-safe); else yt-dlp (local)."""
    if settings.youtube_api_key:
        vid = _video_id(url)
        if not vid:
            raise ValueError(f"Could not parse YouTube video id from {url!r}")
        return _metadata_via_data_api(vid)
    opts = {**_common_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_audio(url: str, video_id: str) -> str:
    out = str(TMP_DIR / f"yt_{video_id}.%(ext)s")
    opts = {
        **_common_opts(),
        "format": "bestaudio/best",
        "outtmpl": out,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "5"}
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    return str(TMP_DIR / f"yt_{video_id}.mp3")


def _approx_segments(
    text: str, total_duration: int | None, words_per_seg: int = 30
) -> list[dict]:
    """Plain transcript text → pseudo-segments with approximate timestamps.

    Apify's transcript actor returns plain text (and auto-captions often have no
    punctuation), so we window the text into ~fixed word counts and spread the
    known video duration across them by word position. Chunk citations then show
    a sensible, increasing [Video A @ m:ss] instead of everything at 0:00.
    """
    words = text.split()
    if not words:
        return []
    total = len(words)
    segs: list[dict] = []
    for i in range(0, total, words_per_seg):
        window = words[i : i + words_per_seg]
        start = (i / total * total_duration) if total_duration else None
        end = (min(i + words_per_seg, total) / total * total_duration) if total_duration else None
        segs.append({"start": start, "end": end, "text": " ".join(window)})
    return segs


def _transcript_via_apify(url: str, total_duration: int | None) -> list[dict] | None:
    """Fetch a YouTube transcript via an Apify actor (runs on Apify IPs, so it
    works from blocked datacenter IPs). Returns approximate-timed segments."""
    if not settings.apify_token:
        return None
    from apify_client import ApifyClient

    client = ApifyClient(settings.apify_token)
    run = client.actor(settings.apify_yt_transcript_actor).call(
        run_input={"startUrls": [url], "includeTimestamps": "Yes"}
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        return None
    it = items[0]
    # actor returns transcript either as a timestamped list or plain `text`
    t = it.get("transcript")
    if isinstance(t, list) and t:
        segs = []
        for s in t:
            ts = s.get("timestamp")
            segs.append({"start": _ts_to_seconds(ts), "end": None, "text": s.get("text", "")})
        return segs or None
    text = it.get("text") or (t if isinstance(t, str) else "")
    return _approx_segments(text, total_duration) if text else None


def _ts_to_seconds(ts: str | None) -> float | None:
    if not ts:
        return None
    parts = [int(x) for x in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])


def _fetch_captions(video_id: str) -> list[dict] | None:
    """v1 instance API (proxied on cloud). Returns [{start,end,text}] or None."""
    try:
        api = YouTubeTranscriptApi(proxy_config=_proxy_config())
        fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return None
    except Exception:
        # IP blocks on datacenter ranges land here — fall back to Whisper.
        return None
    segments = []
    for snip in fetched:
        segments.append(
            {"start": snip.start, "end": snip.start + snip.duration, "text": snip.text}
        )
    return segments or None


def _normalize_date(d: str | None) -> str | None:
    # yt-dlp gives YYYYMMDD
    if d and len(d) == 8 and d.isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return d


class YouTubeProvider(VideoProvider):
    async def fetch(self, url: str) -> VideoData:
        info = await asyncio.to_thread(_extract_metadata, url)
        video_id = _video_id(url) or info.get("id")

        data = VideoData(
            platform="youtube",
            title=info.get("title") or "",
            creator=info.get("channel") or info.get("uploader") or "",
            follower_count=info.get("channel_follower_count"),
            views=info.get("view_count"),
            likes=info.get("like_count"),
            comments=info.get("comment_count"),
            hashtags=list(info.get("tags") or [])[:30],
            upload_date=_normalize_date(info.get("upload_date")),
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            source="youtube:data-api" if settings.youtube_api_key else "youtube:yt-dlp",
        )

        # Transcript chain: captions (proxied) → Apify actor → Whisper-on-audio.
        captions = await asyncio.to_thread(_fetch_captions, video_id)
        if captions:
            data.transcript_segments = captions
            data.source += "+captions"
            return data

        apify_segs = None
        try:
            apify_segs = await asyncio.to_thread(_transcript_via_apify, url, data.duration)
        except Exception:
            apify_segs = None  # fall through to Whisper
        if apify_segs:
            data.transcript_segments = apify_segs
            data.source += "+apify-transcript"
            return data

        # Last resort: download audio (yt-dlp, proxied) and Whisper it.
        data.audio_path = await asyncio.to_thread(_download_audio, url, video_id)
        data.source += "+whisper"
        return data
