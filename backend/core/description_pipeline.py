"""Description-input intelligence pipeline (Sprint — Smart Input Intelligence).

Handles two cases:
  A) has_company_info=True  → STEP 2A: full verification (delegates to orchestrator)
  B) has_company_info=False → STEP 2B: content-analysis-only, confidence capped at 55

Also exposes:
  - extract_fields_from_description()  — LLM extraction
  - GENERIC_COMPANY_BLOCKLIST / sanitize_company_name()  — hallucination guard
  - build_content_analysis_signals()  — description-quality signals (no URL, no company)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("jobsignal")

# ---------------------------------------------------------------------------
# Hallucination guard
# ---------------------------------------------------------------------------

GENERIC_COMPANY_BLOCKLIST: frozenset[str] = frozenset(
    {
        "company",
        "employer",
        "client",
        "confidential",
        "undisclosed",
        "our client",
        "leading company",
        "top company",
        "global company",
        "a company",
        "the company",
        "anonymous",
        "n/a",
        "not specified",
        "not disclosed",
    }
)


def sanitize_company_name(name: Optional[str]) -> Optional[str]:
    """Return None if name matches a generic/placeholder company name."""
    if not name:
        return None
    cleaned = name.strip()
    if not cleaned:
        return None
    if cleaned.lower() in GENERIC_COMPANY_BLOCKLIST:
        return None
    # also catch partial matches: "a leading company" etc.
    lower = cleaned.lower()
    for phrase in GENERIC_COMPANY_BLOCKLIST:
        if len(phrase) >= 5 and phrase in lower:
            return None
    return cleaned


# ---------------------------------------------------------------------------
# Structured extraction result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DescriptionExtractionResult:
    company_name: Optional[str]
    job_title: Optional[str]
    location: Optional[str]
    salary_mentioned: bool
    salary_range: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    application_url: Optional[str]
    has_company_info: bool  # False if company_name is None/generic


# ---------------------------------------------------------------------------
# LLM extraction from description text
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = (
    "You are a structured data extractor. Extract only what is explicitly stated in the text. "
    "Do not infer, assume, or invent any values. Return only valid JSON."
)

_EXTRACTION_PROMPT = (
    "Extract structured information from the following job posting text. "
    "Return only a JSON object with these fields: "
    "company_name, job_title, location, salary_mentioned, salary_range, "
    "contact_email, contact_phone, application_url, has_company_info. "
    "If a field cannot be determined from the text, set it to null. "
    "salary_mentioned is a boolean. "
    "Do not invent or infer values that are not present. "
    "has_company_info is true only if a specific company name is clearly stated.\n\n"
    "JOB POSTING TEXT:\n{text}"
)

_FALLBACK_EXTRACTION = (
    '{"company_name":null,"job_title":null,"location":null,"salary_mentioned":false,'
    '"salary_range":null,"contact_email":null,"contact_phone":null,'
    '"application_url":null,"has_company_info":false}'
)


def _valid_url(s: Optional[str]) -> Optional[str]:
    """Return s if it looks like an http/https URL, else None."""
    if not s:
        return None
    try:
        p = urlparse(s.strip())
        if p.scheme in ("http", "https") and p.netloc:
            return s.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def extract_fields_from_description(
    text: str,
    *,
    request_id: str = "desc_extract",
) -> DescriptionExtractionResult:
    """
    Call the LLM to extract structured fields from a description.
    Falls back to an empty result on any error — never raises.
    """
    from backend.core.llm_fireworks import _get, llm_enabled
    from backend.core.llm_safe import call_llm_safe_chat_sync

    _empty = DescriptionExtractionResult(
        company_name=None,
        job_title=None,
        location=None,
        salary_mentioned=False,
        salary_range=None,
        contact_email=None,
        contact_phone=None,
        application_url=None,
        has_company_info=False,
    )

    if not llm_enabled():
        return _empty

    api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    if not api_key:
        return _empty

    model = _get("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2p6") or ""
    timeout_s = int(_get("FIREWORKS_TIMEOUT_S", "20") or "20")

    prompt = _EXTRACTION_PROMPT.format(text=text[:20_000])

    try:
        raw = call_llm_safe_chat_sync(
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            fallback=_FALLBACK_EXTRACTION,
            request_id=request_id,
            model=model,
            temperature=0.1,
            max_tokens=512,
            timeout=float(timeout_s),
            prose_mode=False,
            max_chars=4096,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("description_extract_failed request_id=%s error=%s", request_id, exc)
        return _empty

    # Strip JSON fences if present
    content = raw.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```").strip()
        if content.endswith("```"):
            content = content[:-3].strip()

    # Grab the first JSON object
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1:
        content = content[start : end + 1]

    try:
        data: Dict[str, Any] = json.loads(content)
    except Exception:  # noqa: BLE001
        return _empty

    if not isinstance(data, dict):
        return _empty

    raw_company = data.get("company_name") or None
    company = sanitize_company_name(raw_company if isinstance(raw_company, str) else None)
    has_company = bool(company) and bool(data.get("has_company_info"))

    application_url = _valid_url(str(data.get("application_url") or ""))

    return DescriptionExtractionResult(
        company_name=company,
        job_title=(str(data.get("job_title") or "").strip() or None),
        location=(str(data.get("location") or "").strip() or None),
        salary_mentioned=bool(data.get("salary_mentioned")),
        salary_range=(str(data.get("salary_range") or "").strip() or None),
        contact_email=(str(data.get("contact_email") or "").strip() or None),
        contact_phone=(str(data.get("contact_phone") or "").strip() or None),
        application_url=application_url,
        has_company_info=has_company,
    )


# ---------------------------------------------------------------------------
# Content-analysis signals (STEP 2B — no company info)
# ---------------------------------------------------------------------------

# Free email domains — corporate roles on these are a red flag
_FREE_DOMAINS = frozenset(
    {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "aol.com", "icloud.com", "protonmail.com", "live.com",
        "mail.com", "zoho.com", "yandex.com",
    }
)

_PRESSURE_PATTERNS = re.compile(
    r"\b(apply\s+immediately|limited\s+slots?|pay\s+to\s+(train|start)|"
    r"act\s+fast|urgent(ly)?|immediate\s+(start|hire|opening)|"
    r"(slots?|spots?)\s+(are\s+)?(filling|going)\s+fast|"
    r"no\s+experience\s+required|work\s+from\s+home.*earn|"
    r"earn\s+(up\s+to\s+)?\$?\d+\s+(per\s+)?(day|hour|week))\b",
    re.I,
)

_GENERIC_TEMPLATE_PATTERNS = re.compile(
    r"\b(job\s+description\s*:[\s]*n/a|responsibilities\s*:[\s]*n/a|"
    r"see\s+attached|please\s+apply\s+to\s+learn\s+more|"
    r"details\s+to\s+be\s+provided|must\s+be\s+a\s+(team\s+player|go-getter))\b",
    re.I,
)

_VAGUE_INDICATORS = re.compile(
    r"\b(various\s+duties|general\s+tasks|perform\s+other\s+duties|"
    r"as\s+assigned|and\s+more|etc\.?\s*$|"
    r"will\s+(be\s+)?train(ed)?|no\s+(prior\s+)?experience\s+needed)\b",
    re.I,
)


def _word_count(text: str) -> int:
    return len(text.split())


def _contact_legitimacy_signal(email: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return a signal dict if a free-domain email is found in a corporate context."""
    if not email:
        return None
    domain = email.lower().split("@")[-1] if "@" in email else ""
    if domain in _FREE_DOMAINS:
        return {
            "id": "contact_legitimacy",
            "label": "Contact Email",
            "tier": "T2",
            "strength": "low",
            "details": f"Contact email uses a free domain ({domain}). Legitimate companies use corporate email.",
        }
    return {
        "id": "contact_legitimacy",
        "label": "Contact Email",
        "tier": "T2",
        "strength": "medium",
        "details": f"Contact email domain: {domain}",
    }


