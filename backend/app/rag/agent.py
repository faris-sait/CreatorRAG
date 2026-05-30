"""LangGraph ReAct agent over the two videos.

- LLM: Gemini 2.5 Flash (via LangChain, which LangGraph needs).
- Tool: the Qdrant retriever (transcripts), scoped to A/B.
- Memory: a process-wide InMemorySaver keyed by thread_id (= session_id), so
  the conversation remembers earlier turns ('improve B' after discussing A).

Structured metadata (engagement, followers, etc.) is injected into the system
prompt so numeric questions are answered from facts, while transcript questions
go through retrieval + citation.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from ..config import settings

# Memory is NOT a process-local checkpointer (lost on restart, grows unbounded).
# Instead we persist messages in Postgres and replay a bounded window each turn
# (see rag/stream.py). So the agent itself is stateless across calls.

# Cache one LLM client per API key (keys are rotated for quota headroom).
_llms: dict[str, object] = {}


def _llm_for(api_key: str):
    if api_key not in _llms:
        from langchain_google_genai import ChatGoogleGenerativeAI

        _llms[api_key] = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=0.2,
            google_api_key=api_key,
            disable_streaming=False,
        )
    return _llms[api_key]


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
        "Rules:\n"
        "1. For anything about what is *said* in a video (hooks, topics, "
        "structure, advice), call `search_transcripts` first — never invent "
        "transcript content.\n"
        "2. Answer numeric/metadata questions (engagement, followers, views) "
        "directly from the known facts above.\n"
        "3. Cite transcript evidence inline as [Video A @ m:ss] / [Video B @ "
        "m:ss] using the labels the tool returns.\n"
        "4. When comparing or suggesting improvements, be concrete and tie "
        "advice to specific evidence from the better-performing video.\n"
        "5. Keep answers tight and skimmable."
    )


def build_agent(tool: StructuredTool, video_a: dict, video_b: dict, api_key: str):
    return create_react_agent(
        _llm_for(api_key),
        [tool],
        prompt=build_system_prompt(video_a, video_b),
    )
