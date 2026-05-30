"""SSE event generator for the chat endpoint.

Streams four kinds of Server-Sent Events:
  event: token   → incremental answer text (token-level, for a live typewriter)
  event: sources → the transcript chunks the agent retrieved (video + timestamp)
  event: done    → end of turn
  event: error   → something failed

Memory: we persist every message in Postgres and replay a bounded window
(`chat_history_messages`) into the agent each turn. So memory survives restarts
AND context cost stays capped — unlike an in-process checkpointer.

Key rotation: each turn is attempted with a round-robin Google key, failing over
to the next on a quota/429 error (as long as nothing was streamed yet).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from .. import db
from ..config import settings
from ..keyring import is_quota_error, keyring
from .agent import build_graph


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _text_of(content) -> str:
    if isinstance(content, list):
        return "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return content or ""


def _final_text(messages: list) -> str:
    """Last AI message's text from a state's message list (zero-token fallback)."""
    for msg in reversed(messages or []):
        if getattr(msg, "type", None) == "ai" and getattr(msg, "content", None):
            return _text_of(msg.content)
    return ""


def _history_to_messages(history: list[dict]) -> list:
    out = []
    for m in history:
        if m["role"] == "user":
            out.append(HumanMessage(content=m["content"]))
        else:
            out.append(AIMessage(content=m["content"]))
    return out


def _dedup_sources(collector: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in collector:
        key = (c["video"], c["chunk_index"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


async def chat_stream(
    pair: dict, session_id: str, message: str
) -> AsyncIterator[str]:
    video_a = await db.get_video(pair["a_video_id"])
    video_b = await db.get_video(pair["b_video_id"])
    if not video_a or not video_b:
        yield _sse("error", {"message": "Videos for this pair not found"})
        return

    slot_map = {"A": pair["a_video_id"], "B": pair["b_video_id"]}
    # Replay bounded conversation history (persistent memory).
    history = await db.get_recent_messages(session_id, settings.chat_history_messages)
    history_messages = _history_to_messages(history)

    try:
        keys = keyring.ordered_from_next()
    except RuntimeError:
        yield _sse("error", {"message": "No Google API key configured"})
        return

    last_err: Exception | None = None
    for idx, key in enumerate(keys):
        # Fresh single-pass retrieve→generate graph per key attempt. Retrieval
        # re-runs on failover, but that's only ~0.2s and only on the rare
        # quota-exhausted path.
        graph = build_graph(video_a, video_b, slot_map, key)
        streamed_any = False
        answer = ""
        final_state = None
        try:
            async for mode, chunk in graph.astream(
                {"question": message, "history": history_messages},
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    msg, meta = chunk
                    if (
                        isinstance(msg, AIMessageChunk)
                        and meta.get("langgraph_node") == "generate"
                        and msg.content
                    ):
                        text = _text_of(msg.content)
                        if text:
                            streamed_any = True
                            answer += text
                            yield _sse("token", {"text": text})
                elif mode == "values":
                    final_state = chunk

            # Zero-token safety net (Gemini occasionally returns no stream).
            if not streamed_any and final_state:
                answer = _final_text(final_state.get("messages", []))
                if answer:
                    yield _sse("token", {"text": answer})

            # Persist the turn (memory).
            await db.save_message(session_id, "user", message)
            if answer:
                await db.save_message(session_id, "assistant", answer)

            sources = _dedup_sources(final_state.get("citations", []) if final_state else [])
            yield _sse("sources", {"sources": sources})
            yield _sse("done", {})
            return  # success
        except Exception as e:  # noqa: BLE001
            last_err = e
            if streamed_any:
                yield _sse("error", {"message": str(e)})
                return
            if is_quota_error(e) and idx < len(keys) - 1:
                continue  # fail over to next key
            break

    if last_err is not None and is_quota_error(last_err):
        msg = (
            f"All {len(keys)} Google API key(s) are rate-limited right now. "
            "Free tier is ~20 requests/day per key — wait or add more keys."
        )
    else:
        msg = str(last_err) if last_err else "Chat failed"
    yield _sse("error", {"message": msg})
