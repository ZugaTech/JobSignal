"""LLM-assisted job URL recovery — **fallback only** after deterministic validation/normalization fails."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Optional

from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.llm_fireworks import _get, llm_enabled
from backend.core.llm_safe import call_llm_safe, under_pytest
from backend.core.normalization import normalize_job_url

logger = logging.getLogger("jobsignal")


def llm_url_normalize_enabled() -> bool:
    v = (os.environ.get("ENABLE_LLM_URL_NORMALIZE", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class UrlLlmRecoveryResult:
    """Structured outcome from the fallback model (never trusted without ``normalize_job_url``)."""

    outcome: Literal["recovered", "not_job_url", "uncertain", "disabled", "error"]
    canonical_url: Optional[str]
    user_message: str


def _parse_recovery_json(text: str) -> Optional[dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _finalize_canonical(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url or not isinstance(raw_url, str):
        return None
    u = raw_url.strip()
    if not u:
        return None
    canon, _ = normalize_job_url(u)
    return canon


async def recover_job_url_with_llm_fallback(raw_input: str, *, request_id: str) -> UrlLlmRecoveryResult:
    """When normal channels cannot produce a canonical job URL, ask the model once for a structured recovery.

    The pipeline **must** still pass any ``normalized_url`` through ``normalize_job_url`` before use.
    """

    raw = (raw_input or "").strip()
    if not raw:
        return UrlLlmRecoveryResult(outcome="uncertain", canonical_url=None, user_message="No URL was provided.")

    if not llm_url_normalize_enabled():
        return UrlLlmRecoveryResult(
            outcome="disabled",
            canonical_url=None,
            user_message="URL recovery assistant is disabled.",
        )

    if under_pytest() and getattr(call_llm_safe, "__module__", "") == "backend.core.llm_safe":
        return UrlLlmRecoveryResult(outcome="disabled", canonical_url=None, user_message="")

    if not llm_enabled() or not (_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")):
        return UrlLlmRecoveryResult(
            outcome="disabled",
            canonical_url=None,
            user_message="URL recovery requires LLM credentials.",
        )

    fallback = '{"outcome":"uncertain","normalized_url":null,"user_message":"Could not interpret the URL."}'
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You help job seekers fix broken or messy job posting URLs. "
                "Reply with a single JSON object only — no markdown, no prose outside JSON. "
                "Never invent a company or job; only fix encoding, scheme, or obvious copy-paste wrappers. "
                "If the input is not a job posting web address, say so honestly."
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyze this user input (may be a URL fragment, wrong scheme, or pasted text with a link).\n"
                f"INPUT:\n{raw[:1800]}\n\n"
                "Return exactly this JSON shape:\n"
                "{\n"
                '  "outcome": "valid_job_url" | "not_job_url" | "uncertain",\n'
                '  "normalized_url": "<https URL to a job posting page>" | null,\n'
                '  "user_message": "<one short sentence for the user>"\n'
                "}\n"
                "Rules: outcome=valid_job_url only if normalized_url is a plausible http(s) job page you are "
                "confident about. Otherwise outcome=uncertain or not_job_url. normalized_url must be https when set."
            ),
        },
    ]
    try:
        raw_out = await call_llm_safe(
            messages=messages,
            fallback=fallback,
            request_id=f"{request_id}_url_recover",
            model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            temperature=0.0,
            max_tokens=320,
            timeout=12.0,
            prose_mode=False,
            max_chars=2000,
            min_prose_len=2,
            require_sentence_period=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("url_recover_llm_failed request_id=%s err=%s", request_id, e)
        return UrlLlmRecoveryResult(
            outcome="error",
            canonical_url=None,
            user_message="We could not analyze that URL right now. Try a direct https link to the job posting.",
        )

    data = _parse_recovery_json(raw_out) or _parse_recovery_json(fallback)
    if not data:
        return UrlLlmRecoveryResult(outcome="uncertain", canonical_url=None, user_message="Could not interpret the URL.")

    oc = str(data.get("outcome") or "uncertain").strip().lower()
    msg = str(data.get("user_message") or "").strip() or "We could not use that input as a job posting URL."
    nu = data.get("normalized_url")

    if oc == "not_job_url":
        return UrlLlmRecoveryResult(outcome="not_job_url", canonical_url=None, user_message=msg)

    if oc != "valid_job_url":
        return UrlLlmRecoveryResult(outcome="uncertain", canonical_url=None, user_message=msg)

    canon = _finalize_canonical(nu if isinstance(nu, str) else None)
    if canon:
        logger.info("url_recover_llm_recovered request_id=%s", request_id)
        return UrlLlmRecoveryResult(outcome="recovered", canonical_url=canon, user_message=msg)

    return UrlLlmRecoveryResult(
        outcome="uncertain",
        canonical_url=None,
        user_message=msg or "The model suggested a URL we could not validate. Paste a direct https job link.",
    )
