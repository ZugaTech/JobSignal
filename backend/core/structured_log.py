from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger("jobsignal")


def configure_logging(level: str = "info") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")


def log_stage(
    *,
    request_id: str,
    stage: str,
    duration_ms: float,
    verdict: Optional[str] = None,
    level: str = "info",
    extra: Optional[dict] = None,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "stage": stage,
        "duration_ms": round(duration_ms, 2),
    }
    if verdict:
        payload["verdict"] = verdict
    if extra:
        payload.update(extra)
    msg = json.dumps(payload, separators=(",", ":"))
    getattr(logger, level.lower(), logger.info)(msg)
