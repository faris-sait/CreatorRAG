"""Postgres access layer (asyncpg). Plain SQL — no ORM — to keep it auditable.

Holds a single shared pool. Bootstraps the schema on startup so a fresh
`docker compose up` + backend start is enough to run the whole app.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from .config import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_pool: asyncpg.Pool | None = None


# ── URL normalization + hashing (dedup key) ───────────────────────────────
def normalize_url(url: str) -> str:
    """Normalize a video URL so trivially different strings dedup to one row.

    Lowercases host, drops fragments and tracking query params, strips a
    trailing slash. Intentionally conservative — we keep the path and the
    meaningful query (e.g. YouTube's ?v=).
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # keep only meaningful query params
    keep = []
    for kv in parts.query.split("&"):
        if not kv:
            continue
        key = kv.split("=", 1)[0].lower()
        if key in {"v", "list"}:  # youtube id / playlist; ig reels use path
            keep.append(kv)
    query = "&".join(keep)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


# ── Pool lifecycle ────────────────────────────────────────────────────────
async def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text())


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


# ── Video CRUD ────────────────────────────────────────────────────────────
async def get_or_create_video(url: str, platform: str) -> tuple[dict[str, Any], bool]:
    """Return (video_row, created). Dedups by url_hash — the core of the
    'never re-embed the same chunk twice' guarantee."""
    h = url_hash(url)
    async with pool().acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM videos WHERE url_hash=$1", h)
        if existing:
            return _row(existing), False
        row = await conn.fetchrow(
            """INSERT INTO videos (url, url_hash, platform, status)
               VALUES ($1,$2,$3,'queued') RETURNING *""",
            url, h, platform,
        )
        return _row(row), True


async def get_video(video_id: str) -> dict[str, Any] | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM videos WHERE id=$1", video_id)
        return _row(row) if row else None


async def set_status(video_id: str, status: str, error: str | None = None) -> None:
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE videos SET status=$2, error=$3, updated_at=now() WHERE id=$1",
            video_id, status, error,
        )


async def save_ingest_result(
    video_id: str,
    *,
    metadata: dict[str, Any],
    engagement_rate: float | None,
    transcript: str,
    num_chunks: int,
) -> None:
    async with pool().acquire() as conn:
        await conn.execute(
            """UPDATE videos
                  SET status='ready', metadata=$2, engagement_rate=$3,
                      transcript=$4, transcript_len=$5, num_chunks=$6,
                      error=NULL, updated_at=now()
                WHERE id=$1""",
            video_id, json.dumps(metadata), engagement_rate,
            transcript, len(transcript or ""), num_chunks,
        )


# ── Pairs ─────────────────────────────────────────────────────────────────
async def create_pair(a_video_id: str, b_video_id: str) -> dict[str, Any]:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO pairs (a_video_id, b_video_id) VALUES ($1,$2) RETURNING *",
            a_video_id, b_video_id,
        )
        return _row(row)


async def get_pair(pair_id: str) -> dict[str, Any] | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM pairs WHERE id=$1", pair_id)
        return _row(row) if row else None


# ── Thumbnails (persisted bytes; CDN URLs expire) ─────────────────────────
async def save_thumbnail(video_id: str, data: bytes, content_type: str) -> None:
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE videos SET thumbnail_data=$2, thumbnail_type=$3 WHERE id=$1",
            video_id, data, content_type,
        )


async def get_thumbnail(video_id: str) -> tuple[bytes, str] | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT thumbnail_data, thumbnail_type FROM videos WHERE id=$1", video_id
        )
        if row and row["thumbnail_data"]:
            return bytes(row["thumbnail_data"]), row["thumbnail_type"] or "image/jpeg"
        return None


# ── Chat history (persistent, bounded memory) ─────────────────────────────
async def save_message(session_id: str, role: str, content: str) -> None:
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES ($1,$2,$3)",
            session_id, role, content,
        )


async def get_recent_messages(session_id: str, limit: int) -> list[dict[str, Any]]:
    """Last `limit` messages for a session, oldest→newest (for replay)."""
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM (
                   SELECT role, content, id FROM chat_messages
                   WHERE session_id=$1 ORDER BY id DESC LIMIT $2
               ) t ORDER BY id ASC""",
            session_id, limit,
        )
        return [{"role": r["role"], "content": r["content"]} for r in rows]


# ── helpers ───────────────────────────────────────────────────────────────
def _row(row: asyncpg.Record | None) -> dict[str, Any]:
    """asyncpg Record → plain dict, decoding the JSONB metadata column."""
    if row is None:
        return {}
    d = dict(row)
    d.pop("thumbnail_data", None)  # never carry raw image bytes around in dicts
    for k in ("id", "url_hash", "a_video_id", "b_video_id"):
        if k in d and d[k] is not None:
            d[k] = str(d[k])
    if "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = json.loads(d["metadata"])
    for k in ("created_at", "updated_at"):
        if k in d and d[k] is not None:
            d[k] = d[k].isoformat()
    return d
