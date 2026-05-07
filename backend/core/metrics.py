from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict


@dataclass
class MetricsStore:
    total_requests: int = 0
    total_verifications: int = 0
    total_response_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    verdict_distribution: Dict[str, int] = field(default_factory=lambda: {"APPLY": 0, "VERIFY": 0, "SKIP": 0})
    _lock: Lock = field(default_factory=Lock)

    def record_request(self, duration_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_response_time_ms += duration_ms

    def record_verification(self, verdict: str, *, cache_hit: bool) -> None:
        with self._lock:
            self.total_verifications += 1
            if verdict in self.verdict_distribution:
                self.verdict_distribution[verdict] += 1
            if cache_hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg_ms = (self.total_response_time_ms / self.total_requests) if self.total_requests else 0.0
            total_cache = self.cache_hits + self.cache_misses
            cache_hit_rate = (self.cache_hits / total_cache) if total_cache else 0.0
            return {
                "total_requests": self.total_requests,
                "total_verifications": self.total_verifications,
                "verdict_distribution": dict(self.verdict_distribution),
                "avg_response_time_ms": round(avg_ms, 2),
                "cache_hit_rate": round(cache_hit_rate, 4),
                "generated_at_ms": int(time.time() * 1000),
            }


METRICS = MetricsStore()
