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


def _serpapi_probe(api_key: str, *, timeout_s: float) -> bool:
    try:
        import httpx

        r = httpx.get(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": "JobSignal readiness check", "num": 1, "api_key": api_key},
            timeout=timeout_s,
        )
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def serper_api_reachable(*, timeout_s: float = 6.0) -> Optional[bool]:
    """Return True if at least one configured search provider accepts the key (HTTP 200).

    Probes Serper when ``SERPER_API_KEY`` / ``SEARCH_API_KEY`` is set; otherwise SerpApi when
    ``SERPAPI_API_KEY`` is set. When Serper is configured but fails, SerpApi is tried if present.

    Returns ``None`` when no search key is set.
    """

    serper_key = (os.environ.get("SERPER_API_KEY") or os.environ.get("SEARCH_API_KEY") or "").strip()
    serpapi_key = (os.environ.get("SERPAPI_API_KEY") or "").strip()
    if not serper_key and not serpapi_key:
        return None
    try:
        import httpx

        if serper_key:
            r = httpx.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                json={"q": "JobSignal readiness check", "num": 1},
                timeout=timeout_s,
            )
            if r.status_code == 200:
                return True
            if r.status_code == 429:
                if serpapi_key:
                    return _serpapi_probe(serpapi_key, timeout_s=timeout_s)
                return True  # reachable; rate limited (legacy semantics)
            if serpapi_key:
                return _serpapi_probe(serpapi_key, timeout_s=timeout_s)
            return False

        return _serpapi_probe(serpapi_key, timeout_s=timeout_s)
    except Exception:  # noqa: BLE001
        if serpapi_key:
            return _serpapi_probe(serpapi_key, timeout_s=timeout_s)
        return False
