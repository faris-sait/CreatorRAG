"""Single-pass RAG graph over the two videos (LangGraph).

A 2-node StateGraph:  retrieve  →  generate

- retrieve: embed the question, semantic-search BOTH videos' transcripts
  (Qdrant + MMR), and build the grounded context + structured citations.
- generate: one streaming LLM call that answers from that context + the
  structured metadata baked into the system prompt.

Why not a ReAct tool-calling agent? Almost every question here is about the two
videos and should hit transcript search anyway. A ReAct agent spends a whole
extra LLM round-trip just deciding "I should call the search tool" — ~1.5-2s of
latency before retrieval even starts. Doing retrieval unconditionally collapses
that to a single LLM call and roughly halves time-to-first-token.

- LLM: Gemini (flash-lite) via LangChain (which LangGraph builds on).
- Memory: NOT a process-local checkpointer. We persist messages in Postgres and
  replay a bounded window each turn (see rag/stream.py), so the graph is
  stateless across calls and memory survives restarts.
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from .. import qdrant_store
from ..config import settings
from ..embeddings import embed_query

# Cache one LLM client per API key (keys are rotated for quota headroom).
_llms: dict[str, object] = {}


def _llm_for(api_key: str):
    if api_key not in _llms:
        from langchain_google_genai import ChatGoogleGenerativeAI

        _llms[api_key] = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=0.2,
            google_api_key=api_key,
            # Cap the answer length: short-form video Q&A doesn't need long
            # essays, and generation time scales with output tokens. This is the
            # single biggest lever on response latency.
            max_output_tokens=settings.llm_max_output_tokens,
        )
    return _llms[api_key]


def warmup_llm() -> None:
    """Pre-construct the LLM client for the next key at startup so the first
    chat request doesn't pay client-construction cost. Best-effort."""
    from ..keyring import keyring

    if keyring:
        _llm_for(keyring.next())


def _fmt_ts(seconds) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _summarize(slot: str, platform: str, meta: dict[str, Any], rate) -> str:
    return (
        f"Video {slot} ({platform}): "
        f"creator=@{meta.get('creator') or '?'}, "
        f"followers={meta.get('follower_count')}, "
        f"views={meta.get('views')}, likes={meta.get('likes')}, "
        f"comments={meta.get('comments')}, "
        f"engagement_rate={rate if rate is not None else 'n/a'}%, "
        f"duration={meta.get('duration')}s, "
        f"uploaded={meta.get('upload_date')}, "
        f"hashtags={', '.join(meta.get('hashtags') or []) or 'none'}, "
        f"title={meta.get('title') or ''!r}"
    )


def build_system_prompt(video_a: dict, video_b: dict) -> str:
    a = _summarize("A", video_a.get("platform", "youtube"),
                   video_a.get("metadata", {}), video_a.get("engagement_rate"))
    b = _summarize("B", video_b.get("platform", "instagram"),
                   video_b.get("metadata", {}), video_b.get("engagement_rate"))
    return (
        "You are CreatorRAG, an analyst helping a creator compare two short "
        "videos: Video A and Video B.\n\n"
        "Known facts about the videos:\n"
        f"- {a}\n- {b}\n\n"
        "Engagement rate = (likes + comments) / views * 100.\n\n"
        "You are given retrieved transcript excerpts from both videos, each "
        "labeled [Video A @ m:ss] or [Video B @ m:ss].\n\n"
        "Rules:\n"
        "1. For anything about what is *said* in a video (hooks, topics, "
        "structure, advice), ground your answer in the provided excerpts — "
        "never invent transcript content. If the excerpts don't cover it, say "
        "so.\n"
        "2. Answer numeric/metadata questions (engagement, followers, views) "
        "directly from the known facts above.\n"
        "3. Cite transcript evidence inline as [Video A @ m:ss] / [Video B @ "
        "m:ss] using the labels shown on the excerpts.\n"
        "4. When comparing or suggesting improvements, be concrete and tie "
        "advice to specific evidence from the better-performing video.\n"
        "5. Keep answers tight and skimmable — aim for under ~150 words unless "
        "the user explicitly asks you to go deeper. Lead with the answer; skip "
        "preamble."
    )


class RAGState(TypedDict, total=False):
    question: str          # the current user question
    history: list          # prior conversation as LC messages (bounded replay)
    context: str           # retrieved transcript excerpts (set by retrieve)
    citations: list[dict]  # structured sources (set by retrieve)
    messages: list         # [AIMessage] answer (set by generate)


def build_graph(video_a: dict, video_b: dict, slot_map: dict[str, str], api_key: str):
    """Compile a fresh retrieve→generate graph for one turn (closes over the
    pair's videos, the A/B id map, and the chosen API key for failover)."""
    a_id, b_id = slot_map["A"], slot_map["B"]
    id_to_slot = {v: k for k, v in slot_map.items()}
    llm = _llm_for(api_key)
    system = build_system_prompt(video_a, video_b)

    async def retrieve(state: RAGState) -> dict:
        qvec = await asyncio.to_thread(embed_query, state["question"])
        hits = await qdrant_store.search(
            qvec, video_ids=[a_id, b_id], limit=settings.retrieval_k
        )
        lines: list[str] = []
        citations: list[dict] = []
        for h in hits:
            slot = id_to_slot.get(h.get("video_id"), "?")
            ts = _fmt_ts(h.get("start"))
            citations.append({
                "video": slot,
                "chunk_index": h.get("chunk_index"),
                "start": h.get("start"),
                "end": h.get("end"),
                "timestamp": ts,
                "text": h.get("text"),
                "score": round(h.get("score", 0), 4),
            })
            lines.append(f"[Video {slot} @ {ts}] {h.get('text')}")
        context = "\n\n".join(lines) if lines else "No relevant transcript excerpts found."
        return {"context": context, "citations": citations}

    async def generate(state: RAGState, config: RunnableConfig) -> dict:
        user = (
            "Transcript excerpts:\n"
            f"{state['context']}\n\n"
            "---\n\n"
            f"Question: {state['question']}"
        )
        msgs = [SystemMessage(content=system)]
        msgs.extend(state.get("history", []))
        msgs.append(HumanMessage(content=user))
        # Stream (not ainvoke) so the model emits token chunks as they're
        # generated — that's what LangGraph's stream_mode="messages" forwards to
        # the SSE layer for the live typewriter. We MUST pass `config` through so
        # the streaming callbacks propagate; without it the chunks are swallowed
        # and the answer arrives as one lump (TTFT == total). Accumulate into one
        # AIMessage for the final state (memory + zero-token fallback).
        final = None
        async for chunk in llm.astream(msgs, config):
            final = chunk if final is None else final + chunk
        return {"messages": [final] if final is not None else []}

    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()
