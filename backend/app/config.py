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

    # LLM + embeddings
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    embed_model: str = "models/gemini-embedding-001"
    embed_dim: int = 768

    # Transcription
    groq_api_key: str = ""
    whisper_model: str = "whisper-large-v3-turbo"

    # Instagram
    apify_token: str = ""
    use_fixtures: bool = True

    # Infra
    database_url: str = "postgresql://creatorrag:creatorrag@localhost:5432/creatorrag"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "video_chunks"

    # Chunking
    chunk_tokens: int = 400
    chunk_overlap: int = 60

    # App
    backend_cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def has_google(self) -> bool:
        return bool(self.google_api_key)

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
