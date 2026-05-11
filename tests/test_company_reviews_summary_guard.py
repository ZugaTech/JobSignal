"""Guard reputation summaries from instruction/meta leakage."""

from __future__ import annotations

import pytest

from backend.evidence.company_reviews import _generate_llm_summary, get_company_reviews


@pytest.mark.asyncio
async def test_reputation_summary_meta_text_falls_back(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setattr("backend.core.llm_fireworks.llm_enabled", lambda: True)

    async def fake_call_llm_safe(*_args, **_kwargs):
        return (
            "I need to ignore any lines clearly about a different employer. "
            "Looking at the data: 1. Positive sources 2. Mixed sources."
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call_llm_safe)

    out = await _generate_llm_summary(
        "sofatutor",
        overall_sentiment="mostly positive",
        avg_rating=4.6,
        green_flags=["94% would recommend working there to a friend"],
        red_flags=[],
        sources_found=2,
        request_id="test-guard",
    )
    assert out is not None
    low = out.lower()
    assert "i need to ignore" not in low
    assert "looking at the data" not in low
    assert "sofatutor" in low


@pytest.mark.asyncio
async def test_plain_summary_fallback_does_not_echo_raw_review_snippet(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    class DummyCoordinator:
        async def search(self, query: str, num: int = 5):
            _ = num
            if "Glassdoor" in query:
                return [
                    {
                        "title": "Deloitte reviews",
                        "snippet": "Deloitte has an employee rating of 3.8 out of 5 stars, based on 113,693 company reviews on Glassdoor.",
                        "link": "https://glassdoor.com/reviews/deloitte",
                    }
                ]
            return []

    out = await get_company_reviews(DummyCoordinator(), "Deloitte")
    low = out.plain_summary.lower()
    assert "113,693 company reviews on glassdoor" not in low
    assert "deloitte" in low

