"""The retrieval tool the agent calls to ground its answers.

Built per-conversation via `make_retriever_tool` so it closes over:
  - slot_map: {"A": <youtube video_id>, "B": <instagram video_id>}
  - collector: a list the tool appends retrieved chunks to, so the SSE layer
    can emit them as structured `sources` events (cite which video + timestamp).

The tool lets the agent scope retrieval to Video A, Video B, or both — which is
exactly what questions like 'compare the hooks in A and B' need.
"""
from __future__ import annotations

from typing import Literal

from langchain_core.tools import StructuredTool

from .. import qdrant_store
from ..embeddings import embed_query


def _fmt_ts(seconds) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def make_retriever_tool(slot_map: dict[str, str], collector: list[dict]) -> StructuredTool:
    id_to_slot = {v: k for k, v in slot_map.items()}

    async def search_transcripts(
        query: str,
        video: Literal["A", "B", "both"] = "both",
        first_seconds: int = 0,
    ) -> str:
        """Search the transcripts of the two analyzed videos.

        Args:
            query: what to look for (a paraphrase of the user's intent).
            video: 'A' (YouTube), 'B' (Instagram), or 'both'.
            first_seconds: if > 0, only search the opening N seconds of the
                video(s). Use this for hook questions, e.g. "the first 5 seconds".
        Returns transcript chunks, each labeled with its video and timestamp.
        """
        if video == "A":
            ids = [slot_map["A"]]
        elif video == "B":
            ids = [slot_map["B"]]
        else:
            ids = [slot_map["A"], slot_map["B"]]

        import asyncio

        qvec = await asyncio.to_thread(embed_query, query)
        hits = await qdrant_store.search(
            qvec,
            video_ids=ids,
            max_start=float(first_seconds) if first_seconds and first_seconds > 0 else None,
        )

        lines: list[str] = []
        for h in hits:
            slot = id_to_slot.get(h.get("video_id"), "?")
            ts = _fmt_ts(h.get("start"))
            citation = {
                "video": slot,
                "chunk_index": h.get("chunk_index"),
                "start": h.get("start"),
                "end": h.get("end"),
                "timestamp": ts,
                "text": h.get("text"),
                "score": round(h.get("score", 0), 4),
            }
            collector.append(citation)
            lines.append(f"[Video {slot} @ {ts}] {h.get('text')}")

        if not lines:
            return "No relevant transcript chunks found."
        return "\n\n".join(lines)

    return StructuredTool.from_function(
        coroutine=search_transcripts,
        name="search_transcripts",
        description=(
            "Search the transcripts of the two analyzed videos (A=YouTube, "
            "B=Instagram). Use video='A', 'B', or 'both'. Set first_seconds=N "
            "to search only the opening N seconds (for hook questions). Always "
            "call this before answering questions about what was said in the videos."
        ),
    )
