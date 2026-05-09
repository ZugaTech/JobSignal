"""Lightweight reachability checks for /ready (optional keys must validate, not only exist)."""

from __future__ import annotations

import os
from typing import Optional


def _fireworks_base_url() -> str:
    return (os.environ.get("FIREWORKS_BASE_URL") or "https://api.fireworks.ai/inference/v1").rstrip("/")


def fireworks_api_reachable(*, timeout_s: float = 5.0) -> Optional[bool]:
    """Return True if Fireworks OpenAI-compatible ``/models`` responds with 200.

    Returns ``None`` when no API key is configured (caller should treat as skip).
    """

    api_key = (os.environ.get("FIREWORKS_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        import httpx

        url = f"{_fireworks_base_url()}/models"
        r = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout_s)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def serper_api_reachable(*, timeout_s: float = 6.0) -> Optional[bool]:
    """Return True if Serper search endpoint accepts the key (HTTP 200).

    Uses one minimal query.
    Returns ``None`` when no Serper-compatible key is set.
    """

    key = (
        (os.environ.get("SERPER_API_KEY") or os.environ.get("SEARCH_API_KEY") or os.environ.get("SERPAPI_API_KEY") or "")
        .strip()
    )
    if not key:
        return None
    try:
        import httpx

        r = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": "JobSignal readiness check", "num": 1},
            timeout=timeout_s,
        )
        if r.status_code == 200:
            return True
        if r.status_code == 429:
            return True  # reachable; rate limited
        return False
    except Exception:  # noqa: BLE001
        return False
