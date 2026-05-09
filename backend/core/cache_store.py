"""Cache store interface + implementations.

- In-memory TTL cache (default for local dev/tests).
- Optional Redis cache when CACHE_URL is configured (Sprint 10).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol


class CacheStore(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


@dataclass
class InMemoryCache:
    """TTL cache using monotonic clock; inject ``now_fn`` for deterministic tests."""

    now_fn: Callable[[], float] = time.monotonic
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._data.get(key)
            if not row:
                return None
            expires_at, payload = row
            if self.now_fn() >= expires_at:
                del self._data[key]
                return None
            return payload

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (self.now_fn() + ttl_seconds, value)


class RedisCache:
    """Redis-backed cache store (string values).

    Redis dependency is imported lazily so unit tests can run without it.
    """

    def __init__(self, url: str, *, connect_timeout_s: float = 1.0, timeout_s: float = 1.0) -> None:
        self._url = url
        self._connect_timeout_s = float(connect_timeout_s)
        self._timeout_s = float(timeout_s)

    def _client(self):
        import redis  # type: ignore

        return redis.Redis.from_url(
            self._url,
            socket_connect_timeout=self._connect_timeout_s,
            socket_timeout=self._timeout_s,
            decode_responses=True,
        )

    def get(self, key: str) -> Optional[str]:
        try:
            return self._client().get(key)
        except Exception:  # noqa: BLE001
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self._client().set(name=key, value=value, ex=int(ttl_seconds))
        except Exception:  # noqa: BLE001
            return None


def cache_ping(cache_url: str) -> bool:
    """Return True if Redis responds to PING quickly."""

    try:
        c = RedisCache(cache_url)._client()
        return bool(c.ping())
    except Exception:  # noqa: BLE001
        return False
