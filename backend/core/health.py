"""Health and readiness payloads for deployment probes (Sprint 4)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.core.env import EnvConfig
from backend.core.fetch_job_page import job_fetch_enabled
from backend.core.llm_fireworks import image_verify_enabled, llm_enabled
from backend.core.recommendations import any_search_configured, env_recommendations_default_on


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def require_shared_verification_cache(cfg: EnvConfig) -> bool:
    """Production/staging always need Redis; optional flag forces the same rule on Railway dev NODE_ENV."""

    return cfg.node_env in ("production", "staging") or _truthy_env("JOBSIGNAL_REQUIRE_SHARED_CACHE")


def build_health_payload() -> Dict[str, Any]:
    """Process liveness: minimal signal for load balancers (Railway default healthcheck)."""

    return {
        "status": "ok",
        "service": "jobsignal-api",
        "checks": {"process": "ok"},
        "readiness": {
            "path": "/ready",
            "note": "Use /ready for Redis connectivity, API keys, and optional live provider probes.",
        },
    }


def build_ready_payload(
    cfg: EnvConfig,
    *,
    cache_ping_ok: Optional[bool] = None,
    fireworks_reachable: Optional[bool] = None,
    serper_reachable: Optional[bool] = None,
    live_probe: bool = False,
) -> Dict[str, Any]:
    """Readiness with explicit pass/fail/skip checks and degraded mode."""

    has_llm_key = bool((os.environ.get("FIREWORKS_API_KEY") or os.environ.get("LLM_API_KEY")))
    rec_enabled = env_recommendations_default_on()
    has_serp_key = bool(
        (os.environ.get("SERPER_API_KEY") or os.environ.get("SERPAPI_API_KEY") or os.environ.get("SEARCH_API_KEY") or "").strip()
    )

    checks: Dict[str, str] = {
        "redis": "skip",
        "llm_key": "pass" if has_llm_key else "fail",
        "serp_key": "pass" if has_serp_key else "fail",
        "serp_key_for_recommendations": "skip",
    }

    need_shared = require_shared_verification_cache(cfg)
    if need_shared:
        if not cfg.cache_url:
            checks["redis"] = "fail"
        else:
            checks["redis"] = "pass" if cache_ping_ok else "fail"
    elif cfg.cache_url:
        checks["redis"] = "pass" if cache_ping_ok else "fail"

    if has_llm_key and fireworks_reachable is not None:
        checks["llm_key"] = "pass" if fireworks_reachable else "fail"

    if rec_enabled:
        checks["serp_key_for_recommendations"] = "pass" if has_serp_key else "fail"
        if has_serp_key and serper_reachable is not None:
            checks["serp_key_for_recommendations"] = "pass" if serper_reachable else "fail"

    hard_fail = checks["redis"] == "fail"
    degraded = (
        checks["llm_key"] == "fail"
        or checks["serp_key"] == "fail"
        or checks["serp_key_for_recommendations"] == "fail"
    )
    status = "unavailable" if hard_fail else ("degraded" if degraded else "ready")
    return {
        "status": status,
        "live_probe": live_probe,
        "checks": checks,
        "features": {
            "search_configured": any_search_configured(),
            "recommendations_default_enabled": rec_enabled,
            "job_fetch_enabled": job_fetch_enabled(),
            "image_verify_enabled": image_verify_enabled(),
            "llm_signals_enabled": llm_enabled(),
            "shared_cache_required": need_shared,
        },
        "http": 503 if status == "unavailable" else 200,
    }
