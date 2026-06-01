import asyncio
import math

import app.rag.agent as agent
from app.qdrant_store import _dot, _mmr
from app.rag.agent import time_window_seconds


def _unit(*xs):
    n = math.sqrt(sum(x * x for x in xs)) or 1.0
    return [x / n for x in xs]


def test_dot_of_unit_vectors_is_cosine():
    assert abs(_dot(_unit(1, 0), _unit(1, 0)) - 1.0) < 1e-9
    assert abs(_dot(_unit(1, 0), _unit(0, 1))) < 1e-9


def test_mmr_skips_near_duplicate_for_diversity():
    cands = [
        {"score": 0.90, "_vec": _unit(1, 0, 0), "chunk_index": 0},
        {"score": 0.88, "_vec": _unit(1, 0.05, 0), "chunk_index": 1},  # ~dup of 0
        {"score": 0.60, "_vec": _unit(0, 1, 0), "chunk_index": 2},  # diverse
    ]
    picked = [c["chunk_index"] for c in _mmr(cands, k=2, lambda_=0.6)]
    assert picked == [0, 2]  # top relevance, then the diverse one (not the dup)


def test_mmr_pure_relevance_when_lambda_one():
    cands = [
        {"score": 0.9, "_vec": _unit(1, 0), "chunk_index": 0},
        {"score": 0.8, "_vec": _unit(1, 0), "chunk_index": 1},
        {"score": 0.7, "_vec": _unit(0, 1), "chunk_index": 2},
    ]
    picked = [c["chunk_index"] for c in _mmr(cands, k=2, lambda_=1.0)]
    assert picked == [0, 1]  # diversity ignored → top-2 by score


# ── "first N seconds" / hook intent → time-window retrieval ────────────────
# Regression: the single-pass retrieve node must map a "first 5 seconds"/hook
# question to qdrant_store.search(max_start=...), or the opening chunks never
# get retrieved and the model answers "can't find the first 5 seconds".

def test_time_window_parses_explicit_seconds():
    assert time_window_seconds("Compare the hooks in the first 5 seconds.") == 5.0
    assert time_window_seconds("what happens in the first 10 seconds?") == 10.0


def test_time_window_parses_minutes():
    assert time_window_seconds("walk me through the first 2 minutes") == 120.0


def test_time_window_defaults_for_bare_hook_intent():
    # No explicit number, but clearly about the opening → a window, not None.
    assert time_window_seconds("compare the hooks of both videos") is not None
    assert time_window_seconds("how do the openings compare?") is not None


def test_time_window_none_for_non_time_questions():
    assert time_window_seconds("What's the engagement rate of each?") is None
    assert time_window_seconds("Who is the creator of Video B?") is None
    assert time_window_seconds("Suggest improvements for B based on what worked in A.") is None


def test_retrieve_applies_time_window_and_relaxes_floor(monkeypatch):
    captured: dict = {}

    async def fake_search(_qvec, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(agent.qdrant_store, "search", fake_search)
    monkeypatch.setattr(agent, "embed_query", lambda q: [0.1, 0.2])
    asyncio.run(
        agent._retrieve_context(
            "Compare the hooks in the first 5 seconds.", "a", "b", {"a": "A", "b": "B"}
        )
    )
    assert captured.get("max_start") == 5.0
    # opening is hard-constrained by time, so the relevance floor must be relaxed
    assert captured.get("score_threshold") == 0.0


def test_retrieve_plain_search_for_metadata_question(monkeypatch):
    captured: dict = {}

    async def fake_search(_qvec, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(agent.qdrant_store, "search", fake_search)
    monkeypatch.setattr(agent, "embed_query", lambda q: [0.1, 0.2])
    asyncio.run(
        agent._retrieve_context(
            "What's the engagement rate of each?", "a", "b", {"a": "A", "b": "B"}
        )
    )
    assert "max_start" not in captured  # no time filter → normal floor applies
