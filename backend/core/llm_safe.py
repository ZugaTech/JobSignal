"""Safe Fireworks chat wrappers (import from ``llm_fireworks`` only lazily from callers to avoid cycles)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.llm_fireworks import _client, _get
from backend.core.prompt_guard import extract_chat_completion_message_text
from backend.core.user_copy import contains_internal_verdict_jargon

logger = logging.getLogger("jobsignal")

_LEAK_MARKERS = [
    "the user wants",
    "key constraints",
    "data provided",
    "wait, there's",
    "constraints:",
    "instructions:",
    "system prompt",
    "you are a",
    "as an ai",
    "here is the",
    "given the following",
    "based on the following evidence",
    "write a",
    "generate a",
    # Phrase-level threshold leaks
    "apply gate",
    "medium+ with",
    "high with support",
]


def _looks_like_prompt_leak(text: str) -> bool:
    tl = text.lower()
    if any(m in tl for m in _LEAK_MARKERS):
        return True
    if re.search(r"\b(t1|t2|t3)\b", tl):
        return True
    if re.search(r"\b(gate|gates)\b", tl):
        return True
    if re.search(r"\btier\b", tl):
        return True
    return contains_internal_verdict_jargon(text)


def call_llm_safe_chat_sync(
    *,
    messages: List[Dict[str, Any]],
    fallback: str,
    request_id: str,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 256,
    timeout: Optional[float] = None,
    prose_mode: bool = True,
    max_chars: int = 500,
    min_prose_len: int = 20,
    require_sentence_period: bool = True,
) -> str:
    """Fireworks chat completion with leak guards; never returns request prompts as output."""
    if not fallback:
        raise ValueError("fallback must be non-empty")
    if prose_mode and require_sentence_period and "." not in fallback:
        raise ValueError("prose fallback must include a period")

    mid = model or _get("FIREWORKS_MODEL") or DEFAULT_FIREWORKS_MODEL
    try:
        tout = float(timeout if timeout is not None else (_get("FIREWORKS_TIMEOUT_S") or "10"))
    except ValueError:
        tout = 10.0

    try:
        client = _client()
        resp = client.chat.completions.create(
            model=mid,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=tout,
        )
        raw = extract_chat_completion_message_text(resp)
        if raw is None:
            logger.warning("llm_call_failed request_id=%s error=empty_message_content", request_id)
            return fallback[:max_chars]
        text = raw.strip()
        if prose_mode:
            too_short = len(text) < min_prose_len
            no_period = require_sentence_period and "." not in text
            if too_short or no_period:
                logger.warning("llm_response_too_short request_id=%s", request_id)
                return fallback[:max_chars]
        else:
            if len(text) < 2:
                logger.warning("llm_response_too_short request_id=%s", request_id)
                return fallback[:max_chars]
        if _looks_like_prompt_leak(text):
            logger.warning("llm_prompt_leak_detected request_id=%s preview=%s", request_id, text[:100])
            return fallback[:max_chars]
        return text[:max_chars]
    except Exception as e:  # noqa: BLE001
        logger.warning("llm_call_failed request_id=%s error=%s", request_id, str(e))
        return fallback[:max_chars]


async def call_llm_safe(
    *,
    messages: List[Dict[str, Any]],
    fallback: str,
    request_id: str,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 256,
    timeout: Optional[float] = None,
    prose_mode: bool = True,
    max_chars: int = 500,
    min_prose_len: int = 20,
    require_sentence_period: bool = True,
) -> str:
    return await asyncio.to_thread(
        call_llm_safe_chat_sync,
        messages=messages,
        fallback=fallback,
        request_id=request_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        prose_mode=prose_mode,
        max_chars=max_chars,
        min_prose_len=min_prose_len,
        require_sentence_period=require_sentence_period,
    )


def under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))
