from datetime import datetime, timedelta, timezone

from app.config import settings
from app.routes.videos import _is_stale


def _video(status="ready", hours_ago=0.0):
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"status": status, "updated_at": ts.isoformat()}


def test_fresh_ready_video_not_stale():
    assert _is_stale(_video("ready", hours_ago=1)) is False


def test_old_ready_video_is_stale(monkeypatch):
    monkeypatch.setattr(settings, "metadata_ttl_hours", 24.0)
    assert _is_stale(_video("ready", hours_ago=48)) is True


def test_non_ready_never_stale():
    assert _is_stale(_video("queued", hours_ago=100)) is False
    assert _is_stale(_video("error", hours_ago=100)) is False


def test_missing_updated_at_not_stale():
    assert _is_stale({"status": "ready"}) is False
