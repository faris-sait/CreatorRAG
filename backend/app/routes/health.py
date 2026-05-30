"""Health + config introspection (handy in the demo to show what's wired)."""
from __future__ import annotations

from fastapi import APIRouter

from .. import db, qdrant_store
from ..config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    out: dict = {"status": "ok"}
    try:
        async with db.pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
        out["postgres"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["postgres"] = f"error: {e}"
        out["status"] = "degraded"
    try:
        out["qdrant_chunks"] = await qdrant_store.count()
    except Exception as e:  # noqa: BLE001
        out["qdrant_chunks"] = f"error: {e}"
        out["status"] = "degraded"
    out["config"] = {
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "use_fixtures": settings.use_fixtures,
        "google_key_set": settings.has_google,
        "google_keys_count": len(settings.google_keys),
        "groq_key_set": settings.has_groq,
        "apify_token_set": settings.has_apify,
    }
    return out
