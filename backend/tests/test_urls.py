import pytest

from app.db import normalize_url, url_hash
from app.ingest.providers.factory import detect_platform


def test_youtube_dedup_ignores_tracking_params():
    a = "https://www.youtube.com/watch?v=abc12345678&t=42s&feature=share"
    b = "https://youtube.com/watch?v=abc12345678"
    # both keep only ?v= → same hash
    assert url_hash(a) == url_hash(b)


def test_trailing_slash_and_fragment_normalized():
    a = "https://www.instagram.com/reel/CtjUklXt5Vp/#comments"
    b = "https://www.instagram.com/reel/CtjUklXt5Vp"
    assert normalize_url(a) == normalize_url(b)


def test_different_videos_differ():
    a = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    b = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    assert url_hash(a) != url_hash(b)


def test_detect_platform():
    assert detect_platform("https://youtu.be/abc") == "youtube"
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_platform("https://www.instagram.com/reel/x/") == "instagram"


def test_detect_platform_rejects_unknown():
    with pytest.raises(ValueError):
        detect_platform("https://vimeo.com/123")
