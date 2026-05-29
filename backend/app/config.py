"""Central configuration, loaded from the repo-root .env.

Every tunable lives here so nothing downstream is hard-coded — inputs (the two
URLs) are the only hard-coded-able thing per the assignment rules.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (one level above backend/)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # LLM + embeddings.
    # Provide one key in GOOGLE_API_KEY, and optionally more for rotation:
    #   - GOOGLE_API_KEY_2, GOOGLE_API_KEY_3, ... (numbered), or
    #   - GOOGLE_API_KEYS as a comma-separated list.
    # All non-empty keys are pooled and round-robined (with quota failover) to
    # multiply the free-tier daily request cap.
    google_api_key: str = ""
    google_api_key_2: str = ""
    google_api_key_3: str = ""
    google_api_key_4: str = ""
    google_api_key_5: str = ""
    google_api_keys: str = ""  # optional comma-separated list
    llm_model: str = "gemini-2.5-flash"
    embed_model: str = "models/gemini-embedding-001"
    embed_dim: int = 768

    # Transcription
    groq_api_key: str = ""
    whisper_model: str = "whisper-large-v3-turbo"

    # Instagram
    apify_token: str = ""
    use_fixtures: bool = True

    # YouTube (deployment-safe path).
    # Metadata via the official YouTube Data API v3 — reliable from any IP,
    # free 10k units/day. Get a key + enable the API at console.cloud.google.com.
    youtube_api_key: str = ""
    # Transcript path on cloud IPs needs a residential proxy (YouTube blocks
    # datacenter IPs). Provide ONE of:
    #   - Webshare residential creds (recommended), or
    #   - a generic proxy URL http://user:pass@host:port
    webshare_proxy_username: str = ""
    webshare_proxy_password: str = ""
    youtube_proxy_url: str = ""
    # Optional Netscape cookies.txt as an additional yt-dlp bypass.
    ytdlp_cookies_file: str = ""
    # Apify actor for YouTube transcripts (runs on Apify IPs → no proxy needed).
    # Used as a transcript fallback when captions are blocked from the server IP.
    apify_yt_transcript_actor: str = "topaz_sharingan/youtube-transcript-scraper-1"
    # Use Apify as the primary YouTube source (metadata + transcript in one
    # actor) instead of the Data API / yt-dlp path. Reliable from any IP.
    youtube_use_apify: bool = True

    # Infra
    database_url: str = "postgresql://creatorrag:creatorrag@localhost:5432/creatorrag"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "video_chunks"

    # Chunking
    chunk_tokens: int = 400
    chunk_overlap: int = 60

    # Retrieval
    retrieval_k: int = 6                # final chunks returned to the agent
    retrieval_fetch_k: int = 16         # over-fetch before MMR rerank
    retrieval_min_score: float = 0.3    # drop weakly-relevant chunks (cosine)
    retrieval_mmr_lambda: float = 0.6   # MMR: relevance vs diversity (1=pure relevance)

    # Conversation memory (persisted in Postgres, replayed bounded)
    chat_history_messages: int = 10     # how many prior messages to replay

    # Metadata freshness — re-scrape a ready video older than this (views/likes
    # change over time; dedup must not serve stale metrics forever).
    metadata_ttl_hours: float = 24.0

    # App
    backend_cors_origins: str = "http://localhost:3000"

    # Security. If api_key is set, mutating endpoints require X-API-Key.
    # rate_limit_per_min throttles per client IP (0 disables).
    api_key: str = ""
    rate_limit_per_min: int = 30

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def google_keys(self) -> list[str]:
        """All configured Google API keys, de-duped, order-preserving."""
        raw = [
            self.google_api_key,
            self.google_api_key_2,
            self.google_api_key_3,
            self.google_api_key_4,
            self.google_api_key_5,
            *self.google_api_keys.split(","),
        ]
        seen: set[str] = set()
        keys: list[str] = []
        for k in raw:
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
        return keys

    @property
    def has_google(self) -> bool:
        return bool(self.google_keys)

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_apify(self) -> bool:
        return bool(self.apify_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
