"""API auth + per-IP rate limiting for the expensive endpoints.

- `require_api_key`: enforced only when API_KEY is configured (no-op in dev).
- `rate_limit`: Redis-backed fixed-window counter per client IP. We already run
  Redis for the queue, so no new dependency.

Note: an API key shipped to a browser SPA is gating, not real auth (it's
visible client-side). The per-IP rate limit is the meaningful abuse protection;
real user auth (login/JWT) would be the next step.
"""
from __future__ import annotations

import time

from fastapi import Header, HTTPException, Request

from .config import settings
from .pipeline.queue import get_queue


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_min
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    bucket = int(time.time() // 60)  # 1-minute fixed window
    key = f"ratelimit:{ip}:{bucket}"
    redis = await get_queue()  # ArqRedis is a redis.asyncio client
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 60)
    if n > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({limit}/min). Slow down and retry.",
        )