def build_content_analysis_signals(
    text: str,
    extraction: DescriptionExtractionResult,
) -> List[Dict[str, Any]]:
    """
    Build description-quality signals for the no-company pipeline (STEP 2B).
    Does not touch company reputation. Never hallucinate.
    """
    signals: List[Dict[str, Any]] = []

    # 1. Pressure language
    pressure_hits = _PRESSURE_PATTERNS.findall(text)
    if pressure_hits:
        signals.append(
            {
                "id": "pressure_language",
                "label": "Urgency / Pressure Language",
                "tier": "T2",
                "strength": "low" if len(pressure_hits) >= 2 else "medium",
                "details": f"Found urgency language patterns: {', '.join(str(h[0] if isinstance(h, tuple) else h)[:30] for h in pressure_hits[:3])}",
            }
        )
    else:
        signals.append(
            {
                "id": "pressure_language",
                "label": "Urgency / Pressure Language",
                "tier": "T2",
                "strength": "high",
                "details": "No urgent/pressure language detected.",
            }
        )

    # 2. Vagueness score
    vague_hits = _VAGUE_INDICATORS.findall(text)
    wc = _word_count(text)
    if wc < 80:
        # Guard handled before we get here, but defensive
        vague_strength = "low"
    elif len(vague_hits) >= 3 or (wc < 150 and len(vague_hits) >= 1):
        vague_strength = "low"
    elif len(vague_hits) >= 1:
        vague_strength = "medium"
    else:
        vague_strength = "high"

    signals.append(
        {
            "id": "vagueness_score",
            "label": "Description Specificity",
            "tier": "T2",
            "strength": vague_strength,
            "details": (
                f"Vague language patterns found ({len(vague_hits)})." if vague_hits
                else "Description appears specific about responsibilities."
            ),
        }
    )

    # 3. Salary plausibility (only if mentioned)
    if extraction.salary_mentioned and extraction.salary_range:
        # Basic sanity — extremely high or extremely low
        salary_str = extraction.salary_range.lower()
        # Simple heuristic: extract any dollar amount
        amounts = re.findall(r"\$?([\d,]+)", salary_str)
        parsed_amounts = []
        for a in amounts:
            try:
                parsed_amounts.append(int(a.replace(",", "")))
            except ValueError:
                pass
        if parsed_amounts:
            max_amt = max(parsed_amounts)
            # Extremely high (>500k) or extremely low (<100/year or < 1 as implied hourly)
            if max_amt > 500_000 or (max_amt < 1_000 and "year" in salary_str):
                strength = "low"
                detail = f"Stated salary ({extraction.salary_range}) appears unrealistic."
            else:
                strength = "medium"
                detail = f"Salary stated: {extraction.salary_range}. Plausibility check passed."
        else:
            strength = "medium"
            detail = f"Salary mentioned: {extraction.salary_range}"

        signals.append(
            {
                "id": "salary_plausibility",
                "label": "Salary Plausibility",
                "tier": "T2",
                "strength": strength,
                "details": detail,
            }
        )

    # 4. Contact legitimacy
    contact_sig = _contact_legitimacy_signal(extraction.contact_email)
    if contact_sig:
        signals.append(contact_sig)

    # 5. Generic posting detection
    generic_hits = _GENERIC_TEMPLATE_PATTERNS.findall(text)
    if generic_hits:
        signals.append(
            {
                "id": "generic_posting_detection",
                "label": "Generic Template Detection",
                "tier": "T2",
                "strength": "low",
                "details": "Posting appears to use generic template language, suggesting it may be reused across multiple platforms.",
            }
        )

    # 6. Engagement bait detection (simple heuristic: many benefits + no requirements)
    has_benefits_section = bool(re.search(r"\b(benefits|perks|unlimited\s+pto|work\s+from\s+home)\b", text, re.I))
    has_requirements = bool(re.search(r"\b(required|must\s+have|minimum\s+\d+\s+year|bachelor'?s|degree|experience\s+in)\b", text, re.I))
    if has_benefits_section and not has_requirements:
        signals.append(
            {
                "id": "engagement_bait_detection",
                "label": "Engagement Bait Indicator",
                "tier": "T2",
                "strength": "low",
                "details": "Posting emphasises benefits/perks but omits clear requirements — possible engagement bait.",
            }
        )

    return signals


