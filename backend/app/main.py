"""FastAPI app entrypoint.

Run:  uvicorn app.main:app --reload --port 8000
(the arq worker runs separately: arq app.pipeline.worker.WorkerSettings)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, qdrant_store
from .config import settings
from .pipeline.queue import close_queue
from .routes import chat, health, videos


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await qdrant_store.ensure_collection()
    yield
    await close_queue()
    await db.close_pool()


app = FastAPI(title="CreatorRAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(videos.router)
app.include_router(chat.router)


@app.get("/")
async def root() -> dict:
    return {"name": "CreatorRAG API", "docs": "/docs"}
