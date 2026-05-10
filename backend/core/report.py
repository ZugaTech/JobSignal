"""Public report envelope for API/UI (Sprint 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, TypedDict, cast

from backend.core.decision_schema import CacheMeta, DecisionResponse, ResponseMeta
from backend.core.scoring import decision_to_jsonable
from backend.core.user_copy import human_reason_warning_line, plain_reason_for_code

_INTERNAL_SIGNAL_IDS = frozenset({
    "url_canonical", "input_text_only",
})

_SIGNAL_LABELS: dict[str, str] = {
    "careers_domain_match": "Official Company Domain",
    "careers_page_match": "Official Careers Listing",
    "company_linkedin_presence": "LinkedIn Profile Verification",
    "company_registry_presence": "Public Business Registry",
    "cross_platform_freshness": "Multi-Platform Verification",
    "first_seen_estimate": "First Detected Date",
    "posting_duplication_signal": "Duplicate Posting Check",
    "staleness_flag": "Listing Age",
    "company_reputation_signal": "Employer Reputation",
    "jd_specificity": "Job description quality",
    "jd_red_flags": "Job description risk patterns",
    "jd_missing_fields": "Missing job details",
    "live_page_fetch": "Page Reachability",
    "domain_match_after_redirect": "Redirect Domain Check",
    "fetch_ok": "Source Page Access",
    "domain_align": "Domain Alignment",
}

_STATUS_MAP: dict[str, str] = {
    "none": "Not Checked",
    "low": "Weak Signal",
    "medium": "Partial Match",
    "high": "Strong Match",
    "pass": "Verified",
    "fail": "Flagged",
    "unknown": "Inconclusive",
}

class PublicVerifyReport(TypedDict, total=False):
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
    review_summary: Optional[dict[str, Any]]
    cache: CacheMeta
    meta: ResponseMeta
    ingestion: dict[str, Any]
    recommendations: list[dict[str, Any]]
    confidence_score: int
    trust_signals: list[dict[str, str]]
    evidence_sources: list[dict[str, str]]
    llm_summary: str
    coverage_ratio: float
    similar_jobs: list[dict[str, Any]]


def _signal_label(s: dict[str, Any]) -> str:
    name = s.get("id", "")
    if name in _SIGNAL_LABELS:
        return _SIGNAL_LABELS[name]
    return name.replace("_", " ").title().strip()


def _signal_status(strength: str) -> str:
    st = str(strength or "").lower()
    return _STATUS_MAP.get(st, st.title())


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
    evidence_sources: Optional[list[dict[str, str]]] = None,
    data_freshness: Optional[str] = None,
    review_summary: Optional[dict[str, Any]] = None,
) -> PublicVerifyReport:
    payload = decision_to_jsonable(decision)

    signals: list[dict[str, Any]] = payload.get("signals", [])
    warnings: list[dict[str, Any]] = payload.get("warnings", [])
    has_url = any(s.get("id") == "url_canonical" for s in signals)
    has_image = ingestion is not None and ingestion.get("status") == "ok"
    user_signals = [s for s in signals if s.get("id") not in _INTERNAL_SIGNAL_IDS]

    what_matched = [_signal_label(s) for s in user_signals if s.get("strength") in ("high", "medium") and _signal_label(s)]
    what_did_not_match = [_signal_label(s) for s in user_signals if s.get("strength") in ("none", "low") and _signal_label(s)]
    sources: list[str] = []
    for s in user_signals:
        if str(s.get("strength", "")).lower() not in ("high", "medium"):
            continue
        det = str(s.get("details", "") or "").strip()
        if det:
            sources.append(det[:400])
    sources = sources[:12]
    red_flags = [plain_reason_for_code(str(w.get("code", ""))) for w in warnings if str(w.get("code", "")).strip()]

    rec_map = {
        "APPLY": "This listing looks legitimate. You can go ahead and apply.",
        "VERIFY": "We couldn't fully confirm this listing. Check the company's official careers page before applying.",
        "SKIP": "We found signals that suggest this listing may not be trustworthy. Proceed with caution.",
    }
    try:
        numeric_confidence = int(payload["confidence_score"]) if payload.get("confidence_score") is not None else 0
    except (TypeError, ValueError):
        numeric_confidence = 0
    numeric_confidence = max(0, min(100, numeric_confidence))

    trust_signals = [
        {
            "name": _signal_label(s),
            "status": _signal_status(str(s.get("strength", ""))),
            "detail": str(s.get("details", ""))[:240],
        }
        for s in user_signals
    ]

    human_reasons = [
        {
            "code": str(r.get("code", "") or ""),
            "message": human_reason_warning_line(code=str(r.get("code", "") or ""), message=str(r.get("message", "") or "")),
        }
        for r in payload.get("reasons", [])
    ]
    human_warnings = [
        {
            "code": str(w.get("code", "") or ""),
            "message": human_reason_warning_line(code=str(w.get("code", "") or ""), message=str(w.get("message", "") or "")),
        }
        for w in payload.get("warnings", [])
    ]

    overlay: dict[str, Any] = {
        "report_schema_version": "2.0.0",
        "verdict": payload["verdict"],
        "confidence": payload["confidence"],
        "what_was_checked": _checked_description(signals, has_url, has_image),
        "what_matched": what_matched,
        "what_did_not_match": what_did_not_match,
        "red_flags": red_flags,
        "sources": sources,
        "confidence_score": numeric_confidence,
        "company_legitimacy_score": int(payload.get("company_legitimacy_score", 0)),
        "company_signals": list(payload.get("company_signals", [])),
        "posting_authenticity_score": int(payload.get("posting_authenticity_score", 0)),
        "posting_signals": list(payload.get("posting_signals", [])),
        "freshness_score": int(payload.get("freshness_score", 0)),
        "staleness_flag": bool(payload.get("staleness_flag", False)),
        "first_seen_estimate": payload.get("first_seen_estimate"),
        "verified_signal_count": int(payload.get("verified_signal_count", 0)),
        "total_signal_count": int(payload.get("total_signal_count", 0)),
        "coverage_ratio": float(payload.get("coverage_ratio", 0.0)),
        "trust_signals": trust_signals,
        "evidence_sources": evidence_sources or [],
        "llm_summary": str(payload.get("llm_summary") or ""),
        "review_summary": review_summary,
        "reasons": human_reasons,
        "warnings": human_warnings,
        "similar_jobs": payload.get("similar_jobs") or [],
        "disclaimer": str(payload.get("disclaimer") or "This assessment is advisory and may be incomplete. Always verify directly with the employer."),
        "data_freshness": data_freshness or datetime.now(timezone.utc).isoformat(),
        "recommendation": rec_map.get(payload["verdict"], "Verify manually."),
    }
    merged: dict[str, Any] = {**payload, **overlay}

    if cache is not None:
        merged["cache"] = cache
    if meta is not None:
        merged["meta"] = meta
    if ingestion is not None:
        merged["ingestion"] = ingestion
    return cast(PublicVerifyReport, merged)
