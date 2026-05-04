"""Minimal cache store interface + in-memory implementation for tests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol


class CacheStore(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


@dataclass
class InMemoryCache:
    """TTL cache using monotonic clock; inject ``now_fn`` for deterministic tests."""

    now_fn: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> Optional[str]:
        row = self._data.get(key)
        if not row:
            return None
        expires_at, payload = row
        if self.now_fn() >= expires_at:
            del self._data[key]
            return None
        return payload

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._data[key] = (self.now_fn() + ttl_seconds, value)
