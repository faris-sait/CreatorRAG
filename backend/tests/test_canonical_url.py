import pytest

from app.ingest.providers.factory import canonical_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        # two URLs glued together (the real paste-glitch bug)
        (
            "https://www.youtube.com/watch?v=zBZgdTb-dnswww.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=zBZgdTb-dns",
        ),
        # tracking params
        (
            "https://www.youtube.com/watch?v=zBZgdTb-dns&t=10s&feature=share",
            "https://www.youtube.com/watch?v=zBZgdTb-dns",
        ),
        # short link
        ("https://youtu.be/zBZgdTb-dns", "https://www.youtube.com/watch?v=zBZgdTb-dns"),
        # instagram reel with igsh param
        (
            "https://www.instagram.com/reel/DELhBGtvmBw/?igsh=cjJuaWVjdmU5YnZl",
            "https://www.instagram.com/reel/DELhBGtvmBw/",
        ),
    ],
)
def test_canonical_url(raw, expected):
    assert canonical_url(raw) == expected
