"""Public report envelope for API/UI (Sprint 3)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict, cast

from backend.core.decision_schema import CacheMeta, DecisionResponse, ResponseMeta
from backend.core.scoring import decision_to_jsonable

# Signal IDs that are internal bookkeeping — never show them to users
_INTERNAL_SIGNAL_IDS = frozenset({
    "url_canonical", "input_text_only",
})

# Maps raw signal IDs to plain-English labels for user display
_SIGNAL_LABELS: dict[str, str] = {
    "fetch_ok": "Job page loaded and verified",
    "domain_align": "URL matches company domain",
    "board_corroboration": "Listing found on a known job board",
    "search_corroboration": "Listing confirmed via web search",
    "official_careers_page": "Found on the company's official careers page",
    "duplicate_repost_risk": "Duplicate or repost detected",
    "jd_domain_align": "Job description domain alignment",
    "jd_market_salary": "Salary is within normal market range",
    "jd_scam_indicators": "Scam-pattern check",
    "jd_red_flags": "Red flag content check",
    "jd_content_farm_score": "Content farm check",
    "jd_specificity": "Role-specific details present",
    "jd_employer_identifiability": "Employer clearly identified",
    "jd_recruiter_intent_score": "Recruiter intent looks genuine",
    "jd_ai_generated_score": "AI-generated content check",
}

# Warning codes that are purely internal and must never surface to users
_INTERNAL_WARNING_CODES = frozenset({
    "FIXTURES_MISS", "CONFIDENCE_LOW", "FETCH", "SOURCES",
    "TEXT_ONLY_NOT_CORROBORATED", "CONTRADICTION",
})

# Maps warning codes to plain-English user messages (only shown when genuinely useful)
_WARNING_LABELS: dict[str, str] = {
    "HONESTY_GUARD": "Confidence was too low to give a clear recommendation. Verify manually before applying.",
    "DUPLICATE_RISK": "This listing may be a repost or copy of another job. Check the original source.",
    "TEXT_PATTERN_MATCH": "The description contains patterns commonly seen in suspicious listings.",
}


class PublicVerifyReport(TypedDict, total=False):
    """Stable JSON shape for clients; extends decision JSON with versioning."""

    report_schema_version: str
    verdict: str
    confidence: str
    what_was_checked: str
    what_matched: list[str]
    what_did_not_match: list[str]
    red_flags: list[str]
    sources: list[str]
    recommendation: str
    reasons: list[dict[str, str]]
    warnings: list[dict[str, str]]
    signals: list[dict[str, Any]]
    cache: CacheMeta
    meta: ResponseMeta
    ingestion: dict[str, Any]
    recommendations: list[dict[str, Any]]


def _signal_label(s: dict[str, Any]) -> str:
    """Return the best human-readable label for a signal."""
    return _SIGNAL_LABELS.get(s.get("id", ""), s.get("label", "")) or ""


def _checked_description(signals: list[dict[str, Any]], has_url: bool, has_image: bool) -> str:
    parts = []
    if has_url:
        parts.append("the job URL")
    if has_image:
        parts.append("your screenshot")
    if any(s.get("id", "").startswith("jd_") for s in signals):
        parts.append("the job description text")
    if not parts:
        parts.append("the information you provided")
    return "We checked " + ", ".join(parts) + " against official company domains and live web sources."


def build_public_report(
    decision: DecisionResponse,
    *,
    cache: Optional[CacheMeta] = None,
    meta: Optional[ResponseMeta] = None,
    ingestion: Optional[dict[str, Any]] = None,
) -> PublicVerifyReport:
    payload = decision_to_jsonable(decision)

    signals: list[dict[str, Any]] = payload.get("signals", [])
    warnings: list[dict[str, Any]] = payload.get("warnings", [])
    has_url = any(s.get("id") == "url_canonical" for s in signals)
    has_image = ingestion is not None and ingestion.get("status") == "ok"

    # Filter out purely internal signals before exposing to UI
    user_signals = [s for s in signals if s.get("id") not in _INTERNAL_SIGNAL_IDS]

    what_matched = [
        _signal_label(s) for s in user_signals
        if s.get("strength") in ("high", "medium") and _signal_label(s)
    ]
    what_did_not_match = [
        _signal_label(s) for s in user_signals
        if s.get("strength") in ("none", "low") and _signal_label(s)
    ]

    # Sources: only T1 signals with meaningful details (URLs, domain names)
    sources = [
        s.get("details", "") for s in user_signals
        if s.get("tier") == "T1" and s.get("details", "").strip()
    ]

    # Red flags: only map known warning codes to plain English — never show raw messages
    red_flags = [
        _WARNING_LABELS[w.get("code", "")]
        for w in warnings
        if w.get("code") in _WARNING_LABELS
    ]

    rec_map = {
        "APPLY": "This listing looks legitimate. You can go ahead and apply.",
        "VERIFY": "We couldn't fully confirm this listing. Check the company's official careers page before applying.",
        "SKIP": "We found signals that suggest this listing may not be trustworthy. Proceed with caution.",
    }

    merged: dict[str, Any] = {
        "report_schema_version": "2.0.0",
        "verdict": payload["verdict"],
        "confidence": payload["confidence"],
        "what_was_checked": _checked_description(signals, has_url, has_image),
        "what_matched": what_matched,
        "what_did_not_match": what_did_not_match,
        "red_flags": red_flags,
        "sources": sources,
        "recommendation": rec_map.get(payload["verdict"], "Verify manually."),
        **payload,
    }

    if cache is not None:
        merged["cache"] = cache
    if meta is not None:
        merged["meta"] = meta
    if ingestion is not None:
        merged["ingestion"] = ingestion
    return cast(PublicVerifyReport, merged)
