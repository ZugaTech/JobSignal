"""Confidence label must always follow the numeric score (no drift)."""

from backend.core.response_contract import validate_and_repair_response
from backend.core.response_contract import build_preflight_skip_report


def test_confidence_label_derived_from_score_not_incoming_label():
    raw = {
        "verdict": "VERIFY",
        "confidence_score": 85,
        "confidence_label": "Low",  # inconsistent — must be repaired
        "trust_signals": [],
        "signals": [],
        "reasons": ["Test."],
        "warnings": [],
        "llm_summary": "Not enough data.",
        "review_summary": None,
        "cache": {"hit": False},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000001",
    }
    out = validate_and_repair_response(raw, request_id="x")
    assert out["confidence_score"] == 85
    assert out["confidence_label"] == "High"


def test_score_zero_maps_to_none_label():
    raw = {
        "verdict": "SKIP",
        "confidence_score": 0,
        "confidence_label": "High",
        "trust_signals": [],
        "signals": [],
        "reasons": ["Bad URL."],
        "warnings": [],
        "llm_summary": "Skipped.",
        "review_summary": None,
        "cache": {"hit": False},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000002",
    }
    out = validate_and_repair_response(raw, request_id="x")
    assert out["confidence_label"] == "None"


def test_fast_fail_skip_report_uses_zero_confidence():
    out = build_preflight_skip_report(reason="Invalid URL.", request_id="00000000-0000-4000-8000-000000000004")
    assert out["confidence_score"] == 0
    assert out["confidence_label"] == "None"
    assert isinstance(out.get("signals"), list)
    assert len(out["signals"]) == 1
    assert out["signals"][0].get("id") == "early_input_scope"


def test_missing_confidence_score_repairs_to_zero_not_band_default():
    raw = {
        "verdict": "VERIFY",
        "confidence": "medium",
        "confidence_label": "Moderate",
        "trust_signals": [],
        "signals": [],
        "reasons": ["No numeric score was returned."],
        "warnings": [],
        "llm_summary": "No numeric score was returned.",
        "review_summary": None,
        "cache": {"hit": False},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000003",
    }
    out = validate_and_repair_response(raw, request_id="x")
    assert out["confidence_score"] == 0
    assert out["confidence_label"] == "None"


def test_evidence_completeness_matches_coverage_ratio_not_inflated_row_count():
    raw = {
        "verdict": "VERIFY",
        "confidence_score": 50,
        "confidence_label": "Moderate",
        "trust_signals": [{"name": "A", "status": "Verified", "detail": "x"}] * 5,
        "signals": [{"id": f"sig_{i}", "strength": "low", "details": "d"} for i in range(5)],
        "reasons": ["Test."],
        "warnings": [],
        "llm_summary": "Test.",
        "review_summary": None,
        "verified_signal_count": 2,
        "total_signal_count": 10,
        "coverage_ratio": 0.2,
        "cache": {"hit": False},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000011",
    }
    out = validate_and_repair_response(raw, request_id="x")
    assert out["evidence_completeness_score"] == 20


def test_evidence_completeness_falls_back_to_verified_over_total_when_ratio_missing():
    raw = {
        "verdict": "VERIFY",
        "confidence_score": 40,
        "confidence_label": "Low",
        "trust_signals": [],
        "signals": [],
        "reasons": ["Test."],
        "warnings": [],
        "llm_summary": "Test.",
        "review_summary": None,
        "verified_signal_count": 3,
        "total_signal_count": 12,
        "cache": {"hit": True},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000012",
    }
    out = validate_and_repair_response(raw, request_id="x")
    assert out["evidence_completeness_score"] == 25
