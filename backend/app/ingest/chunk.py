"""Segment-aware transcript chunking.

We don't blindly split on characters. We accumulate whole transcript segments
(which carry timestamps) until we hit a token budget, then emit a chunk that
keeps the start time of its first segment and the end time of its last. A small
token overlap preserves context across chunk boundaries.

Chunk size (~400 tokens, ~60 overlap) is tuned for short-form video: big enough
to hold a complete thought / hook, small enough that retrieval stays precise and
citations point at a specific moment. Defended in the README.
"""
from __future__ import annotations

import tiktoken

from ..config import settings

# cl100k is a fine proxy for token counting; the exact tokenizer doesn't matter
# for *budgeting* chunk sizes.
_enc = tiktoken.get_encoding("cl100k_base")


def _ntokens(text: str) -> int:
    return len(_enc.encode(text))


def chunk_segments(
    segments: list[dict],
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[dict]:
    """segments: [{start, end, text}] → chunks: [{chunk_index, start, end, text}]."""
    max_tokens = max_tokens or settings.chunk_tokens
    overlap_tokens = overlap_tokens or settings.chunk_overlap

    # Drop empties.
    segs = [s for s in segments if (s.get("text") or "").strip()]
    if not segs:
        return []

    chunks: list[dict] = []
    cur: list[dict] = []
    cur_tokens = 0

    def flush() -> None:
        nonlocal cur, cur_tokens
        if not cur:
            return
        text = " ".join(s["text"].strip() for s in cur).strip()
        chunks.append(
            {
                "chunk_index": len(chunks),
                "start": cur[0].get("start"),
                "end": cur[-1].get("end"),
                "text": text,
            }
        )
        # Carry an overlap tail (by tokens) into the next chunk.
        if overlap_tokens > 0:
            tail: list[dict] = []
            tok = 0
            for s in reversed(cur):
                t = _ntokens(s["text"])
                if tok + t > overlap_tokens:
                    break
                tail.insert(0, s)
                tok += t
            cur = tail
            cur_tokens = tok
        else:
            cur = []
            cur_tokens = 0

    for s in segs:
        t = _ntokens(s["text"])
        # A single huge segment still becomes its own chunk.
        if cur and cur_tokens + t > max_tokens:
            flush()
        cur.append(s)
        cur_tokens += t

    # final flush without re-seeding overlap
    if cur:
        text = " ".join(s["text"].strip() for s in cur).strip()
        chunks.append(
            {
                "chunk_index": len(chunks),
                "start": cur[0].get("start"),
                "end": cur[-1].get("end"),
                "text": text,
            }
        )
    return chunks


def full_text(segments: list[dict]) -> str:
    return " ".join((s.get("text") or "").strip() for s in segments).strip()
