"""Environment loading with optional strict (production) validation.

Provider/env authority (Sprint 2 audit):
- SERPAPI_API_KEY / SEARCH_API_KEY
- SEARCH_API_ENDPOINT (optional override for provider endpoint)
- SEARCH_TIMEOUT_S / SEARCH_RETRY_COUNT / SEARCH_RATE_LIMIT_PER_MINUTE
- FIREWORKS_API_KEY / FIREWORKS_BASE_URL / FIREWORKS_MODEL / FIREWORKS_VISION_MODEL
- FIREWORKS_TIMEOUT_S / FIREWORKS_RETRY_COUNT
- ENABLE_LLM_SIGNALS / ENABLE_IMAGE_VERIFY / ENABLE_JOB_FETCH / RECOMMENDATIONS_ENABLED
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.config import AppConfig


def _int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    n = default
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
    search_timeout_s: int
    search_retry_count: int
    search_rate_limit_per_minute: int
    fireworks_base_url: str
    fireworks_model: str
    fireworks_vision_model: str
    fireworks_timeout_s: int
    fireworks_retry_count: int
    log_level: str
    pipeline_deadline_s: int
    llm_summary_confidence_threshold: int

    @staticmethod
    def load(*, strict: bool = False) -> "EnvConfig":
        """Load configuration from the process environment.

        ``strict=True`` is intended for production/staging: fail fast when cache URL
        is absent (shared verification requires a real store in multi-instance deploys).
        """

        app_cfg = AppConfig.load()
        node_env = str(app_cfg.get("NODE_ENV") or "development").lower()
        ttl = _int("CACHE_DEFAULT_TTL_DAYS", int(app_cfg.get("CACHE_DEFAULT_TTL_DAYS") or 14), min_v=10, max_v=30)
        fetch_bytes = _int("FETCH_MAX_BYTES", int(app_cfg.get("FETCH_MAX_BYTES") or 2_097_152), min_v=64_000, max_v=20_000_000)
        fetch_redirs = _int("FETCH_MAX_REDIRECTS", int(app_cfg.get("FETCH_MAX_REDIRECTS") or 5), min_v=0, max_v=20)

        cache_url = str(app_cfg.get("CACHE_URL")).strip() if app_cfg.get("CACHE_URL") else None
        search_api_endpoint = str(app_cfg.get("SEARCH_API_ENDPOINT") or "")
        search_timeout_s = _int("SEARCH_TIMEOUT_S", int(app_cfg.get("SEARCH_TIMEOUT_S") or 10), min_v=1, max_v=60)
        search_retry_count = _int("SEARCH_RETRY_COUNT", int(app_cfg.get("SEARCH_RETRY_COUNT") or 2), min_v=0, max_v=5)
        search_rate_limit = _int("SEARCH_RATE_LIMIT_PER_MINUTE", int(app_cfg.get("SEARCH_RATE_LIMIT_PER_MINUTE") or 60), min_v=1, max_v=10000)
        fw_base = str(app_cfg.get("FIREWORKS_BASE_URL") or "https://api.fireworks.ai/inference/v1")
        fw_model = str(app_cfg.get("FIREWORKS_MODEL") or "accounts/fireworks/models/kimi-k2-instruct")
        fw_vision_model = str(app_cfg.get("FIREWORKS_VISION_MODEL") or fw_model)
        fw_timeout_s = _int("FIREWORKS_TIMEOUT_S", int(app_cfg.get("FIREWORKS_TIMEOUT_S") or 10), min_v=1, max_v=120)
        fw_retry_count = _int("FIREWORKS_RETRY_COUNT", int(app_cfg.get("FIREWORKS_RETRY_COUNT") or 2), min_v=0, max_v=5)
        pipeline_deadline_s = _int("PIPELINE_DEADLINE_S", int(app_cfg.get("PIPELINE_DEADLINE_S") or 18), min_v=8, max_v=90)
        llm_summary_threshold = _int(
            "LLM_SUMMARY_CONFIDENCE_THRESHOLD",
            int(app_cfg.get("LLM_SUMMARY_CONFIDENCE_THRESHOLD") or 85),
            min_v=50,
            max_v=100,
        )

        if strict or node_env in ("production", "staging"):
            if not cache_url:
                raise ValueError("CACHE_URL is required when strict=True or NODE_ENV is production/staging")

        return EnvConfig(
            node_env=node_env,
            cache_ttl_days=ttl,
            source_pipeline_version=str(app_cfg.get("SOURCE_PIPELINE_VERSION") or "1"),
            scorer_version=str(app_cfg.get("SCORER_VERSION") or "1"),
            fetch_max_bytes=fetch_bytes,
            fetch_max_redirects=fetch_redirs,
            cache_url=cache_url,
            search_api_endpoint=search_api_endpoint,
            search_timeout_s=search_timeout_s,
            search_retry_count=search_retry_count,
            search_rate_limit_per_minute=search_rate_limit,
            fireworks_base_url=fw_base,
            fireworks_model=fw_model,
            fireworks_vision_model=fw_vision_model,
            fireworks_timeout_s=fw_timeout_s,
            fireworks_retry_count=fw_retry_count,
            log_level=str(app_cfg.get("LOG_LEVEL") or "info").lower(),
            pipeline_deadline_s=pipeline_deadline_s,
            llm_summary_confidence_threshold=llm_summary_threshold,
        )
