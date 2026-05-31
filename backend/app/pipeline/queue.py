"""API-side handle to the arq queue (enqueue ingest jobs)."""
from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from ..config import settings

_redis: ArqRedis | None = None


async def get_queue() -> ArqRedis:
    global _redis
    if _redis is None:
        _redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _redis


async def close_queue() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def enqueue_ingest(
    video_id: str,
    url: str,
    platform: str,
    exact_yt: bool = False,
    is_short: bool = False,
) -> None:
    q = await get_queue()
    job_id = f"ingest:{video_id}"
    # _job_id keeps it idempotent while a job is queued/in-flight. But arq also
    # refuses to enqueue when a *completed* result with this id still exists
    # (within keep_result), which would silently strand a re-submission at
    # "queued". So drop any stale result first, then enqueue.
    try:
        await q.delete(f"arq:result:{job_id}")
    except Exception:
        pass
    await q.enqueue_job(
        "ingest_video", video_id, url, platform, exact_yt, is_short, _job_id=job_id
    )
