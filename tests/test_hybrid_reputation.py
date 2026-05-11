"""Hybrid LLM + Serper reputation pipeline unit tests."""

from __future__ import annotations

import json

import pytest

from backend.evidence.company_reviews import (
    contains_raw_snippet,
    extract_company_from_domain,
    get_llm_company_baseline,
    synthesize_reputation,
)


@pytest.mark.asyncio
async def test_get_llm_company_baseline_accepts_known_major_employer(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")

    payload = {
        "known": True,
        "company_type": "public",
        "industry": "Technology",
        "headquarters": "Mountain View, USA",
        "size_estimate": "enterprise",
        "reputation_summary": "Well-known global technology employer.",
        "known_positives": ["Strong brand", "Compensation", "Benefits"],
        "known_concerns": ["High expectations"],
        "confidence": "high",
        "knowledge_cutoff_note": "",
    }

    async def fake_call(*_a, **_kw):
        return json.dumps(payload)

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)
    out = await get_llm_company_baseline("Google", job_title="Engineer", request_id="t-google")
    assert out is not None
    assert out.get("known") is True
    assert out.get("confidence") == "high"


@pytest.mark.asyncio
async def test_get_llm_company_baseline_unknown_for_fictional(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")

    async def fake_call(*_a, **_kw):
        return json.dumps(
            {
                "known": False,
                "company_type": "unknown",
                "industry": None,
                "headquarters": None,
                "size_estimate": None,
                "reputation_summary": "",
                "known_positives": [],
                "known_concerns": [],
                "confidence": "none",
                "knowledge_cutoff_note": "",
            }
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)
    out = await get_llm_company_baseline("FictionalCorpXYZ123", request_id="t-fic")
    assert out is None


@pytest.mark.asyncio
async def test_synthesize_reputation_avoids_raw_snippet_echo(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")

    async def fake_call(*_a, **_kw):
        return json.dumps(
            {
                "overall_sentiment": "mixed",
                "review_confidence_score": 72,
                "plain_summary": (
                    "Deloitte is a large professional services firm. "
                    "Employee sentiment online is mixed, with both growth-oriented and demanding-workload themes."
                ),
                "green_flags": ["Structured career paths"],
                "red_flags": ["Long hours during peak periods"],
                "data_sources": ["LLM knowledge", "Live search"],
                "reliability": "medium",
            }
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)
    base = {"known": True, "reputation_summary": "Big Four firm.", "known_positives": [], "known_concerns": []}
    serper = [{"title": "Reviews", "snippet": "Summary only", "link": "https://example.com"}]
    out = await synthesize_reputation(
        "Deloitte",
        base,
        serper,
        legacy_score=70,
        legacy_sentiment="mixed",
        legacy_green=["g"],
        legacy_red=["r"],
        sources_found=2,
        request_id="t-syn",
    )
    assert out is not None
    ps = str(out.get("plain_summary") or "").lower()
    assert "out of 5 stars" not in ps
    assert "company reviews on" not in ps


@pytest.mark.asyncio
async def test_synthesize_reputation_llm_only_branch(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")

    async def fake_call(*_a, **_kw):
        return json.dumps(
            {
                "overall_sentiment": "positive",
                "review_confidence_score": 55,
                "plain_summary": (
                    "Wema Bank is a Nigerian financial institution. "
                    "Note: live review data was unavailable at this time."
                ),
                "green_flags": ["Established retail bank"],
                "red_flags": [],
                "data_sources": ["LLM knowledge only"],
                "reliability": "medium",
            }
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)
    base = {
        "known": True,
        "reputation_summary": "Regional bank.",
        "known_positives": ["Retail presence"],
        "known_concerns": [],
        "confidence": "medium",
    }
    out = await synthesize_reputation(
        "Wema Bank",
        base,
        None,
        legacy_score=50,
        legacy_sentiment="mixed",
        legacy_green=[],
        legacy_red=[],
        sources_found=0,
        request_id="t-llm-only",
    )
    assert out is not None
    assert out.get("data_sources") == ["LLM knowledge only"]
    assert "unavailable" in str(out.get("plain_summary") or "").lower()


@pytest.mark.asyncio
async def test_synthesize_reputation_returns_none_when_both_sources_missing():
    out = await synthesize_reputation(
        "X",
        None,
        None,
        legacy_score=50,
        legacy_sentiment="unknown",
        legacy_green=[],
        legacy_red=[],
        sources_found=0,
        request_id="t-none",
    )
    assert out is None


def test_extract_company_from_domain_wema_careers():
    # ``wemabank`` is re-split into "Wema Bank" so the LLM baseline and Serper queries
    # see a recognizable employer name, not a single-word slug.
    assert extract_company_from_domain("https://careers.wemabank.com/jobs/123") == "Wema Bank"


def test_contains_raw_snippet_two_markers():
    s = "The firm has 3.8 out of 5 stars based on 1,000 company reviews on Glassdoor."
    assert contains_raw_snippet(s) is True


@pytest.mark.asyncio
async def test_get_llm_company_baseline_caches_positive_result(monkeypatch):
    """Second call for the same employer must skip the LLM and hit the in-process cache."""
    from backend.evidence import company_reviews as cr

    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")
    cr.clear_baseline_cache()

    calls = {"n": 0}

    async def fake_call(*_a, **_kw):
        calls["n"] += 1
        return json.dumps(
            {
                "known": True,
                "reputation_summary": "Cached test employer.",
                "known_positives": ["Stable"],
                "known_concerns": [],
                "confidence": "high",
            }
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)

    first = await cr.get_llm_company_baseline("CacheCo Inc")
    second = await cr.get_llm_company_baseline("CacheCo Inc")
    third = await cr.get_llm_company_baseline("cacheco inc")  # normalized key

    assert first is not None and first.get("known") is True
    assert second is not None and second.get("known") is True
    assert third is not None
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_get_llm_company_baseline_negative_cached_skips_second_llm(monkeypatch):
    """Unknown employer (known:false) must cache so we do not call Fireworks twice."""
    from backend.evidence import company_reviews as cr

    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")
    cr.clear_baseline_cache()

    calls = {"n": 0}

    async def fake_call(*_a, **_kw):
        calls["n"] += 1
        return json.dumps(
            {
                "known": False,
                "reputation_summary": "",
                "known_positives": [],
                "known_concerns": [],
                "confidence": "none",
            }
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call)

    first = await cr.get_llm_company_baseline("TotallyUnknownEmployerXYZ999")
    second = await cr.get_llm_company_baseline("TotallyUnknownEmployerXYZ999")

    assert first is None
    assert second is None
    assert calls["n"] == 1
