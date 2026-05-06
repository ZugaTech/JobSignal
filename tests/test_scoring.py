import pytest

from backend.core.scoring import SCORER_VERSION, decide_from_signals, decision_to_jsonable
from backend.core.report import build_public_report


def _sig(sid: str, tier: str, strength: str, details: str = "") -> dict:
    return {
        "id": sid,
        "label": sid,
        "tier": tier,
        "strength": strength,
        "details": details,
    }


def test_policy_skip_returns_skip():
    d = decide_from_signals([], policy_skip=("SSRF", "Blocked private URL"))
    assert d["verdict"].value == "SKIP"
    assert d["confidence"] == "low"
    assert len(d["reasons"]) >= 2


def test_apply_when_t1_strong_with_support():
    signals = [
        _sig("fetch_ok", "T1", "high"),
        _sig("domain_align", "T1", "medium"),
        _sig("search_corroboration", "T2", "medium"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "APPLY"
    assert d["confidence"] == "high"


def test_verify_on_contradiction_fetch_without_domain():
    signals = [
        _sig("fetch_ok", "T1", "high"),
        _sig("domain_align", "T1", "none"),
        _sig("search_corroboration", "T3", "medium"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "VERIFY"


def test_verify_when_fetch_weak_with_url():
    signals = [
        _sig("fetch_ok", "T1", "low"),
        _sig("domain_align", "T1", "high"),
        _sig("board_corroboration", "T2", "high"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "VERIFY"


def test_verify_t3_only_loudest():
    signals = [
        _sig("search_corroboration", "T3", "high"),
    ]
    d = decide_from_signals(signals, url_provided=False)
    assert d["verdict"].value == "VERIFY"


def test_honesty_guard_downgrades_borderline_apply():
    # Exactly two medium+ T1 rows: passes APPLY gates but lands in low confidence band.
    signals = [
        _sig("fetch_ok", "T1", "medium"),
        _sig("domain_align", "T1", "medium"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "VERIFY"
    codes = [w["code"] for w in d["warnings"]]
    assert "HONESTY_GUARD" in codes


def test_reasons_minimum_length():
    d = decide_from_signals([_sig("search_corroboration", "T3", "low")], url_provided=False)
    assert len(d["reasons"]) >= 2


def test_decision_to_jsonable_roundtrip_keys():
    d = decide_from_signals(
        [_sig("fetch_ok", "T1", "high"), _sig("domain_align", "T1", "medium"), _sig("board_corroboration", "T2", "medium")],
        url_provided=True,
    )
    j = decision_to_jsonable(d)
    assert j["verdict"] in {"APPLY", "VERIFY", "SKIP"}
    assert isinstance(j["signals"], list)


def test_public_report_includes_schema_version():
    d = decide_from_signals(
        [_sig("fetch_ok", "T1", "high"), _sig("domain_align", "T1", "medium"), _sig("board_corroboration", "T2", "medium")],
        url_provided=True,
    )
    r = build_public_report(
        d,
        cache={"hit": True, "ttl_expires_at": "2099-01-01T00:00:00Z", "key_fingerprint": "abc"},
        meta={"pipeline_version": "1", "scorer_version": SCORER_VERSION},
    )
    assert r["report_schema_version"] == "1.1.0"
    assert r["cache"]["hit"] is True
