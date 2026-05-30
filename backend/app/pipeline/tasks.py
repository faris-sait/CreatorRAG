"""The ingest job: one video, URL → ready-to-chat.

fetch → (transcribe if needed) → engagement rate → chunk → embed → Qdrant +
Postgres → status=ready. Status is advanced at each step so the frontend can
show live progress per video. Any failure marks the video 'error' with a
message rather than crashing the worker.
"""
from __future__ import annotations

import asyncio
import json
import logging

from arq import Retry

from .. import db, qdrant_store
from ..embeddings import embed_documents
from ..ingest.chunk import chunk_segments, full_text
from ..ingest.providers.base import engagement_rate
from ..ingest.providers.factory import get_provider
from ..ingest.transcribe import transcribe
from ..keyring import is_quota_error
from ..media import fetch_image
from .queue import get_queue

log = logging.getLogger("creatorrag.pipeline")

MAX_TRIES = 4  # bounded retries for transient failures before dead-lettering


def _is_transient(e: Exception) -> bool:
    """Worth retrying (network blips, rate limits, gateway errors) vs permanent
    (e.g. 'no transcript available')."""
    s = str(e).lower()
    return is_quota_error(e) or any(
        t in s
        for t in ("timeout", "timed out", "connection", "temporarily",
                  "reset by peer", "502", "503", "504")
    )


async def _dead_letter(video_id: str, url: str, error: str) -> None:
    """Record a permanently-failed job for ops visibility (the DB row's
    status='error' is the source of truth; this is a quick ops queue)."""
    try:
        q = await get_queue()
        await q.rpush(
            "creatorrag:dead_letter",
            json.dumps({"video_id": video_id, "url": url, "error": error}),
        )
    except Exception:  # noqa: BLE001
        pass


async def ingest_video(
    ctx: dict, video_id: str, url: str, platform: str, exact_yt: bool = False
) -> dict:
    try:
        await db.set_status(video_id, "fetching")
        provider = get_provider(url, youtube_exact=exact_yt)
        data = await provider.fetch(url)

        # Persist the thumbnail bytes now — CDN URLs are time-signed and expire.
        if data.thumbnail:
            img = await fetch_image(data.thumbnail)
            if img:
                await db.save_thumbnail(video_id, img[0], img[1])

        # transcript: captions if provided, else Whisper on audio
        segments = data.transcript_segments
        if not segments:
            await db.set_status(video_id, "transcribing")
            segments = await transcribe(
                audio_path=data.audio_path, audio_url=data.audio_url
            )
        if not segments:
            raise RuntimeError("No transcript could be produced for this video")

        transcript = full_text(segments)
        rate = engagement_rate(data.likes, data.comments, data.views)

        await db.set_status(video_id, "embedding")
        chunks = chunk_segments(segments)
        texts = [c["text"] for c in chunks]
        vectors = await asyncio.to_thread(embed_documents, texts)
        await qdrant_store.upsert_chunks(video_id, platform, chunks, vectors)

        meta = data.metadata_dict()
        meta["engagement_rate"] = rate
        await db.save_ingest_result(
            video_id,
            metadata=meta,
            engagement_rate=rate,
            transcript=transcript,
            num_chunks=len(chunks),
        )
        log.info("Ingested %s (%s) — %d chunks", video_id, platform, len(chunks))
        return {"video_id": video_id, "status": "ready", "chunks": len(chunks)}
    except Exception as e:  # noqa: BLE001
        tries = ctx.get("job_try", 1)
        if _is_transient(e) and tries < MAX_TRIES:
            backoff = min(2 ** tries, 30)  # 2s, 4s, 8s… capped
            log.warning(
                "Ingest %s transient failure (try %d/%d) — retrying in %ds: %s",
                video_id, tries, MAX_TRIES, backoff, e,
            )
            await db.set_status(video_id, "queued")
            raise Retry(defer=backoff) from e  # arq re-queues with backoff
        log.exception("Ingest permanently failed for %s", video_id)
        await db.set_status(video_id, "error", error=str(e))
        await _dead_letter(video_id, url, str(e))
        return {"video_id": video_id, "status": "error", "error": str(e)}
