"""Integration tests — exercise the real data layer (Postgres + Qdrant).

Skipped unless CREATORRAG_INTEGRATION=1 (so plain `pytest` stays unit-only).
CI sets that env and provides service containers. Uses synthetic vectors, so no
external API keys are needed.
"""
import math
import os

import pytest

pytestmark = pytest.mark.integration

RUN = os.getenv("CREATORRAG_INTEGRATION") == "1"
skip = pytest.mark.skipif(not RUN, reason="integration services not configured")


def _unit(seed: int) -> list[float]:
    xs = [math.sin(seed * 0.7 + i * 0.013) for i in range(768)]
    n = math.sqrt(sum(x * x for x in xs)) or 1.0
    return [x / n for x in xs]


@skip
async def test_dedup_and_filtered_search_roundtrip():
    from app import db, qdrant_store

    await db.init_pool()
    try:
        url = "https://www.youtube.com/watch?v=INTEGRATIO1"
        v, created = await db.get_or_create_video(url, "youtube")
        # dedup: same video, messy variant → same row
        v2, created2 = await db.get_or_create_video(url + "&t=5s&x=1", "youtube")
        assert v["id"] == v2["id"]
        assert created is True and created2 is False

        await qdrant_store.ensure_collection()
        chunks = [
            {"text": f"chunk {i}", "start": i * 2.0, "end": i * 2.0 + 2, "chunk_index": i}
            for i in range(3)
        ]
        await qdrant_store.upsert_chunks(v["id"], "youtube", chunks, [_unit(i) for i in range(3)])

        hits = await qdrant_store.search(_unit(0), video_ids=[v["id"]], limit=3, score_threshold=0.0)
        assert hits and all(h["video_id"] == v["id"] for h in hits)
        assert {"text", "start", "end", "chunk_index", "video_id"} <= set(hits[0])
    finally:
        await db.close_pool()


@skip
async def test_chat_memory_persists():
    from app import db

    await db.init_pool()
    try:
        sid = "integration-mem"
        async with db.pool().acquire() as c:
            await c.execute("DELETE FROM chat_messages WHERE session_id=$1", sid)
        await db.save_message(sid, "user", "first")
        await db.save_message(sid, "assistant", "reply")
        recent = await db.get_recent_messages(sid, 5)
        assert [m["content"] for m in recent] == ["first", "reply"]
    finally:
        await db.close_pool()
