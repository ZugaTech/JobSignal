"""Honesty contract: validate and repair /v1/verify payloads before serialization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.prompt_guard import is_prompt_leak
from backend.core.user_copy import (
    build_fallback_llm_summary,
    contains_internal_verdict_jargon,
    human_reason_warning_line,
    scrub_internal_jargon,
)

logger = __import__("logging").getLogger("jobsignal")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repair_request_id(rid: Any) -> str:
    if rid is None:
        return str(uuid.uuid4())
    try:
        uuid.UUID(str(rid))
        return str(rid)
    except Exception:  # noqa: BLE001
        return str(uuid.uuid4())


def _repair_iso(ts: Any) -> str:
    if isinstance(ts, str) and ts.strip():
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return ts.strip()
        except ValueError:
            pass
    return _now_iso()


def _score_to_label(score: int) -> str:
    if score <= 0:
        return "None"
    if score < 34:
        return "Low"
    if score < 67:
        return "Moderate"
    return "High"


def build_preflight_skip_report(*, reason: str, request_id: str) -> Dict[str, Any]:
    ts = _now_iso()
    rid = _repair_request_id(request_id)
    summary = reason if reason.endswith(".") else f"{reason}."
    return {
        "verdict": "SKIP",
        "confidence": "low",
        "confidence_score": 0,
        "confidence_label": "None",
        "trust_signals": [],
        "signals": [],
        "reasons": [reason],
        "warnings": [],
        "llm_summary": summary,
        "review_summary": None,
        "similar_jobs": None,
        "recommendations": None,
        "data_freshness": ts,
        "request_id": rid,
        "cache": {"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        "report_schema_version": "2.0.0",
    }


def build_preflight_verify_job_uncertain_report(*, reason: str, request_id: str) -> Dict[str, Any]:
    ts = _now_iso()
    rid = _repair_request_id(request_id)
    summary = reason if reason.endswith(".") else f"{reason}."
    return {
        "verdict": "VERIFY",
        "confidence": "low",
        "confidence_score": 15,
        "confidence_label": "Low",
        "trust_signals": [],
        "signals": [],
        "reasons": [reason],
        "warnings": [],
        "llm_summary": summary,
        "review_summary": None,
        "similar_jobs": None,
        "recommendations": None,
        "data_freshness": ts,
        "request_id": rid,
        "cache": {"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        "report_schema_version": "2.0.0",
    }


def validate_and_repair_response(report: Dict[str, Any], *, request_id: str) -> Dict[str, Any]:
    """Enforce response honesty contract; mutate a shallow copy / repair fields — never raises."""
    out = dict(report)
    rid = _repair_request_id(out.get("request_id") or request_id)
    out["request_id"] = rid

    out["data_freshness"] = _repair_iso(out.get("data_freshness"))

    verdict = str(out.get("verdict") or "").upper()
    if verdict not in ("APPLY", "VERIFY", "SKIP"):
        logger.warning("response_contract_invalid_verdict request_id=%s repaired", rid)
        verdict = "VERIFY"
        out["verdict"] = verdict

    cs_raw = out.get("confidence_score")
    try:
        cs = int(cs_raw) if cs_raw is not None else None
    except (TypeError, ValueError):
        cs = None
    if cs is None:
        cs = 0
    cs = max(0, min(100, cs))
    out["confidence_score"] = cs
    # Label is always derived from the numeric score so UI cannot drift from the bar.
    out["confidence_label"] = _score_to_label(cs)

    reasons_in = out.get("reasons")
    reasons_out: List[str] = []
    if isinstance(reasons_in, list):
        for item in reasons_in:
            if isinstance(item, str) and item.strip():
                reasons_out.append(
                    scrub_internal_jargon(item.strip(), replacement="Some checks were inconclusive.")
                )
            elif isinstance(item, dict):
                reasons_out.append(
                    human_reason_warning_line(
                        code=str(item.get("code") or ""),
                        message=str(item.get("message") or ""),
                    )
                )
    if not reasons_out:
        reasons_out.append("Not enough verified information was available to complete this check.")
    out["reasons"] = reasons_out

    llm = out.get("llm_summary")
    if not isinstance(llm, str) or not llm.strip() or "." not in llm.strip():
        logger.warning("response_contract_llm_summary_repaired request_id=%s", rid)
        out["llm_summary"] = build_fallback_llm_summary(out)
    elif is_prompt_leak(llm) or contains_internal_verdict_jargon(llm):
        logger.warning("response_contract_llm_summary_leak request_id=%s", rid)
        out["llm_summary"] = build_fallback_llm_summary(out)
    else:
        out["llm_summary"] = llm.strip()

    rs = out.get("review_summary")
    if rs is not None:
        if not isinstance(rs, dict):
            out["review_summary"] = None
        else:
            ps = rs.get("plain_summary")
            if isinstance(ps, str) and ps.strip():
                if is_prompt_leak(ps) or contains_internal_verdict_jargon(ps):
                    logger.warning("response_contract_review_summary_leak request_id=%s", rid)
                    rs = dict(rs)
                    rs["plain_summary"] = "Employer reputation summary was unavailable for this result."
                    out["review_summary"] = rs
            else:
                rs = dict(rs)
                rs["plain_summary"] = "No employer reputation summary was available."
                out["review_summary"] = rs

    # Normalise similar_jobs: explicit None stays None for UI contract
    sj = out.get("similar_jobs")
    if sj is not None and not isinstance(sj, list):
        out["similar_jobs"] = None

    return out


def assert_no_demo_mode_in_production() -> None:
    """Fail startup when demo/fixture switches are enabled outside tests."""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    node = (os.environ.get("NODE_ENV") or "development").lower()
    if node not in ("production", "staging"):
        return

    offenders: List[str] = []
    for key in ("DEMO_MODE", "OFFLINE_MODE", "USE_FIXTURES", "USE_SEARCH_FIXTURES"):
        v = (os.environ.get(key) or "").strip().lower()
        if v in ("1", "true", "yes", "on"):
            offenders.append(key)

    path_key = "JOBSIGNAL_SEARCH_FIXTURE_PATH"
    p = (os.environ.get(path_key) or "").strip()
    if p:
        offenders.append(f"{path_key}(set)")

    if offenders:
        raise SystemExit(
            "Refusing to start: demo/fixture configuration is not allowed in production/staging: "
            + ", ".join(offenders)
        )
