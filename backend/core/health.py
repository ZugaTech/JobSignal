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
    """Readiness: strict env implies cache URL present; optional ping results."""

    checks: Dict[str, Any] = {
        "config_loaded": "ok",
        "node_env": cfg.node_env,
        "cache_url_configured": bool(cfg.cache_url),
        "search_configured": any_search_configured(),
        "recommendations_default_enabled": env_recommendations_default_on(),
        "job_fetch_enabled": job_fetch_enabled(),
        "image_verify_enabled": image_verify_enabled(),
        "llm_signals_enabled": llm_enabled(),
        "fireworks_key_present": bool((os.environ.get("FIREWORKS_API_KEY") or os.environ.get("LLM_API_KEY"))),
    }
    if cache_ping_ok is not None:
        checks["cache_ping"] = "ok" if cache_ping_ok else "fail"

    ready = True
    if cfg.node_env in ("production", "staging") and not cfg.cache_url:
        ready = False
    if cache_ping_ok is False:
        ready = False

    status = "ready" if ready else "not_ready"
    http_code_hint = 200 if ready else 503
    return {"status": status, "checks": checks, "http": http_code_hint}
