"""Public report envelope for API/UI (Sprint 3)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict, cast

from backend.core.decision_schema import CacheMeta, DecisionResponse, ResponseMeta
from backend.core.scoring import decision_to_jsonable


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


def build_public_report(
    decision: DecisionResponse,
    *,
    cache: Optional[CacheMeta] = None,
    meta: Optional[ResponseMeta] = None,
    ingestion: Optional[dict[str, Any]] = None,
) -> PublicVerifyReport:
    payload = decision_to_jsonable(decision)
    
    # Compute the new explicit fields
    signals = payload.get("signals", [])
    warnings = payload.get("warnings", [])
    
    what_matched = [s.get("label", "") for s in signals if s.get("strength") in ("high", "medium")]
    what_did_not_match = [s.get("label", "") for s in signals if s.get("strength") in ("none", "low")]
    red_flags = [w.get("message", "") for w in warnings if w.get("code") not in ("FIXTURES_MISS", "CONFIDENCE_LOW")]
    sources = [s.get("details", "") for s in signals if s.get("tier") == "T1"]
    
    rec_map = {
        "APPLY": "The evidence supports this role as legitimate. You can proceed with applying.",
        "VERIFY": "Evidence is mixed or incomplete. Please manually verify on the official company careers page.",
        "SKIP": "Strong indicators suggest this is a duplicate, repost, or unverified listing. Proceed with extreme caution."
    }
    
    merged: dict[str, Any] = {
        "report_schema_version": "2.0.0", 
        "verdict": payload["verdict"],
        "confidence": payload["confidence"],
        "what_was_checked": "Job description text, image contents, and provided URL against official company domains and open web search.",
        "what_matched": what_matched,
        "what_did_not_match": what_did_not_match,
        "red_flags": red_flags,
        "sources": sources,
        "recommendation": rec_map.get(payload["verdict"], "Manually verify."),
        **payload
    }
    
    if cache is not None:
        merged["cache"] = cache
    if meta is not None:
        merged["meta"] = meta
    if ingestion is not None:
        merged["ingestion"] = ingestion
    return cast(PublicVerifyReport, merged)
