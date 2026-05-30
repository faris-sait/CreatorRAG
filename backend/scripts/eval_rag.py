"""Single-run RAG latency profiler.

Runs ONE question through the REAL pipeline — the same LangGraph ReAct agent the
chat endpoint uses (app.rag.stream.chat_stream) — and prints a stage-by-stage
timing breakdown so we can see where the response time goes.

It wraps the real embed_query / qdrant search with timers (so the numbers come
from the actual code path, not a reimplementation) and measures time-to-first
-token and total wall time from the SSE stream.

A ReAct turn normally makes ~2 LLM calls (decide-tool, then answer) + 1 embed
call, so this is a handful of API requests — run sparingly to respect free-tier
quota. Default is a single run.

Run:
    cd backend && . .venv/bin/activate
    python -m scripts.eval_rag                       # auto-pick a ready pair
    python -m scripts.eval_rag --pair <id> --q "..."
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from app import db, qdrant_store
from app.config import settings
from app.rag import agent as rag_agent

DEFAULT_Q = "Compare the hooks of the two videos. Which opening is stronger and why?"


class Accum:
    def __init__(self) -> None:
        self.embed_ms = 0.0
        self.embed_calls = 0
        self.search_ms = 0.0
        self.search_calls = 0


def _install_timers(acc: Accum):
    """Wrap the real embed_query (as seen by the graph) and qdrant_store.search
    with timers. Returns a restore() callable."""
    real_embed = rag_agent.embed_query
    real_search = qdrant_store.search

    def timed_embed(text):
        t0 = time.perf_counter()
        try:
            return real_embed(text)
        finally:
            acc.embed_ms += (time.perf_counter() - t0) * 1000
            acc.embed_calls += 1

    async def timed_search(*a, **k):
        t0 = time.perf_counter()
        try:
            return await real_search(*a, **k)
        finally:
            acc.search_ms += (time.perf_counter() - t0) * 1000
            acc.search_calls += 1

    # agent.py binds embed_query into its own namespace at import time, so patch
    # it there. search is looked up on the module each call, so patch the module.
    rag_agent.embed_query = timed_embed
    qdrant_store.search = timed_search

    def restore():
        rag_agent.embed_query = real_embed
        qdrant_store.search = real_search

    return restore


async def _pick_ready_pair() -> str | None:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT p.id FROM pairs p
                 JOIN videos a ON a.id = p.a_video_id
                 JOIN videos b ON b.id = p.b_video_id
                WHERE a.status='ready' AND b.status='ready'
                  AND a.num_chunks > 0 AND b.num_chunks > 0
                ORDER BY p.created_at DESC LIMIT 1"""
        )
    return str(row["id"]) if row else None


def _bar(ms: float, total: float, width: int = 30) -> str:
    filled = int(round((ms / total) * width)) if total else 0
    return "█" * filled + "·" * (width - filled)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default=None)
    ap.add_argument("--q", default=DEFAULT_Q)
    args = ap.parse_args()

    await db.init_pool()
    await qdrant_store.ensure_collection()

    pair_id = args.pair or await _pick_ready_pair()
    if not pair_id:
        print("No ready pair with chunks found. Ingest a pair first, or pass --pair.")
        await db.close_pool()
        return
    pair = await db.get_pair(pair_id)

    print(f"\n  pair_id : {pair_id}")
    print(f"  question: {args.q}")
    print(f"  model   : {settings.llm_model}  max_tokens={settings.llm_max_output_tokens}")
    print(f"  embed   : {settings.embed_model} ({settings.embed_dim}d)")

    from app.rag.stream import chat_stream

    acc = Accum()
    restore = _install_timers(acc)
    session_id = "eval-profiler-session"

    n_token_events = 0
    answer_chars = 0
    n_sources = 0
    ttft_ms = None
    wall0 = time.perf_counter()
    try:
        async for frame in chat_stream(pair, session_id, args.q):
            # frame is a raw SSE string: "event: X\ndata: {...}\n\n"
            ev = ""
            data = ""
            for line in frame.splitlines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
            if ev == "token":
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - wall0) * 1000
                n_token_events += 1
                try:
                    answer_chars += len(json.loads(data).get("text", ""))
                except Exception:
                    pass
            elif ev == "sources":
                try:
                    n_sources = len(json.loads(data).get("sources", []))
                except Exception:
                    pass
            elif ev == "error":
                print("\n  !! error event:", data)
    finally:
        restore()

    wall = (time.perf_counter() - wall0) * 1000
    llm_ms = max(0.0, wall - acc.embed_ms - acc.search_ms)

    print("\n  ── latency breakdown ─────────────────────────────────────")
    rows = [
        (f"embed_query  ×{acc.embed_calls}", acc.embed_ms),
        (f"qdrant+mmr   ×{acc.search_calls}", acc.search_ms),
        ("LLM (generate)", llm_ms),
    ]
    for name, ms in rows:
        pct = (ms / wall) * 100 if wall else 0
        print(f"  {name:<20} {ms:8.1f} ms  {pct:5.1f}%  {_bar(ms, wall)}")
    print(f"  {'TOTAL (wall)':<20} {wall:8.1f} ms")

    print("\n  ── output ───────────────────────────────────────────────")
    print(f"  time-to-first-token : {ttft_ms:.0f} ms" if ttft_ms else "  (no tokens streamed)")
    print(f"  token events        : {n_token_events}")
    print(f"  answer chars        : {answer_chars}")
    print(f"  sources cited       : {n_sources}")
    if answer_chars and wall:
        print(f"  throughput          : {answer_chars / (wall/1000):.0f} chars/s")

    # Clean up the eval session's persisted messages so we don't pollute memory.
    async with db.pool().acquire() as conn:
        await conn.execute("DELETE FROM chat_messages WHERE session_id=$1", session_id)

    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
