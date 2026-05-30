# CreatorRAG

Give it a YouTube video and an Instagram Reel. It pulls both transcripts and
their stats, works out the engagement rate, and lets you chat with the content —
the answers stream in, cite the exact moment in the video they came from, and the
chat remembers what you asked earlier.

I built this for the CreatorJoy screening. The brief wanted a dynamic full-stack
RAG chatbot with LangGraph + embeddings + a vector DB, and a real opinion on how
to run it cheaply at scale. This README is the honest version: what it does, why
I made the calls I made, and where the seams are — most of which come from the
fact that I built the whole thing on free tiers.

---

## The one thing that actually matters

Everything here is standard except **Instagram**, which fights you, and
**YouTube on a server**, which also fights you. So most of the engineering went
into making ingestion reliable and keeping the rest boring. If you only read one
section, read "The hard parts" below.

---

## Running it

You need Docker (for Redis, Qdrant, Postgres) and a few free API keys.

```bash
cp .env.example .env          # fill in the keys (see below)
docker compose up -d          # redis + qdrant + postgres

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # terminal 1
arq app.pipeline.worker.WorkerSettings        # terminal 2 (the worker)

# frontend
cd ../frontend
cp .env.local.example .env.local
npm install
npm run dev                                    # http://localhost:3000
```

Or use the Makefile: `make infra`, `make api`, `make worker`, `make web`.

### Keys you need

| Key | What for | Where |
|-----|----------|-------|
| `GOOGLE_API_KEY` (+ `_2`, `_3`) | Gemini chat + embeddings | aistudio.google.com/apikey |
| `GROQ_API_KEY` | Whisper transcription | console.groq.com/keys |
| `APIFY_TOKEN` | Instagram + YouTube scraping | console.apify.com |
| `YOUTUBE_API_KEY` | YouTube metadata (Data API v3) | console.cloud.google.com |

I'm running multiple Google keys on purpose — that's a free-tier thing I explain
later.

---

## How it works

```
You → Next.js → FastAPI  (submit two URLs)
        → hash the URL, check if we've seen it (dedup)
        → if new/stale: push a job onto Redis
        → a worker picks it up:
              scrape metadata + transcript   (Apify / Data API / Groq Whisper)
              compute engagement rate
              chunk the transcript, embed it (Gemini), store in Qdrant
              save everything to Postgres
        → frontend polls until both videos are "ready"
        → chat: LangGraph agent answers over Qdrant, streams via SSE
```

Two videos are a "pair". Video A is the YouTube one, Video B is the Instagram
one. The chat scopes its searches to just those two.

Engagement rate is `(likes + comments) / views × 100`, with guards so a video
with hidden likes or zero views shows "n/a" instead of a fake number.

---

## The stack, and why

- **FastAPI + Redis queue (arq) + worker pool.** Scraping and transcription are
  slow and flaky, so they don't belong in the request. The API just enqueues;
  workers do the heavy lifting. To handle more load you run more workers.
- **Qdrant** for vectors (not pgvector, even though I already run Postgres).
  Qdrant's payload filtering lets me scope a search to "just Video A" cheaply,
  and the vector workload scales separately from the relational one. For two
  videos it's overkill; at 1000/day it's the right shape.
- **Gemini 2.5 Flash + `gemini-embedding-001`.** The brief named
  `text-embedding-004`, but Google deprecated that in January 2026, so I switched
  to its successor and truncated it to 768 dimensions (it supports that) — smaller
  index, basically the same quality on short transcripts.
- **LangGraph** for the agent: a small ReAct loop with one retrieval tool. The
  model decides when to search the transcripts vs. answer from the stats I hand
  it in the system prompt.
- **Postgres** for metadata, status, chat history, and thumbnails. Plain SQL, no
  ORM. Works the same locally or on Supabase — just change `DATABASE_URL`.

---

## The hard parts

**Instagram.** You can't reliably scrape it from a server anymore. yt-dlp won't
give you the creator's follower count and usually wants a login. So I use **Apify**
(one actor for the reel's stats + media, another for the follower count), and I
put it behind a provider interface with a **cached-fixture fallback** — if Apify
fails mid-demo, it serves a saved reel instead of crashing. That fallback is the
single most important design decision in here.

**YouTube on a cloud IP.** YouTube blocks datacenter IPs — both yt-dlp and the
transcript library get "confirm you're not a bot" from a server. I confirmed this
the hard way on this box. So for deployment I don't scrape YouTube directly:

- **Metadata** comes from the official **YouTube Data API v3** (works from any IP,
  free quota, gives views/likes/comments/subscribers/duration).
- **Transcript** comes from an **Apify** actor that runs on Apify's IPs.

There's a toggle for this. The default "fast hybrid" (Data API + a quick
transcript actor) finishes in ~15s with approximate timestamps; flip "Exact
YouTube timestamps" and it uses a heavier actor that returns real SRT subtitle
timings but takes ~70s. Locally (residential IP), it just uses yt-dlp and the
captions API and none of this matters.

**Messy input.** People paste URLs with tracking junk, or two URLs glued
together. The backend now canonicalizes every URL down to the real video id
before anything touches it, so garbage in still works.

---

## Extra things I added (the production polish)

The core was working early, so I spent the rest of the time making it behave like
something you'd actually deploy:

- **Persistent, bounded chat memory.** Conversation history lives in Postgres
  (not in process memory), so it survives restarts. Each turn only replays the
  last N messages, so a long chat doesn't quietly blow up the token bill.
- **Metadata freshness (TTL).** Dedup is great, but views and likes change. A
  video older than 24h gets re-scraped on the next submit instead of serving
  stale numbers forever.
