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
        _sig("official_careers_page", "T1", "high"),
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
    # Exactly two medium+ T1 rows: passes APPLY gates but lands in low confidence band (<45).
    signals = [
        _sig("official_careers_page", "T1", "medium"),
        _sig("fetch_ok", "T1", "medium"),
        _sig("domain_align", "T1", "low"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "VERIFY"
    codes = [w["code"] for w in d["warnings"]]
    assert "HONESTY_GUARD" in codes


def test_reasons_minimum_length():
    d = decide_from_signals([_sig("search_corroboration", "T3", "low")], url_provided=False)
    assert len(d["reasons"]) >= 2


def test_verify_description_only_leads_with_prefer_posting_url():
    """Ensure pasted-text VERIFY does not read like URL-based corroboration alone."""
    d = decide_from_signals([_sig("search_corroboration", "T3", "low")], url_provided=False)
    assert d["verdict"].value == "VERIFY"
    assert d["reasons"][0]["code"] == "PREFER_POSTING_URL"
    assert "URL" in (d["reasons"][0].get("message") or "") or "url" in (d["reasons"][0].get("message") or "").lower()


def test_decision_to_jsonable_roundtrip_keys():
    d = decide_from_signals(
        [_sig("fetch_ok", "T1", "high"), _sig("domain_align", "T1", "medium"), _sig("board_corroboration", "T2", "medium")],
        url_provided=True,
    )
    j = decision_to_jsonable(d)
    assert j["verdict"] in {"APPLY", "VERIFY", "SKIP"}
    assert isinstance(j["signals"], list)
    assert "confidence_score" in j
    assert isinstance(j["confidence_score"], int)
    assert 0 <= j["confidence_score"] <= 100


def test_decision_to_jsonable_missing_score_uses_zero_not_band_default():
    d = decide_from_signals([_sig("search_corroboration", "T3", "low")], url_provided=False)
    d["confidence"] = "medium"
    d["confidence_score"] = None
    assert decision_to_jsonable(d)["confidence_score"] == 0


def test_confidence_score_varies_with_signals_not_always_band_default():
    """Regression: UI must not map every medium verdict to a flat 60 via band-only scores."""
    weak = decide_from_signals([_sig("search_corroboration", "T3", "low")], url_provided=False)
    strongish = decide_from_signals(
        [
            _sig("company_linkedin_presence", "T2", "high"),
            _sig("careers_domain_match", "T1", "high"),
            _sig("salary_range_plausibility", "T3", "medium"),
            _sig("role_title_consistency", "T3", "high"),
            _sig("jd_specificity", "T3", "high"),
            _sig("jd_recruiter_intent_score", "T3", "medium"),
            _sig("jd_employer_identifiability", "T3", "high"),
        ],
        url_provided=True,
    )
    w = decision_to_jsonable(weak)["confidence_score"]
    s = decision_to_jsonable(strongish)["confidence_score"]
    assert w != s, "composite confidence_score should reflect signal mix, not a constant band mapping"


def test_url_signal_mix_scores_higher_than_description_only_same_role():
    url_backed = decide_from_signals(
        [
            _sig("company_linkedin_presence", "T1", "high"),
            _sig("careers_domain_match", "T1", "high"),
            _sig("company_registry_presence", "T2", "medium"),
            _sig("cross_platform_freshness", "T2", "high"),
            _sig("posting_duplication_signal", "T2", "high"),
            _sig("jd_specificity", "T3", "high"),
        ],
        url_provided=True,
    )
    description_only = decide_from_signals(
        [
            _sig("jd_specificity", "T3", "high"),
            _sig("jd_recruiter_intent_score", "T3", "medium"),
            _sig("jd_employer_identifiability", "T3", "medium"),
        ],
        url_provided=False,
    )
    url_score = decision_to_jsonable(url_backed)["confidence_score"]
    text_score = decision_to_jsonable(description_only)["confidence_score"]
    assert url_score != text_score
    assert url_score > text_score


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
    assert r["report_schema_version"] == "2.0.0"
    assert r["cache"]["hit"] is True


# ---------------------------------------------------------------------------
# Description-only intelligence (Path C + TEXT_PATTERN_MATCH SKIP)
# ---------------------------------------------------------------------------


def _strict_text_only_signals() -> list[dict]:
    """Signals that satisfy every Path C gate."""

    return [
        _sig("jd_specificity", "T3", "high"),
        _sig("jd_employer_identifiability", "T3", "high"),
        _sig("jd_recruiter_intent_score", "T3", "high"),
        _sig("jd_scam_indicators", "T3", "none"),
        _sig("jd_ai_generated_score", "T3", "low"),
        _sig("jd_content_farm_score", "T3", "low"),
    ]


def test_text_only_apply_promotes_with_strict_combo():
    d = decide_from_signals(_strict_text_only_signals(), url_provided=False)
    assert d["verdict"].value == "APPLY"
    assert d["confidence"] == "medium"
    codes_w = [w["code"] for w in d["warnings"]]
    assert "TEXT_ONLY_NOT_CORROBORATED" in codes_w
    codes_r = [r["code"] for r in d["reasons"]]
    assert "TEXT_ONLY_APPLY" in codes_r


def test_text_only_apply_blocked_when_url_provided():
    # Even with a strict combo, Path C must not apply once a URL is present.
    d = decide_from_signals(_strict_text_only_signals(), url_provided=True)
    # No URL evidence rows present -> should not collapse to APPLY via Path C.
    assert d["verdict"].value != "APPLY"


def test_text_only_apply_blocked_by_any_red_flag():
    rows = _strict_text_only_signals() + [_sig("jd_red_flags", "T3", "high", "vague,vague,vague")]
    d = decide_from_signals(rows, url_provided=False)
    assert d["verdict"].value != "APPLY"


def test_severe_text_pattern_skip_two_high():
    # scam_indicators high + content_farm_score high -> SKIP.
    rows = [
        _sig("jd_scam_indicators", "T3", "high", "training_fee, payment_required"),
        _sig("jd_content_farm_score", "T3", "high"),
        _sig("jd_specificity", "T3", "low"),
    ]
    d = decide_from_signals(rows, url_provided=False)
    assert d["verdict"].value == "SKIP"
    codes = [r["code"] for r in d["reasons"]]
    assert "TEXT_PATTERN_MATCH" in codes
    # Copy must include a non-accusatory disclaimer; must avoid asserting fraud/scam outright.
    text = " ".join(r["message"] for r in d["reasons"]).lower()
    assert "not a fraud claim" in text, "must include explicit non-accusatory disclaimer"
    for accusation in ("is a scam", "is fraudulent", "fraudulent posting"):
        assert accusation not in text, f"must not assert: {accusation!r}"


def test_severe_text_pattern_skip_token_plus_high():
    # scam_indicators medium with a token in details + red_flags high -> SKIP.
    rows = [
        _sig("jd_scam_indicators", "T3", "medium", "telegram_only_contact"),
        _sig("jd_red_flags", "T3", "high", "vague,vague,vague,vague"),
    ]
    d = decide_from_signals(rows, url_provided=False)
    assert d["verdict"].value == "SKIP"
    codes = [r["code"] for r in d["reasons"]]
    assert "TEXT_PATTERN_MATCH" in codes


def test_severe_text_pattern_skip_requires_two_conditions():
    # Single "high" without a second condition or scam token -> not SKIP.
    rows = [_sig("jd_red_flags", "T3", "high", "vague,vague,vague")]
    d = decide_from_signals(rows, url_provided=False)
    assert d["verdict"].value != "SKIP"


def test_text_only_mid_red_flags_yield_strong_verify_copy():
    rows = [
        _sig("jd_specificity", "T3", "low"),
        _sig("jd_red_flags", "T3", "medium", "vague_responsibilities,no_company_info"),
        _sig("jd_content_farm_score", "T3", "medium"),
    ]
    d = decide_from_signals(rows, url_provided=False)
    assert d["verdict"].value == "VERIFY"
    codes = [r["code"] for r in d["reasons"]]
    assert "TEXT_RED_FLAGS" in codes


def test_scorer_version_is_current():
    assert SCORER_VERSION == "3.2.2"
