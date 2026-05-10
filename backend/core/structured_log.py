from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger("jobsignal")


def configure_logging(level: str = "info") -> None:
    """Attach a single stdout handler to ``jobsignal`` so hosted platforms (e.g. Railway) do not tag INFO JSON as stderr/error."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    log = logging.getLogger("jobsignal")
    log.handlers.clear()
    log.setLevel(lvl)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.propagate = False


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
