"""Guard reputation summaries from instruction/meta leakage."""

from __future__ import annotations

import pytest

from backend.evidence.company_reviews import ReviewSource, _generate_llm_summary


@pytest.mark.asyncio
async def test_reputation_summary_meta_text_falls_back(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setattr("backend.core.llm_fireworks.llm_enabled", lambda: True)

    async def fake_call_llm_safe(*args, **kwargs):
        return (
            "I need to ignore any lines clearly about a different employer. "
            "Looking at the data: 1. Positive sources 2. Mixed sources."
        )

    monkeypatch.setattr("backend.core.llm_safe.call_llm_safe", fake_call_llm_safe)

    out = await _generate_llm_summary(
        "sofatutor",
        [
            ReviewSource(
                platform="Glassdoor",
                rating=4.6,
                review_count=1200,
                sentiment="positive",
                snippet="94% would recommend to a friend.",
                reliability="high",
            )
        ],
        request_id="test-guard",
    )
    assert out is not None
    low = out.lower()
    assert "i need to ignore" not in low
    assert "looking at the data" not in low
    assert "sofatutor" in low

