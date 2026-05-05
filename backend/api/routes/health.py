from __future__ import annotations

from fastapi import APIRouter, Response, status

from backend.core.env import EnvConfig
from backend.core.health import build_health_payload, build_ready_payload

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return build_health_payload()


@router.get("/ready")
def ready() -> Response:
    try:
        cfg = EnvConfig.load(strict=False)
    except ValueError:
        # Misconfigured env => not ready
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content='{"status":"not_ready"}', media_type="application/json")

    payload = build_ready_payload(cfg, cache_ping_ok=None)
    code = int(payload.get("http", 200))
    return Response(status_code=code, content=__import__("json").dumps(payload), media_type="application/json")

