"""Video submission + status endpoints.

POST /api/videos       submit a {youtube_url, instagram_url} pair → enqueue
GET  /api/pairs/{id}   poll both videos' status + metadata (frontend polling)
GET  /api/videos/{id}  single video detail
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from .. import db, qdrant_store
from ..config import settings
from ..ingest.providers.factory import canonical_url, detect_platform
from ..media import fetch_image, host_allowed
from ..pipeline.queue import enqueue_ingest
from ..security import rate_limit, require_api_key

router = APIRouter(prefix="/api", tags=["videos"])

# Statuses that mean "no need to (re)process".
_TERMINAL_OK = {"ready"}


def _is_stale(video: dict) -> bool:
    """A ready video whose metadata is older than the TTL needs a refresh —
    views/likes drift over time, so dedup must not serve them forever."""
    if video.get("status") != "ready":
        return False
    updated = video.get("updated_at")
    if not updated:
        return False
    try:
        ts = datetime.fromisoformat(updated)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    return age_hours > settings.metadata_ttl_hours


class SubmitRequest(BaseModel):
    youtube_url: str
    instagram_url: str
    exact_yt_timestamps: bool = False  # SRT actor (exact) vs fast hybrid (approx)


class SubmitResponse(BaseModel):
    pair_id: str
    a_video_id: str
    b_video_id: str


async def _ingest_slot(
    url: str, expected_platform: str, exact_yt: bool = False
) -> dict:
    try:
        platform = detect_platform(url)
        url = canonical_url(url)  # scrub messy/pasted input to a clean URL
    except ValueError as e:
        # Unknown/malformed host → clean 422 (flows through CORS) instead of a
        # 500 that the browser would surface as an opaque "Failed to fetch".
        raise HTTPException(422, str(e)) from e
    if platform != expected_platform:
        raise HTTPException(
            422, f"Expected a {expected_platform} URL, got {platform}: {url}"
        )
    video, created = await db.get_or_create_video(url, platform)
    # (Re)enqueue when new, not-yet-ready, OR ready-but-stale (TTL). A fresh,
    # ready, non-stale video is reused instantly with zero re-embedding.
    if created or video["status"] not in _TERMINAL_OK or _is_stale(video):
        await db.set_status(video["id"], "queued")
        await enqueue_ingest(video["id"], url, platform, exact_yt=exact_yt)
    return video


@router.post(
    "/videos",
    response_model=SubmitResponse,
    dependencies=[Depends(rate_limit), Depends(require_api_key)],
)
async def submit_videos(req: SubmitRequest) -> SubmitResponse:
    a = await _ingest_slot(req.youtube_url, "youtube", exact_yt=req.exact_yt_timestamps)
    b = await _ingest_slot(req.instagram_url, "instagram")  # slot B
    pair = await db.create_pair(a["id"], b["id"])
    return SubmitResponse(pair_id=pair["id"], a_video_id=a["id"], b_video_id=b["id"])


def _public_video(v: dict) -> dict:
    """Trim the heavy transcript out of status payloads."""
    return {
        "id": v["id"],
        "url": v["url"],
        "platform": v["platform"],
        "status": v["status"],
        "error": v.get("error"),
        "engagement_rate": v.get("engagement_rate"),
        "num_chunks": v.get("num_chunks"),
        "metadata": v.get("metadata", {}),
    }


@router.get("/pairs/{pair_id}")
async def get_pair_status(pair_id: str) -> dict:
    pair = await db.get_pair(pair_id)
    if not pair:
        raise HTTPException(404, "pair not found")
    a = await db.get_video(pair["a_video_id"])
    b = await db.get_video(pair["b_video_id"])
    both_ready = bool(a and b and a["status"] == "ready" and b["status"] == "ready")
    return {
        "pair_id": pair_id,
        "ready": both_ready,
        "video_a": _public_video(a) if a else None,
        "video_b": _public_video(b) if b else None,
    }


@router.get("/videos/{video_id}")
async def get_video_detail(video_id: str) -> dict:
    v = await db.get_video(video_id)
    if not v:
        raise HTTPException(404, "video not found")
    out = _public_video(v)
    out["transcript_len"] = v.get("transcript_len")
    return out


_IMG_CACHE = {"Cache-Control": "public, max-age=86400"}


@router.get("/image")
async def image_proxy(url: str = Query(...)) -> Response:
    """Proxy a CDN thumbnail so the browser can load it (Instagram blocks
    hotlinking). Host-allowlisted to prevent SSRF / open-proxy abuse."""
    if not host_allowed(url):
        raise HTTPException(400, "host not allowed")
    img = await fetch_image(url)
    if not img:
        raise HTTPException(502, "failed to fetch image")
    return Response(content=img[0], media_type=img[1], headers=_IMG_CACHE)


@router.get("/videos/{video_id}/thumbnail")
async def video_thumbnail(video_id: str) -> Response:
    """Serve the persisted thumbnail (survives CDN URL expiry). Falls back to a
    live fetch of the stored metadata URL if we haven't persisted bytes yet."""
    stored = await db.get_thumbnail(video_id)
    if stored:
        return Response(content=stored[0], media_type=stored[1], headers=_IMG_CACHE)
    v = await db.get_video(video_id)
    live_url = (v or {}).get("metadata", {}).get("thumbnail") if v else None
    if live_url and host_allowed(live_url):
        img = await fetch_image(live_url)
        if img:
            return Response(content=img[0], media_type=img[1], headers=_IMG_CACHE)
    raise HTTPException(404, "no thumbnail")


@router.get("/videos/{video_id}/transcript")
async def get_transcript(video_id: str) -> dict:
    """Full transcript plus timestamped chunks (what the RAG agent retrieves)."""
    v = await db.get_video(video_id)
    if not v:
        raise HTTPException(404, "video not found")
    chunks = await qdrant_store.get_chunks(video_id)
    return {
        "id": v["id"],
        "platform": v["platform"],
        "title": v.get("metadata", {}).get("title"),
        "transcript": v.get("transcript") or "",
        "chunks": [
            {
                "chunk_index": c.get("chunk_index"),
                "start": c.get("start"),
                "end": c.get("end"),
                "text": c.get("text"),
            }
            for c in chunks
        ],
    }
