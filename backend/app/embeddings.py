"""Embeddings via Google's `gemini-embedding-001`.

We use the modern `google-genai` SDK directly (not the LangChain wrapper)
because we need two things the wrapper doesn't expose at this version:
  1. `output_dimensionality=768` — MRL truncation. 3072-dim is overkill for
     short-form transcripts and quadruples Qdrant storage/latency for no gain.
  2. asymmetric `task_type` — RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY
     for the question. This asymmetry materially improves retrieval quality.

text-embedding-004 (named in the original spec) was deprecated 2026-01-14;
gemini-embedding-001 is its successor.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from google import genai
from google.genai import types

from .config import settings
from .keyring import is_quota_error, keyring

# Gemini embedding API caps batch size; stay well under it.
_BATCH = 64

# One genai client per key, created lazily and reused.
_clients: dict[str, genai.Client] = {}


def _client_for(key: str) -> genai.Client:
    if key not in _clients:
        _clients[key] = genai.Client(api_key=key)
    return _clients[key]


def _l2_normalize(vec: list[float]) -> list[float]:
    # Sub-3072 outputs of gemini-embedding-001 are NOT pre-normalized; cosine
    # search in Qdrant assumes unit vectors, so normalize here.
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def _embed_batch(batch: list[str], task_type: str) -> list[list[float]]:
    """Embed one batch, rotating through keys and failing over on quota errors."""
    keys = keyring.ordered_from_next()
    last_err: Exception | None = None
    for key in keys:
        try:
            resp = _client_for(key).models.embed_content(
                model=settings.embed_model.replace("models/", ""),
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embed_dim,
                ),
            )
            return [_l2_normalize(list(e.values)) for e in resp.embeddings]
        except Exception as e:  # noqa: BLE001
            last_err = e
            if is_quota_error(e):
                continue  # this key is rate-limited — try the next
            raise
    raise RuntimeError(f"All Google keys exhausted for embeddings: {last_err}")


def _embed(texts: Sequence[str], task_type: str) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        out.extend(_embed_batch(list(texts[i : i + _BATCH]), task_type))
    return out


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    """Embed transcript chunks for storage."""
    if not texts:
        return []
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed a single user question for search."""
    return _embed([text], "RETRIEVAL_QUERY")[0]


async def warmup() -> None:
    """Construct the genai client + warm the TLS/HTTP connection at startup so
    the first real query doesn't pay cold-start. Best-effort: never blocks or
    fails app startup. Costs one tiny embedding request per worker boot."""
    import asyncio
    import logging

    if not keyring:
        return
    try:
        await asyncio.to_thread(embed_query, "warmup")
        logging.getLogger(__name__).info("embedding client warmed")
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("embedding warmup skipped: %s", e)
