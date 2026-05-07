from backend.core.scoring import decide_from_signals


def _sig(sid: str, tier: str, strength: str, details: str = "", status: str = "") -> dict:
    row = {"id": sid, "label": sid, "tier": tier, "strength": strength, "details": details}
    if status:
        row["status"] = status
    return row


def test_company_legitimacy_layer_scored_and_exposed():
    signals = [
        _sig("company_linkedin_presence", "T1", "high", "LinkedIn profile found", "pass"),
        _sig("careers_domain_match", "T1", "high", "Domains align", "pass"),
        _sig("company_registry_presence", "T2", "medium", "Registry result found", "pass"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["company_legitimacy_score"] >= 70
    assert len(d["company_signals"]) >= 2


def test_posting_authenticity_layer_scored_and_exposed():
    signals = [
        _sig("salary_range_plausibility", "T3", "high", "Salary plausible", "pass"),
        _sig("role_title_consistency", "T3", "medium", "Title matches body", "pass"),
        _sig("contact_legitimacy", "T3", "high", "Corporate domain email", "pass"),
        _sig("posting_duplication_signal", "T2", "high", "Not widely duplicated", "pass"),
    ]
    d = decide_from_signals(signals, url_provided=False)
    assert d["posting_authenticity_score"] >= 70
    assert len(d["posting_signals"]) >= 3


def test_temporal_freshness_layer_sets_stale_flag():
    signals = [
        _sig("cross_platform_freshness", "T2", "low", "Found on one board", "fail"),
        _sig("staleness_flag", "T2", "low", "Observed listing age up to 45 days", "fail"),
        _sig("first_seen_estimate", "T2", "low", "2026-03-10", "fail"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["staleness_flag"] is True
    assert d["first_seen_estimate"] == "2026-03-10"
    assert d["freshness_score"] <= 40


def test_honest_uncertainty_forces_verify_with_low_coverage():
    signals = [
        _sig("jd_specificity", "T3", "medium", "specificity=medium", "pass"),
        _sig("jd_red_flags", "T3", "none", "", "unknown"),
    ]
    d = decide_from_signals(signals, url_provided=False)
    assert d["verdict"].value == "VERIFY"
    assert d["verified_signal_count"] < 3
    assert "incomplete" in d["disclaimer"].lower() or "unknown" in d["disclaimer"].lower()


def test_recalibrated_scoring_requires_three_layer_pass_for_high_apply_confidence():
    signals = [
        _sig("official_careers_page", "T1", "high"),
        _sig("fetch_ok", "T1", "high"),
        _sig("domain_align", "T1", "high"),
        _sig("company_linkedin_presence", "T1", "high", status="pass"),
        _sig("careers_domain_match", "T1", "high", status="pass"),
        _sig("company_registry_presence", "T2", "medium", status="pass"),
        _sig("salary_range_plausibility", "T3", "high", status="pass"),
        _sig("role_title_consistency", "T3", "high", status="pass"),
        _sig("contact_legitimacy", "T3", "high", status="pass"),
        _sig("posting_duplication_signal", "T2", "high", status="pass"),
        _sig("cross_platform_freshness", "T2", "high", status="pass"),
        _sig("staleness_flag", "T2", "high", status="pass"),
        _sig("first_seen_estimate", "T2", "medium", "2026-05-01", "pass"),
    ]
    d = decide_from_signals(signals, url_provided=True)
    assert d["verdict"].value == "APPLY"
    assert d["confidence"] in ("high", "medium")
    assert d["company_legitimacy_score"] >= 60
    assert d["posting_authenticity_score"] >= 60
    assert d["freshness_score"] >= 60

