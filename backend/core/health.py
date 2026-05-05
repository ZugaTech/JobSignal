"""Health and readiness payloads for deployment probes (Sprint 4)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.env import EnvConfig


def build_health_payload() -> Dict[str, Any]:
    """Process liveness: always OK if importable."""

    return {"status": "ok", "service": "jobsignal-api", "checks": {"process": "ok"}}


def build_ready_payload(cfg: EnvConfig, *, cache_ping_ok: Optional[bool] = None) -> Dict[str, Any]:
    """Readiness: strict env implies cache URL present; optional ping results."""

    checks: Dict[str, Any] = {
        "config_loaded": "ok",
        "node_env": cfg.node_env,
        "cache_url_configured": bool(cfg.cache_url),
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
