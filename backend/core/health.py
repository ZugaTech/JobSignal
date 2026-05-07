"""Health and readiness payloads for deployment probes (Sprint 4)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.core.env import EnvConfig
from backend.core.fetch_job_page import job_fetch_enabled
from backend.core.llm_fireworks import image_verify_enabled, llm_enabled
from backend.core.recommendations import any_search_configured, env_recommendations_default_on


def build_health_payload() -> Dict[str, Any]:
    """Process liveness: always OK if importable."""

    return {"status": "ok", "service": "jobsignal-api", "checks": {"process": "ok"}}


def build_ready_payload(cfg: EnvConfig, *, cache_ping_ok: Optional[bool] = None) -> Dict[str, Any]:
    """Readiness with explicit pass/fail/skip checks and degraded mode."""

    has_llm_key = bool((os.environ.get("FIREWORKS_API_KEY") or os.environ.get("LLM_API_KEY")))
    rec_enabled = env_recommendations_default_on()
    has_serp_key = bool((os.environ.get("SERPAPI_API_KEY") or os.environ.get("SEARCH_API_KEY")))

    checks: Dict[str, str] = {
        "redis": "skip",
        "llm_key": "pass" if has_llm_key else "fail",
        "serp_key_for_recommendations": "skip",
    }
    if cfg.cache_url:
        checks["redis"] = "pass" if cache_ping_ok else "fail"
    if rec_enabled:
        checks["serp_key_for_recommendations"] = "pass" if has_serp_key else "fail"

    hard_fail = checks["redis"] == "fail"
    degraded = checks["llm_key"] == "fail" or checks["serp_key_for_recommendations"] == "fail"
    status = "unavailable" if hard_fail else ("degraded" if degraded else "ready")
    return {
        "status": status,
        "checks": checks,
        "features": {
            "search_configured": any_search_configured(),
            "recommendations_default_enabled": rec_enabled,
            "job_fetch_enabled": job_fetch_enabled(),
            "image_verify_enabled": image_verify_enabled(),
            "llm_signals_enabled": llm_enabled(),
        },
        "http": 503 if status == "unavailable" else 200,
    }
