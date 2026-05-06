"""Fireworks LLM integration (OpenAI-compatible).

This module is intentionally narrow: it produces *signals* and *warnings* from the
provided job text. It must never become a source of truth on its own.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class LlmSignalResult:
    signals: List[Dict[str, Any]]
    warnings: List[Dict[str, str]]


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def llm_enabled() -> bool:
    return (_get("ENABLE_LLM_SIGNALS", "0") or "0") in ("1", "true", "TRUE", "yes", "YES")


def image_verify_enabled() -> bool:
    return (_get("ENABLE_IMAGE_VERIFY", "0") or "0") in ("1", "true", "TRUE", "yes", "YES")


def _client():
    # Import lazily so tests that don't need LLM don't require the dependency.
    from openai import OpenAI  # type: ignore

    api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    base_url = _get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    if not api_key:
        raise ValueError("Missing FIREWORKS_API_KEY (or fallback LLM_API_KEY)")
    return OpenAI(api_key=api_key, base_url=base_url)


def extract_job_fields_from_image_vision(
    *,
    mime_type: str,
    data_url: str,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]]]:
    """Call a vision model; return parsed JSON dict on success, else ``None`` + warnings.

    When disabled or misconfigured, returns ``(None, warnings)`` without raising.
    """

    warnings: List[Dict[str, str]] = []
    if not image_verify_enabled():
        warnings.append(
            {
                "code": "VISION_DISABLED",
                "message": "Image verification is disabled (set ENABLE_IMAGE_VERIFY=1 to enable).",
            }
        )
        return None, warnings

    api_key_present = bool(_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY"))
    if not api_key_present:
        warnings.append(
            {
                "code": "VISION_NO_KEY",
                "message": "Image verification requires FIREWORKS_API_KEY (or LLM_API_KEY).",
            }
        )
        return None, warnings

    _ = mime_type  # reserved for logging / provider-specific paths
    model = (
        _get("FIREWORKS_VISION_MODEL")
        or _get("FIREWORKS_MODEL")
        or "accounts/fireworks/models/kimi-k2p5"
    )
    timeout_s = int(_get("FIREWORKS_TIMEOUT_S", "45") or "45")

    prompt = (
        "You extract job posting details from a screenshot. Return JSON ONLY with this schema:\n"
        "{\n"
        '  "extraction_confidence": "high"|"medium"|"low",\n'
        '  "job_title": string|null,\n'
        '  "company_name": string|null,\n'
        '  "job_url_hint": string|null,\n'
        '  "extracted_job_text": string,\n'
        '  "notes": string\n'
        "}\n"
        "Rules:\n"
        "- extraction_confidence reflects how readable and complete the posting is.\n"
        "- If text is blurry or missing, use extraction_confidence \"low\" and short extracted_job_text.\n"
        "- Do not invent employers, titles, or URLs not visible.\n"
        "- job_url_hint only if a URL is clearly visible (http/https).\n"
        "- extracted_job_text should be plain text of visible posting content, or empty if unreadable.\n"
        "- notes: one short sentence about limitations.\n"
    )

    try:
        c = _client()
        resp = c.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful OCR assistant. Prefer missing fields over guessing.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            temperature=0.1,
            timeout=timeout_s,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        warnings.append(
            {
                "code": "VISION_ERROR",
                "message": f"Vision call failed ({type(e).__name__}).",
            }
        )
        return None, warnings

    # Some models wrap JSON in fences; strip lightly.
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```").strip()
        if content.endswith("```"):
            content = content[: -3].strip()

    try:
        data = json.loads(content)
    except Exception:  # noqa: BLE001
        warnings.append({"code": "VISION_MALFORMED", "message": "Vision model returned non-JSON output."})
        return None, warnings

    if not isinstance(data, dict):
        warnings.append({"code": "VISION_MALFORMED", "message": "Vision model JSON was not an object."})
        return None, warnings

    return data, warnings


def build_llm_signals(*, job_text: str) -> LlmSignalResult:
    """Produce additional signals from job description text.

    Safety/honesty rules:
    - If data is not explicitly present, return it as missing.
    - Do not invent facts about the employer or role.
    - Output must be JSON; callers treat malformed output as a warning and proceed.
    """

    if not llm_enabled():
        return LlmSignalResult(signals=[], warnings=[])

    if not (job_text or "").strip():
        return LlmSignalResult(signals=[], warnings=[])

    api_key_present = bool(_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY"))
    if not api_key_present:
        return LlmSignalResult(
            signals=[],
            warnings=[
                {
                    "code": "LLM_DISABLED",
                    "message": "ENABLE_LLM_SIGNALS is set but no LLM API key is configured; skipping LLM-derived signals.",
                }
            ],
        )

    model = _get("FIREWORKS_MODEL", "accounts/fireworks/models/mixtral-8x7b-instruct") or ""
    timeout_s = int(_get("FIREWORKS_TIMEOUT_S", "20") or "20")

    prompt = (
        "You analyze a job description and extract only what is explicitly stated.\n"
        "Return JSON ONLY with this schema:\n"
        "{\n"
        '  "specificity": "low"|"medium"|"high",\n'
        '  "red_flags": string[],\n'
        '  "missing_fields": string[],\n'
        '  "notes": string\n'
        "}\n"
        "Rules:\n"
        "- Do not guess employer facts.\n"
        "- If the text lacks salary/location/contract type/clear responsibilities, list as missing_fields.\n"
        "- red_flags should be short, observable patterns (e.g. 'vague_responsibilities', 'no_company_info').\n"
        "- notes should be one short sentence.\n\n"
        "JOB DESCRIPTION:\n"
        + job_text[:20_000]
    )

    try:
        c = _client()
        resp = c.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a cautious evaluator. Prefer 'missing' over guessing."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            timeout=timeout_s,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001 - surfaced as warning only
        return LlmSignalResult(
            signals=[],
            warnings=[{"code": "LLM_ERROR", "message": f"LLM call failed; continuing without LLM signals. ({type(e).__name__})"}],
        )

    try:
        data = json.loads(content)
    except Exception:  # noqa: BLE001 - surfaced as warning only
        return LlmSignalResult(
            signals=[],
            warnings=[{"code": "LLM_MALFORMED", "message": "LLM returned non-JSON output; continuing without LLM signals."}],
        )

    specificity = str(data.get("specificity") or "").lower()
    if specificity not in ("low", "medium", "high"):
        specificity = "low"

    red_flags = data.get("red_flags") if isinstance(data.get("red_flags"), list) else []
    missing_fields = data.get("missing_fields") if isinstance(data.get("missing_fields"), list) else []

    signals: List[Dict[str, Any]] = [
        {
            "id": "jd_specificity",
            "label": "jd_specificity",
            "tier": "t3",
            "strength": "high" if specificity == "high" else ("medium" if specificity == "medium" else "low"),
            "details": f"specificity={specificity}",
        }
    ]

    if red_flags:
        signals.append(
            {
                "id": "jd_red_flags",
                "label": "jd_red_flags",
                "tier": "t3",
                "strength": "medium" if len(red_flags) <= 2 else "high",
                "details": ", ".join(str(x)[:40] for x in red_flags[:6]),
            }
        )

    if missing_fields:
        signals.append(
            {
                "id": "jd_missing_fields",
                "label": "jd_missing_fields",
                "tier": "t3",
                "strength": "medium" if len(missing_fields) <= 2 else "high",
                "details": ", ".join(str(x)[:40] for x in missing_fields[:6]),
            }
        )

    return LlmSignalResult(signals=signals, warnings=[])

