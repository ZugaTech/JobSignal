from __future__ import annotations

import json
import os

from fastapi import APIRouter, Response, status

from backend.core.env import EnvConfig
from backend.core.health import build_health_payload, build_ready_payload
from backend.core.cache_store import cache_ping
from backend.core.metrics import METRICS
from backend.core.provider_ping import fireworks_api_reachable, serper_api_reachable

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return build_health_payload()


@router.get("/ready")
def ready() -> Response:
    try:
        cfg = EnvConfig.load(strict=False)
    except ValueError:
        payload = {"status": "unavailable", "checks": {"config": "fail"}}
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=json.dumps(payload), media_type="application/json")

    ping_ok = cache_ping(cfg.cache_url) if cfg.cache_url else None
    fw_ok = None
    serp_ok = None
    live_probe = str(os.environ.get("PROBE_PROVIDERS_ON_READY") or "0").strip().lower() in ("1", "true", "yes", "on")
    if live_probe and not os.environ.get("PYTEST_CURRENT_TEST"):
        fw_ok = fireworks_api_reachable()
        serp_ok = serper_api_reachable()
    payload = build_ready_payload(
        cfg,
        cache_ping_ok=ping_ok,
        fireworks_reachable=fw_ok,
        serper_reachable=serp_ok,
        live_probe=live_probe,
    )
    code = int(payload.get("http", 200))
    return Response(status_code=code, content=json.dumps(payload), media_type="application/json")


@router.get("/metrics")
def metrics() -> dict:
    return METRICS.snapshot()

