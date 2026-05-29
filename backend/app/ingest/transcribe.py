"""Audio → timestamped transcript via Groq Whisper (whisper-large-v3-turbo).

We ask for verbose_json so we get per-segment {start, end, text}. Those
timestamps flow all the way through chunking into Qdrant payloads, which is how
the chat agent can cite '[Video A @ 0:12]'.

Audio comes either as a local file (YouTube download / fixture) or a remote
media URL (Apify videoUrl), which we stream to a temp file first.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
from groq import Groq

from ..config import settings

TMP_DIR = Path(__file__).resolve().parents[2] / "tmp"
TMP_DIR.mkdir(exist_ok=True)


async def _download(url: str) -> str:
    suffix = ".mp4"
    fd, path = tempfile.mkstemp(suffix=suffix, dir=TMP_DIR)
    os.close(fd)
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    return path


def _transcribe_file(path: str) -> list[dict]:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set — cannot transcribe audio")
    client = Groq(api_key=settings.groq_api_key)
    with open(path, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(os.path.basename(path), f.read()),
            model=settings.whisper_model,
            response_format="verbose_json",
        )
    segments = getattr(resp, "segments", None) or []
    out = []
    for s in segments:
        # groq returns dict-like segment objects
        start = s.get("start") if isinstance(s, dict) else getattr(s, "start", None)
        end = s.get("end") if isinstance(s, dict) else getattr(s, "end", None)
        text = s.get("text") if isinstance(s, dict) else getattr(s, "text", "")
        out.append({"start": start, "end": end, "text": (text or "").strip()})
    if not out:  # some short clips return only top-level text
        text = getattr(resp, "text", "") or ""
        out = [{"start": 0.0, "end": None, "text": text.strip()}]
    return out


async def transcribe(
    audio_path: str | None = None, audio_url: str | None = None
) -> list[dict]:
    """Return [{start, end, text}] segments from a local file or remote URL."""
    path = audio_path
    cleanup = False
    if path is None:
        if not audio_url:
            raise ValueError("transcribe() needs audio_path or audio_url")
        path = await _download(audio_url)
        cleanup = True
    try:
        return await asyncio.to_thread(_transcribe_file, path)
    finally:
        if cleanup and path and os.path.exists(path):
            os.remove(path)