# ---------------------------------------------------------------------------
# Confidence cap for no-company pipeline
# ---------------------------------------------------------------------------

CONTENT_ANALYSIS_MAX_CONFIDENCE = 55


def cap_confidence_for_content_only(report: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate report in-place to cap confidence at 55 and downgrade verdict if APPLY."""
    score = report.get("confidence_score")
    if isinstance(score, (int, float)) and score > CONTENT_ANALYSIS_MAX_CONFIDENCE:
        report["confidence_score"] = CONTENT_ANALYSIS_MAX_CONFIDENCE
    # Never return APPLY without company
    if report.get("verdict") == "APPLY":
        report["verdict"] = "VERIFY"
    return report


# ---------------------------------------------------------------------------
# Metadata helpers (attached to report for frontend)
# ---------------------------------------------------------------------------


def build_input_meta_no_company(extraction: DescriptionExtractionResult) -> Dict[str, Any]:
    return {
        "input_method": "description",
        "company_identified": False,
        "extracted_job_title": extraction.job_title,
        "extracted_location": extraction.location,
        "extracted_salary": extraction.salary_range,
        "no_company_reason": (
            "No specific company name was found in the description. "
            "Without knowing the employer, we cannot verify the posting against public records."
        ),
    }


def build_input_meta_with_company(
    extraction: DescriptionExtractionResult,
    *,
    input_method: str = "description",
) -> Dict[str, Any]:
    return {
        "input_method": input_method,
        "company_identified": True,
        "extracted_company_name": extraction.company_name,
        "extracted_job_title": extraction.job_title,
        "extracted_location": extraction.location,
        "extracted_salary": extraction.salary_range,
    }
