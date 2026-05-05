"""Environment loading with optional strict (production) validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val.strip()


def _int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = _get(name)
    if raw is None:
        n = default
    else:
        n = int(raw)
    if n < min_v or n > max_v:
        raise ValueError(f"{name} must be between {min_v} and {max_v}, got {n}")
    return n


@dataclass(frozen=True, slots=True)
class EnvConfig:
    node_env: str
    cache_ttl_days: int
    source_pipeline_version: str
    scorer_version: str
    fetch_max_bytes: int
    fetch_max_redirects: int
    cache_url: Optional[str]
    search_api_endpoint: Optional[str]
    log_level: str

    @staticmethod
    def load(*, strict: bool = False) -> "EnvConfig":
        """Load configuration from the process environment.

        ``strict=True`` is intended for production/staging: fail fast when cache URL
        is absent (shared verification requires a real store in multi-instance deploys).
        """

        node_env = (_get("NODE_ENV", "development") or "development").lower()
        ttl = _int("CACHE_DEFAULT_TTL_DAYS", 14, min_v=10, max_v=30)
        fetch_bytes = _int("FETCH_MAX_BYTES", 2_097_152, min_v=64_000, max_v=20_000_000)
        fetch_redirs = _int("FETCH_MAX_REDIRECTS", 5, min_v=0, max_v=20)

        cache_url = _get("CACHE_URL")
        search_api_endpoint = _get("SEARCH_API_ENDPOINT")

        if strict or node_env in ("production", "staging"):
            if not cache_url:
                raise ValueError("CACHE_URL is required when strict=True or NODE_ENV is production/staging")

        return EnvConfig(
            node_env=node_env,
            cache_ttl_days=ttl,
            source_pipeline_version=_get("SOURCE_PIPELINE_VERSION", "1") or "1",
            scorer_version=_get("SCORER_VERSION", "1") or "1",
            fetch_max_bytes=fetch_bytes,
            fetch_max_redirects=fetch_redirs,
            cache_url=cache_url,
            search_api_endpoint=search_api_endpoint,
            log_level=(_get("LOG_LEVEL", "info") or "info").lower(),
        )
