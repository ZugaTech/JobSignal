"""Public report envelope for API/UI (Sprint 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, TypedDict, cast

from backend.core.decision_schema import CacheMeta, DecisionResponse, ResponseMeta
from backend.core.scoring import decision_to_jsonable

_INTERNAL_SIGNAL_IDS = frozenset({
    "url_canonical", "input_text_only",
})

_SIGNAL_LABELS: dict[str, str] = {
    "fetch_ok": "Job page loaded and verified",
    "domain_align": "URL matches company domain",
    "board_corroboration": "Listing found on a known job board",
    "search_corroboration": "Listing confirmed via web search",
    "official_careers_page": "Found on the company's official careers page",
    "careers_page_match": "Career page corroboration",
    "cross_platform_freshness": "Cross-platform freshness",
    "staleness_flag": "Posting staleness check",
    "company_reputation_signal": "Company reputation check",
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
    "salary_range_plausibility": "Salary range plausibility",
    "role_title_consistency": "Role-title consistency",
    "contact_legitimacy": "Contact legitimacy",
}

_WARNING_LABELS: dict[str, str] = {
    "HONESTY_GUARD": "Confidence was too low to give a clear recommendation. Verify manually before applying.",
    "DUPLICATE_RISK": "This listing may be a repost or copy of another job. Check the original source.",
    "TEXT_PATTERN_MATCH": "The description contains patterns commonly seen in suspicious listings.",
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
    cache: CacheMeta
    meta: ResponseMeta
    ingestion: dict[str, Any]
    recommendations: list[dict[str, Any]]
    confidence_score: int
    trust_signals: list[dict[str, str]]
    evidence_sources: list[dict[str, str]]
    llm_summary: str
    similar_jobs: list[dict[str, Any]]
    disclaimer: str
    data_freshness: str
    company_legitimacy_score: int
    company_signals: list[dict[str, Any]]
    posting_authenticity_score: int
    posting_signals: list[dict[str, Any]]
    freshness_score: int
    staleness_flag: bool
    first_seen_estimate: Optional[str]
    verified_signal_count: int
    total_signal_count: int
    coverage_ratio: float


def _signal_label(s: dict[str, Any]) -> str:
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
    evidence_sources: Optional[list[dict[str, str]]] = None,
    data_freshness: Optional[str] = None,
) -> PublicVerifyReport:
    payload = decision_to_jsonable(decision)

    signals: list[dict[str, Any]] = payload.get("signals", [])
    warnings: list[dict[str, Any]] = payload.get("warnings", [])
    has_url = any(s.get("id") == "url_canonical" for s in signals)
    has_image = ingestion is not None and ingestion.get("status") == "ok"
    user_signals = [s for s in signals if s.get("id") not in _INTERNAL_SIGNAL_IDS]

    what_matched = [_signal_label(s) for s in user_signals if s.get("strength") in ("high", "medium") and _signal_label(s)]
    what_did_not_match = [_signal_label(s) for s in user_signals if s.get("strength") in ("none", "low") and _signal_label(s)]
    sources = [s.get("details", "") for s in user_signals if s.get("tier") == "T1" and s.get("details", "").strip()]
    red_flags = [_WARNING_LABELS[w.get("code", "")] for w in warnings if w.get("code") in _WARNING_LABELS]

    rec_map = {
        "APPLY": "This listing looks legitimate. You can go ahead and apply.",
        "VERIFY": "We couldn't fully confirm this listing. Check the company's official careers page before applying.",
        "SKIP": "We found signals that suggest this listing may not be trustworthy. Proceed with caution.",
    }
    confidence_score_map = {"high": 85, "medium": 60, "low": 35}

    trust_signals = [
        {
            "name": str(s.get("id", "")),
            "status": "unverified" if str(s.get("details", "")).strip().lower() == "unverified" else (
                "supported" if str(s.get("strength", "")) in ("high", "medium") else "weak"
            ),
            "detail": str(s.get("details", ""))[:240],
        }
        for s in user_signals
    ]

    merged: dict[str, Any] = {
        "report_schema_version": "2.0.0",
        "verdict": payload["verdict"],
        "confidence": payload["confidence"],
        "what_was_checked": _checked_description(signals, has_url, has_image),
        "what_matched": what_matched,
        "what_did_not_match": what_did_not_match,
        "red_flags": red_flags,
        "sources": sources,
        "confidence_score": confidence_score_map.get(str(payload["confidence"]).lower(), 35),
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
        "llm_summary": (
            "Automated analysis found limited corroboration. Verify against the official careers page before applying."
            if payload["verdict"] != "APPLY"
            else "Automated checks found supportive evidence across available sources."
        ),
        "similar_jobs": [],
        "disclaimer": str(payload.get("disclaimer") or "This assessment is advisory and may be incomplete. Always verify directly with the employer."),
        "data_freshness": data_freshness or datetime.now(timezone.utc).isoformat(),
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
