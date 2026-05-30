from app.ingest.providers.base import engagement_rate


def test_normal_case():
    # (likes + comments) / views * 100
    assert engagement_rate(132400, 2870, 1840000) == 7.35


def test_none_views_returns_none():
    assert engagement_rate(100, 10, None) is None


def test_zero_views_returns_none():
    # guard divide-by-zero rather than crash or report 0%
    assert engagement_rate(100, 10, 0) is None


def test_none_likes_treated_as_zero():
    assert engagement_rate(None, 10, 1000) == 1.0


def test_all_none_engagement_zero_when_views_known():
    assert engagement_rate(None, None, 1000) == 0.0
