# Backend image: serves both the FastAPI API and the arq ingest worker
# (same code, different command — see docker-compose.prod.yml).
FROM python:3.11-slim

# Flush logs straight to stdout (so `docker logs` is live) and skip .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is REQUIRED at runtime: yt-dlp and the Groq Whisper transcription path
# both shell out to it. Without it, ingestion fails on audio extraction.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so the layer is cached across code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Run as an unprivileged user, not root.
RUN useradd --create-home --uid 1000 app

# App code (build context is ./backend, so this brings in ./backend/app).
COPY --chown=app:app . .

USER app

EXPOSE 8000

# Production server: no --reload, 2 workers to match the 2-CPU droplet.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
