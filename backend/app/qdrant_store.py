"""Qdrant vector store.

Collection `video_chunks`, COSINE distance (matches our L2-normalized Gemini
embeddings). Every point carries the stable `video_id` plus the chunk text and
its transcript timestamps, which is exactly what the chat agent cites.

Point IDs are deterministic (uuid5 of video_id + chunk_index) so re-ingesting a
video is idempotent — combined with DB dedup this is the 'never re-embed twice'
guarantee.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from .config import settings

_NS = uuid.UUID("00000000-0000-0000-0000-00000000c0de")  # stable namespace

_client: AsyncQdrantClient | None = None


def client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


async def ensure_collection() -> None:
    c = client()
    exists = await c.collection_exists(settings.qdrant_collection)
    if not exists:
        await c.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=settings.embed_dim, distance=models.Distance.COSINE
            ),
        )
    # Payload index on video_id makes the per-comparison filter fast.
    try:
        await c.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="video_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # already exists


def _point_id(video_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_NS, f"{video_id}:{chunk_index}"))


async def upsert_chunks(
    video_id: str,
    platform: str,
    chunks: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
) -> None:
    """chunks[i] = {text, start, end, chunk_index}; vectors[i] = embedding."""
    points = [
        models.PointStruct(
            id=_point_id(video_id, ch["chunk_index"]),
            vector=list(vec),
            payload={
                "video_id": video_id,
                "platform": platform,
                "text": ch["text"],
                "start": ch.get("start"),
                "end": ch.get("end"),
                "chunk_index": ch["chunk_index"],
            },
        )
        for ch, vec in zip(chunks, vectors, strict=False)
    ]
    if points:
        await client().upsert(
            collection_name=settings.qdrant_collection, points=points, wait=True
        )


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    # vectors are L2-normalized, so dot product == cosine similarity
    return sum(x * y for x, y in zip(a, b, strict=False))


def _mmr(
    candidates: list[dict[str, Any]], k: int, lambda_: float
) -> list[dict[str, Any]]:
    """Maximal Marginal Relevance: pick k chunks balancing relevance to the
    query against diversity, so we don't return near-duplicate snippets."""
    selected: list[dict[str, Any]] = []
    pool = candidates[:]
    while pool and len(selected) < k:
        best, best_val = None, float("-inf")
        for c in pool:
            rel = c["score"]  # cosine similarity to the query (from Qdrant)
            div = max((_dot(c["_vec"], s["_vec"]) for s in selected), default=0.0)
            val = lambda_ * rel - (1 - lambda_) * div
            if val > best_val:
                best, best_val = c, val
        selected.append(best)
        pool.remove(best)
    return selected


async def search(
    query_vector: Sequence[float],
    video_ids: Sequence[str] | None = None,
    limit: int | None = None,
    max_start: float | None = None,
    score_threshold: float | None = None,
    use_mmr: bool = True,
) -> list[dict[str, Any]]:
    """Filtered semantic search with a relevance floor + MMR diversity rerank.

    - `video_ids` scopes to a comparison's videos (or just A / just B).
    - `max_start` keeps only chunks beginning before this time (seconds) — for
      hook questions like "the first 5 seconds".
    - matches below `score_threshold` are dropped.
    - over-fetch then MMR-select `limit` diverse, relevant chunks.
    """
    limit = limit or settings.retrieval_k
    if score_threshold is None:
        score_threshold = settings.retrieval_min_score

    conditions: list = []
    if video_ids:
        conditions.append(
            models.FieldCondition(key="video_id", match=models.MatchAny(any=list(video_ids)))
        )
    if max_start is not None:
        conditions.append(models.FieldCondition(key="start", range=models.Range(lt=max_start)))
    flt = models.Filter(must=conditions) if conditions else None

    res = await client().query_points(
        collection_name=settings.qdrant_collection,
        query=list(query_vector),
        query_filter=flt,
        limit=settings.retrieval_fetch_k,  # over-fetch for MMR
        score_threshold=score_threshold,
        with_payload=True,
        with_vectors=use_mmr,
    )
    cands = [
        {"score": p.score, "_vec": list(p.vector or []), **(p.payload or {})}
        for p in res.points
    ]
    if use_mmr and cands and cands[0]["_vec"]:
        cands = _mmr(cands, limit, settings.retrieval_mmr_lambda)
    else:
        cands = cands[:limit]
    for c in cands:
        c.pop("_vec", None)
    return cands


async def count() -> int:
    r = await client().count(settings.qdrant_collection, exact=True)
    return r.count


async def get_chunks(video_id: str) -> list[dict[str, Any]]:
    """All chunks for a video, ordered by chunk_index — powers the transcript view."""
    points, _ = await client().scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="video_id", match=models.MatchValue(value=video_id)
                )
            ]
        ),
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )
    chunks = [p.payload or {} for p in points]
    chunks.sort(key=lambda c: c.get("chunk_index", 0))
    return chunks