- **Better retrieval.** A relevance floor (drops weak matches), an MMR rerank (so
  you don't get three near-identical snippets), and a time-window filter so
  "compare the hooks in the first 5 seconds" actually searches the opening, not
  the whole video.
- **Multi-key rotation with failover.** More on this in the free-tier section —
  it's the reason there are three Google keys.
- **Job retries + dead-letter.** Transient failures (network, rate limits,
  gateway errors) retry with exponential backoff; permanent ones fail fast and
  get recorded so you can see what died.
- **Persisted thumbnails.** Instagram's image URLs are signed and expire, and the
  CDN blocks hotlinking, so the browser can't load them directly. I download the
  thumbnail once at ingest, store the bytes, and serve them through the backend.
- **API auth + per-IP rate limiting** on the expensive endpoints, off by default
  for local dev.
- **Frontend niceties:** loading skeletons, a retry button on failed cards, a
  "new chat" button, markdown answers, and citation chips that deep-link to the
  video at the right second.
- **Tests + CI.** ~40 unit tests plus a couple of integration tests, and a
  GitHub Actions pipeline (lint, type-check, tests with real service containers,
  frontend build).

---

## Free-tier trade-offs (read this)

I built the whole thing on free tiers, which shaped a surprising number of
decisions. The honest summary: **at this scale, rate limits break before money
does.**

- **Gemini free tier is ~20 chat requests/day per project.** That's tiny. It's
  fine for a human clicking through a demo, but it dies instantly under any real
  use. My fix is **key rotation**: drop in several Google keys and the app
  round-robins across them and fails over when one hits its limit, so three keys
  ≈ three times the daily quota. The real fix for production is a paid key; the
  rotation is the free-tier workaround.
- **The Gemini keys I'm using are ephemeral.** The ones I had start with `AQ.`
  (AI Studio tokens) rather than the usual `AIza…`. They work but can expire — for
  a real deployment you'd generate standard keys. The Data API key has to be a
  standard `AIza…` key with the API enabled; the ephemeral ones get rejected
  there.
- **Groq Whisper free tier** caps requests/day and audio-seconds/hour. Fine for a
  handful of videos; at volume you'd self-host `faster-whisper` on a GPU and the
  per-video cost basically goes to zero.
- **Apify free credits** ($5/month, no card) cover thousands of scrapes — plenty
  for a demo — but it's the main paid line item at scale, and Instagram's
  anti-bot churn means the occasional re-run.
- **YouTube datacenter-IP blocking** is why ingestion routes through Apify/Data
  API on a server. The cheaper-at-scale alternative is residential proxies
  (which I wired support for but didn't pay for).
- **Everything degrades gracefully.** If a key is rate-limited the chat says
  "wait a few seconds" instead of erroring; if Apify fails Instagram falls back to
  a fixture; if YouTube captions are blocked it falls back to an actor, then to
  Whisper. The point was that a free-tier demo shouldn't be allowed to hard-fail.

---

## Cost & scale: 1000 creators/day

Call it 2000 videos/day (one YouTube + one Instagram each), ~3 minutes long.

- **Instagram scraping (Apify)** is the #1 cost *and* the #1 reliability risk —
  roughly $6/day at this volume, and it's the thing most likely to break.
- **Transcription** is next (~$4/day on Groq). At this scale you'd self-host
  Whisper on a GPU and remove both the cost and the free-tier rate cap.
- **Embeddings, Postgres, Qdrant storage** are rounding errors.
- **YouTube metadata** via the Data API is effectively free (10k units/day, ~2
  units per video).
- **Chat (Gemini Flash)** is usage-driven, not per-ingest, and cheap per turn —
  but long conversations are a silent multiplier, which is exactly why I cap the
  replayed history.

So the lowest-cost / highest-quality version at scale: dedup hard by URL hash
(creators reshare the same videos), batch embeddings, self-host Whisper once you
clear the free tier, keep Gemini Flash, and treat Instagram as the dependency to
cache and route around. The first thing I'd change with a budget is moving
transcription off Groq's free tier onto a GPU, and the Gemini keys onto a paid
plan.

---

## Testing

```bash
cd backend && source .venv/bin/activate
pytest                                  # unit tests
CREATORRAG_INTEGRATION=1 pytest         # also hit live Postgres/Qdrant
```

Covers the fiddly bits: engagement-rate edge cases, chunk-boundary timestamps,
URL dedup/canonicalization, the MMR rerank, the TTL logic, key rotation +
failover, and the provider routing/fallback.

---

## Honest limitations

- The committed Instagram fixture is placeholder data — swap in a real reel before
  recording a demo (`backend/fixtures/README.md`).
- Fast-hybrid YouTube timestamps are approximate (word-windowed); the exact toggle
  is there if you need precise ones.
- Auth is an API key, which is gating, not real auth — the per-IP rate limit is
  the meaningful protection. Real user login would be the next step.
- It's tuned for two videos at a time, which is the brief. Scaling the *comparison*
  beyond a pair would need schema and UI changes.

---

## Layout

```
backend/app
  config.py            all settings, nothing hard-coded
  urls.py              URL parsing / canonicalization
  db.py                Postgres: dedup, status, chat history, thumbnails
  embeddings.py        gemini-embedding-001, key rotation
  qdrant_store.py      collection, upsert, filtered search + MMR
  media.py             thumbnail fetch/proxy
  security.py          API key + per-IP rate limit
  keyring.py           Google API key rotation + quota detection
  ingest/              providers (youtube/instagram/fixtures), transcription, chunking
  pipeline/            arq worker, ingest job, retries
  rag/                 LangGraph agent, retriever tool, SSE streaming
  routes/              videos, chat, health
frontend/src           Next.js app — cards, streaming chat, transcript modal
```
