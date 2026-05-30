from app.ingest.chunk import chunk_segments, full_text

SEGS = [
    {"start": 0.0, "end": 3.0, "text": "First segment about hooks."},
    {"start": 3.0, "end": 6.0, "text": "Second segment with more words here."},
    {"start": 6.0, "end": 9.0, "text": "Third segment continues the thought."},
    {"start": 9.0, "end": 12.0, "text": "Fourth and final segment wraps up."},
]


def test_chunks_preserve_timestamps():
    chunks = chunk_segments(SEGS, max_tokens=12, overlap_tokens=0)
    assert chunks
    assert chunks[0]["start"] == 0.0
    assert chunks[-1]["end"] == 12.0
    # chunk_index is contiguous from 0
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_single_chunk_when_budget_large():
    chunks = chunk_segments(SEGS, max_tokens=10_000, overlap_tokens=0)
    assert len(chunks) == 1
    assert chunks[0]["start"] == 0.0 and chunks[0]["end"] == 12.0


def test_empty_segments():
    assert chunk_segments([]) == []
    assert chunk_segments([{"start": 0, "end": 1, "text": "   "}]) == []


def test_overlap_carries_context():
    no_overlap = chunk_segments(SEGS, max_tokens=12, overlap_tokens=0)
    with_overlap = chunk_segments(SEGS, max_tokens=12, overlap_tokens=8)
    # overlap should not reduce the number of chunks and should repeat some text
    assert len(with_overlap) >= len(no_overlap)


def test_full_text_joins_segments():
    assert "First segment" in full_text(SEGS)
    assert "final segment" in full_text(SEGS)
