"""Google API key rotation.

Pools all configured Google keys and hands them out round-robin so daily
free-tier quota is shared across keys (3 keys ≈ 3× the 20 req/day cap). Callers
that want resilience iterate `ordered_from_next()` and fail over to the next key
on a quota/429 error.

Thread-safe (the rotation index is touched from both the async chat path and the
embeddings thread-pool).
"""
from __future__ import annotations

import threading

from .config import settings


def is_quota_error(exc: Exception) -> bool:
    """True if an exception looks like a rate-limit / quota exhaustion."""
    s = str(exc).lower()
    return (
        "429" in s
        or "resourceexhausted" in s
        or "resource_exhausted" in s
        or "quota" in s
        or "rate limit" in s
        or "rate_limit" in s
    )


class KeyRing:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys
        self._i = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)

    def all(self) -> list[str]:
        return list(self._keys)

    def next(self) -> str:
        """Next key, round-robin."""
        if not self._keys:
            raise RuntimeError("No GOOGLE_API_KEY configured")
        with self._lock:
            k = self._keys[self._i % len(self._keys)]
            self._i += 1
            return k

    def ordered_from_next(self) -> list[str]:
        """All keys, starting at the next round-robin position — for failover."""
        if not self._keys:
            raise RuntimeError("No GOOGLE_API_KEY configured")
        with self._lock:
            start = self._i
            self._i += 1
        n = len(self._keys)
        return [self._keys[(start + j) % n] for j in range(n)]


keyring = KeyRing(settings.google_keys)
