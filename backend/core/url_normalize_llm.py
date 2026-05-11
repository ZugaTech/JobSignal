"""Optional LLM pass to refine messy job URLs before canonical normalization (env-gated)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.llm_fireworks import _get, llm_enabled
from backend.core.llm_safe import call_llm_safe, under_pytest
from backend.core.normalization import normalize_job_url

logger = logging.getLogger("jobsignal")


def llm_url_normalize_enabled() -> bool:
    v = (os.environ.get("ENABLE_LLM_URL_NORMALIZE", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _parse_normalized_url_json(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    u = data.get("normalized_url")
    if u is None:
        return None
    if not isinstance(u, str):
        return None
    u = u.strip()
    if not u:
        return None
    canon, _ = normalize_job_url(u)
    return canon


async def maybe_refine_job_url_with_llm(raw_url: str, *, request_id: str) -> Optional[str]:
    """Return a canonical https URL if the model proposes one; otherwise None."""

    if not llm_url_normalize_enabled():
        return None
    if not raw_url.strip():
        return None
    if under_pytest() and getattr(call_llm_safe, "__module__", "") == "backend.core.llm_safe":
        return None
    if not llm_enabled() or not (_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")):
        return None

    fallback = '{"normalized_url":null}'
    messages: list[Dict[str, Any]] = [
        {
            "role": "system",
            "content": "You normalize job posting URLs. Reply with JSON only. No markdown.",
        },
        {
            "role": "user",
            "content": (
                f"Input URL:\n{raw_url.strip()}\n\n"
                'Return exactly: {"normalized_url":"<https URL>"} or {"normalized_url":null} '
                "if unstable or unsafe to infer. Prefer stripping tracking params; never invent hosts."
            ),
        },
    ]
    try:
        raw = await call_llm_safe(
            messages=messages,
            fallback=fallback,
            request_id=f"{request_id}_url_norm",
            model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            temperature=0.0,
            max_tokens=220,
            timeout=8.0,
            prose_mode=False,
            max_chars=1200,
            min_prose_len=2,
            require_sentence_period=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("url_normalize_llm_failed request_id=%s err=%s", request_id, e)
        return None

    out = _parse_normalized_url_json(raw)
    if out and out != raw_url.strip():
        logger.info("url_normalize_llm_applied request_id=%s", request_id)
    return out
