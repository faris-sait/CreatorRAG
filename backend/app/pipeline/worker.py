"""arq worker: a horizontally-scalable pool of async ingest workers.

Run with:  arq app.pipeline.worker.WorkerSettings

Each worker process pulls ingest jobs off Redis and runs them concurrently
(max_jobs). To scale to 1000 creators/day you just run more of these — the
queue decouples ingestion throughput from the API.
"""
from __future__ import annotations

import logging

from arq.connections import RedisSettings

from .. import db, qdrant_store
from ..config import settings
from .tasks import ingest_video

logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    await db.init_pool()
    await qdrant_store.ensure_collection()


async def shutdown(ctx: dict) -> None:
    await db.close_pool()


class WorkerSettings:
    functions = [ingest_video]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10           # concurrent ingests per worker process
    job_timeout = 600       # seconds; Whisper + scraping can be slow
    keep_result = 3600
