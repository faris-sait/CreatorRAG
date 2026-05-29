-- CreatorRAG schema. Plain Postgres (works locally or on Supabase unchanged).
--
-- Design note: chunks in Qdrant are tagged with the *stable* video id, not the
-- per-comparison slot "A"/"B". A/B is a view onto a `pair`, resolved at query
-- time. This is what makes dedup meaningful — the same video reused in a new
-- comparison is never re-scraped, re-transcribed, or re-embedded.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- One row per unique video (deduped by url_hash).
CREATE TABLE IF NOT EXISTS videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT NOT NULL,
    url_hash        TEXT NOT NULL UNIQUE,            -- sha256 of normalized URL
    platform        TEXT NOT NULL,                   -- 'youtube' | 'instagram'
    status          TEXT NOT NULL DEFAULT 'queued',  -- queued|fetching|transcribing|embedding|ready|error
    -- Full metadata blob (views, likes, comments, creator, follower_count,
    -- hashtags, upload_date, duration, title, thumbnail, source provider...).
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    engagement_rate DOUBLE PRECISION,                -- (likes+comments)/views*100
    transcript      TEXT,                            -- full transcript text
    transcript_len  INTEGER,                         -- char count
    num_chunks      INTEGER DEFAULT 0,
    thumbnail_data  BYTEA,                           -- persisted thumbnail bytes
    thumbnail_type  TEXT,                            -- its content-type
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A comparison of exactly two videos. Slot A = first input, Slot B = second.
CREATE TABLE IF NOT EXISTS pairs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    a_video_id  UUID NOT NULL REFERENCES videos(id),
    b_video_id  UUID NOT NULL REFERENCES videos(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chat history, persisted so conversation memory survives restarts. We replay
-- a bounded window (last N) into the agent each turn to cap context cost.
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,          -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migrations for existing databases (CREATE TABLE IF NOT EXISTS won't add cols).
ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_data BYTEA;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_type TEXT;

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_pairs_created ON pairs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, id);
