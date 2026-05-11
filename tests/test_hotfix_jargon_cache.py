"""Hotfix: plain-language copy, URL cache completeness, jargon guards."""

from __future__ import annotations

import json

from backend.core.response_contract import validate_and_repair_response
from backend.core.url_result_cache import (
    decorate_hit_response,
    is_cacheable_response,
    parse_stored_payload,
    wrap_stored_payload,
)
from backend.core.user_copy import build_fallback_llm_summary, contains_internal_verdict_jargon


def test_wrap_stored_payload_roundtrips_review_summary():
    report = {
        "verdict": "APPLY",
        "confidence_score": 75,
        "review_summary": {"plain_summary": "Good culture mentions.", "status": "ok"},
        "trust_signals": [{"name": "x", "status": "Strong Match", "detail": ""}],
        "request_id": "rid",
    }
    raw = wrap_stored_payload(report=report, cached_at_iso="2026-01-01T00:00:00+00:00", ttl_seconds=3600)
    parsed = parse_stored_payload(raw)
    assert parsed is not None
    rep2, _, _ = parsed
    rs = rep2.get("review_summary")
    assert isinstance(rs, dict)
    assert rs.get("plain_summary") == "Good culture mentions."


def test_cache_hit_preserves_review_summary_identity():
    original = {
        "verdict": "SKIP",
        "confidence_score": 80,
        "review_summary": {"plain_summary": "Mixed reviews online.", "status": "ok"},
        "signals": [],
    }
    raw = wrap_stored_payload(report=original, cached_at_iso="2026-02-01T00:00:00+00:00", ttl_seconds=3600)
    rep2, _, _ = parse_stored_payload(raw)  # type: ignore[misc]
    assert rep2["review_summary"] == original["review_summary"]


def test_no_jargon_in_validated_reasons_and_llm_fallback():
    nasty = {
        "verdict": "VERIFY",
        "confidence": "medium",
        "confidence_score": 55,
        "trust_signals": [{"name": "A", "status": "Strong Match", "detail": ""}],
        "signals": [{"id": "fetch_ok", "strength": "high"}],
        "reasons": [{"code": "INSUFFICIENT_CORROBORATION", "message": "Did not meet APPLY gates: need T1 medium+ with support."}],
        "warnings": [],
        "llm_summary": "Did not meet APPLY gates: need T1 medium+ with support.",
        "review_summary": None,
        "request_id": "00000000-0000-0000-0000-000000000099",
    }
    out = validate_and_repair_response(dict(nasty), request_id="00000000-0000-0000-0000-000000000099")
    blob = json.dumps(out["reasons"] + [out["llm_summary"]]).lower()
    assert "t1" not in blob
    assert "gate" not in blob
    assert "tier" not in blob


def test_summary_with_raw_signal_ids_is_repaired():
    leaked = {
        "verdict": "VERIFY",
        "confidence": "medium",
        "confidence_score": 55,
        "reasons": ["Not enough corroboration from official sources."],
        "warnings": [],
        "signals": [{"id": "fetch_ok", "strength": "high"}],
        "llm_summary": (
            "Key points from the signals: - Decision: VERIFY, Confidence: medium - "
            "Signals: fetch_ok, domain_align, careers_page_match."
        ),
        "review_summary": None,
        "request_id": "00000000-0000-0000-0000-000000000098",
    }
    out = validate_and_repair_response(dict(leaked), request_id="00000000-0000-0000-0000-000000000098")
    low = str(out["llm_summary"]).lower()
    assert "fetch_ok" not in low
    assert "domain_align" not in low
    assert "signals:" not in low
    assert "decision:" not in low


def test_llm_fallback_template_clean():
    report = {
        "verdict": "VERIFY",
        "signals": [
            {"id": "fetch_ok", "strength": "high"},
            {"id": "domain_align", "strength": "low"},
        ],
        "reasons": [{"code": "INSUFFICIENT_CORROBORATION", "message": "ignored"}],
    }
    s = build_fallback_llm_summary(report)
    assert "We checked" not in s
    assert not contains_internal_verdict_jargon(s)


def test_contains_internal_jargon_flags_signal_id_style_output():
    txt = "Decision: VERIFY. Signals: fetch_ok, domain_align, company_reputation_signal."
    assert contains_internal_verdict_jargon(txt) is True


def test_is_cacheable_response_rules():
    base_ok = {
        "verdict": "APPLY",
        "confidence_score": 72,
        "review_summary": {"plain_summary": "ok", "status": "ok"},
    }
    assert is_cacheable_response(base_ok) is True

    low_conf = dict(base_ok)
    low_conf["confidence_score"] = 30
    assert is_cacheable_response(low_conf) is False

    no_review = dict(base_ok)
    no_review["review_summary"] = None
    assert is_cacheable_response(no_review) is False

    unavailable = dict(base_ok)
    unavailable["review_summary"] = {"status": "unavailable"}
    assert is_cacheable_response(unavailable) is True


def test_decorate_hit_cache_complete_flags():
    full = {"verdict": "APPLY", "review_summary": {"plain_summary": "x", "status": "ok"}}
    out = decorate_hit_response(
        full,
        cached_at="2026-01-01T00:00:00+00:00",
        expires_at_iso="2026-01-08T00:00:00+00:00",
        now_iso="2026-01-02T00:00:00+00:00",
    )
    assert out["cache_complete"] is True

    partial = {"verdict": "APPLY", "review_summary": {"status": "ok"}}
    out2 = decorate_hit_response(
        partial,
        cached_at="2026-01-01T00:00:00+00:00",
        expires_at_iso="2026-01-08T00:00:00+00:00",
        now_iso="2026-01-02T00:00:00+00:00",
    )
    assert out2["cache_complete"] is False
