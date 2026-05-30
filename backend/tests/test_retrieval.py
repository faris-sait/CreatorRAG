import math

from app.qdrant_store import _dot, _mmr


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
