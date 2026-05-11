"""Curated employer hints when Kimi baseline would return unknown."""

from backend.core.employer_hints import lookup_curated_employer, merge_curated_baseline


def test_lookup_paystack_alias():
    hit = lookup_curated_employer("Paystack Nigeria")
    assert hit is not None
    assert hit["known"] is True
    assert "payment" in hit["reputation_summary"].lower()


def test_merge_prefers_llm_when_known_medium():
    llm = {"known": True, "confidence": "medium", "reputation_summary": "Solid signal."}
    merged = merge_curated_baseline("Flutterwave", llm)
    assert merged == llm


def test_merge_fills_when_llm_unknown():
    merged = merge_curated_baseline("Flutterwave Ltd", {"known": False, "confidence": "none"})
    assert merged is not None
    assert merged["known"] is True
    assert len(merged["reputation_summary"]) > 10
