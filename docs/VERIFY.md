# End-to-end verification

Two modes. Start with **fixture mode** — it proves the entire pipeline with the
fewest moving parts and zero Instagram risk.

## 0. Prerequisites
```bash
cp .env.example .env          # set at least GOOGLE_API_KEY (and GROQ_API_KEY for live YT)
docker compose up -d          # redis + qdrant + postgres healthy
docker compose ps             # all "healthy"
```

## 1. Start the stack
```bash
# backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000     # terminal 1
arq app.pipeline.worker.WorkerSettings        # terminal 2

# frontend
cd frontend && npm run dev                     # terminal 3 → http://localhost:3000
```

Sanity check the API:
```bash
curl -s localhost:8000/api/health | jq
# expect postgres:ok, qdrant_chunks:<n>, config flags reflecting your .env
```

## 2. Fixture mode (USE_FIXTURES=true, needs only GOOGLE_API_KEY)
The Instagram fixture already includes a transcript, so this path needs **no Groq
and no Apify** — only Google for embeddings + chat. Use a YouTube video that has
captions (so no Whisper needed) for a fully-keyed-by-Google run.

1. Open http://localhost:3000.
2. Paste a captioned YouTube URL into Video A; leave the Instagram default (or any
   `instagram.com/reel/...` URL — it resolves to the fixture).
3. Click **Analyze**. Watch both cards walk through
   `queued → fetching → transcribing → embedding → ready`.
4. Confirm each card shows views/likes/comments/creator/followers/hashtags and an
   **engagement rate**.
5. Confirm chunks landed:
   ```bash
   curl -s localhost:8000/api/health | jq .qdrant_chunks   # > 0
   ```
6. In the chat panel, click each of the 5 quick prompts. Verify:
   - tokens **stream** in,
   - answers carry **`📎 Video A/B @ m:ss`** citations,
   - the engagement-rate / follower-count answers match the cards,
   - a **follow-up** ("now suggest improvements for B") works without you
     re-stating context → memory.

## 3. Dedup
Re-submit the same pair. The already-`ready` videos return immediately and the
worker logs no new embedding work. `qdrant_chunks` count is unchanged.

## 4. Live mode (optional, needs APIFY_TOKEN + GROQ_API_KEY)
Set `USE_FIXTURES=false`, restart the worker, and submit two real URLs (a real
Instagram Reel + a YouTube video). Same flow, now against Apify + Groq + Gemini.
If Instagram blocks Apify, you'll see the worker log a fallback to the fixture —
the demo keeps going.

## 5. Tests
```bash
cd backend && source .venv/bin/activate && pytest -q
```
