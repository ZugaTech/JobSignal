"""Quick reputation path: Serper-only, no Kimi baseline or synthesis."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.evidence.company_reviews import get_company_reviews


@pytest.mark.asyncio
async def test_quick_skips_synthesis_and_uses_live_search_only():
    rows = [
        {
            "title": "Acme Glassdoor reviews",
            "snippet": "Employees mention strong culture and benefits.",
            "link": "https://glassdoor.com/reviews/acme",
        }
    ]

    class Coord:
        def __init__(self) -> None:
            self.search_calls = 0

        async def search(self, q: str, num: int = 5):
            self.search_calls += 1
            return list(rows)

    coord = Coord()

    async def boom(*_a, **_k):  # pragma: no cover
        raise AssertionError("synthesize_reputation must not run in quick mode")

    with patch("backend.evidence.company_reviews.synthesize_reputation", new=boom):
        out = await get_company_reviews(coord, "Acme Corp", quick=True, request_id="t-quick")

    assert out.data_sources == ["Live search only"]
    assert out.review_confidence_score is not None
    assert out.review_confidence_score <= 74
    assert coord.search_calls == 2


@pytest.mark.asyncio
async def test_quick_skips_baseline_llm():
    rows = [
        {
            "title": "Beta Indeed employer reviews",
            "snippet": "Mixed feedback on management.",
            "link": "https://indeed.com/cmp/beta",
        }
    ]

    class Coord:
        async def search(self, q: str, num: int = 5):
            return list(rows)

    async def baseline_boom(*_a, **_k):  # pragma: no cover
        raise AssertionError("get_llm_company_baseline must not run in quick mode")

    with patch("backend.evidence.company_reviews.get_llm_company_baseline", new=baseline_boom):
        out = await get_company_reviews(Coord(), "Beta LLC", quick=True, request_id="t-quick-2")

    assert out.data_sources == ["Live search only"]
