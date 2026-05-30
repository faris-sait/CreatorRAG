"""Streaming chat endpoint (SSE).

POST /api/chat {pair_id, session_id, message} → text/event-stream of
token / sources / done events. session_id is the memory key (thread_id).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..rag.stream import chat_stream
from ..security import rate_limit, require_api_key

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    pair_id: str
    session_id: str
    message: str


@router.post("/chat", dependencies=[Depends(rate_limit), Depends(require_api_key)])
async def chat(req: ChatRequest) -> StreamingResponse:
    pair = await db.get_pair(req.pair_id)
    if not pair:
        raise HTTPException(404, "pair not found")
    return StreamingResponse(
        chat_stream(pair, req.session_id, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
