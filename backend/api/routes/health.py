from __future__ import annotations

import json

from fastapi import APIRouter, Response, status

from backend.core.env import EnvConfig
from backend.core.health import build_health_payload, build_ready_payload
from backend.core.cache_store import cache_ping
from backend.core.metrics import METRICS

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
    payload = build_ready_payload(cfg, cache_ping_ok=ping_ok)
    code = int(payload.get("http", 200))
    return Response(status_code=code, content=json.dumps(payload), media_type="application/json")


@router.get("/metrics")
def metrics() -> dict:
    return METRICS.snapshot()

