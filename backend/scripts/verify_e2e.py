"""Manual end-to-end verification harness.

Runs the real pipeline (ingest YouTube + Instagram) then the real RAG chat over
the resulting pair, exercising embeddings, Qdrant, the LangGraph agent, Gemini,
streaming, citations, and cross-turn memory. Requires GOOGLE_API_KEY (and, for
live videos without captions, GROQ_API_KEY / APIFY_TOKEN).

Usage:
    python -m scripts.verify_e2e [YOUTUBE_URL] [INSTAGRAM_URL]
"""
from __future__ import annotations

import asyncio
import sys

from app import db, qdrant_store
from app.pipeline.tasks import ingest_video
from app.rag.stream import chat_stream

YT = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
IG = sys.argv[2] if len(sys.argv) > 2 else "https://www.instagram.com/reel/CtjUklXt5Vp/"

QUESTIONS = [
    "What's the engagement rate of each video?",
    "Compare the hooks in the first 5 seconds of each.",
    "Who's the creator of Video B and what's their follower count?",
    "Why did Video A get more engagement than Video B?",
    "Suggest improvements for B based on what worked in A.",
    # memory follow-up — relies on the previous turn, no restating
    "Of those suggestions, which one would you prioritize first and why?",
]


async def run_chat(pair: dict, session: str, q: str) -> tuple[str, list]:
    import json

    answer, sources = "", []
    async for frame in chat_stream(pair, session, q):
        for line in frame.split("\n"):
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())
                if ev == "token":
                    answer += data.get("text", "")
                elif ev == "sources":
                    sources = data.get("sources", [])
    return answer, sources


async def main() -> None:
    await db.init_pool()
    await qdrant_store.ensure_collection()

    print("=" * 70, "\nINGEST\n", "=" * 70, sep="")
    a, _ = await db.get_or_create_video(YT, "youtube")
    b, _ = await db.get_or_create_video(IG, "instagram")
    for v, url, plat in [(a, YT, "youtube"), (b, IG, "instagram")]:
        print(f"\n→ ingesting {plat}: {url}")
        res = await ingest_video({}, v["id"], url, plat)
        print(f"   result: {res}")

    a = await db.get_video(a["id"])
    b = await db.get_video(b["id"])
    for slot, v in [("A", a), ("B", b)]:
        m = v["metadata"]
        print(
            f"\nVideo {slot} [{v['status']}] @{m.get('creator')} "
            f"followers={m.get('follower_count')} views={m.get('views')} "
            f"likes={m.get('likes')} comments={m.get('comments')} "
            f"ER={v.get('engagement_rate')}% chunks={v.get('num_chunks')}"
        )
    print("\nqdrant total points:", await qdrant_store.count())

    if a["status"] != "ready" or b["status"] != "ready":
        print("\n!! one or both videos not ready — aborting chat")
        await db.close_pool()
        return

    pair = await db.create_pair(a["id"], b["id"])
    session = "verify-session"

    print("\n" + "=" * 70 + "\nCHAT (single session → memory across turns)\n" + "=" * 70)
    for i, q in enumerate(QUESTIONS, 1):
        ans, srcs = await run_chat(pair, session, q)
        print(f"\n[Q{i}] {q}")
        print(f"  A: {ans.strip()[:600]}")
        if srcs:
            cites = ", ".join(f"Video {s['video']}@{s['timestamp']}" for s in srcs)
            print(f"  sources: {cites}")
    await db.close_pool()
    print("\n" + "=" * 70 + "\nE2E VERIFICATION COMPLETE\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
