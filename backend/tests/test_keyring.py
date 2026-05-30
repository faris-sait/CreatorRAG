import pytest

from app.keyring import KeyRing, is_quota_error


def test_round_robin_cycles():
    kr = KeyRing(["k1", "k2", "k3"])
    assert [kr.next() for _ in range(5)] == ["k1", "k2", "k3", "k1", "k2"]


def test_ordered_from_next_advances_start():
    kr = KeyRing(["k1", "k2", "k3"])
    assert kr.ordered_from_next() == ["k1", "k2", "k3"]
    assert kr.ordered_from_next() == ["k2", "k3", "k1"]
    assert kr.ordered_from_next() == ["k3", "k1", "k2"]


def test_empty_ring_is_falsy_and_raises():
    kr = KeyRing([])
    assert not kr
    assert len(kr) == 0
    with pytest.raises(RuntimeError):
        kr.next()


@pytest.mark.parametrize(
    "msg, expected",
    [
        ("Error 429 Too Many Requests", True),
        ("RESOURCE_EXHAUSTED", True),
        ("quota exceeded for model", True),
        ("rate limit hit", True),
        ("connection refused", False),
        ("invalid api key", False),
    ],
)
def test_is_quota_error(msg, expected):
    assert is_quota_error(Exception(msg)) is expected
