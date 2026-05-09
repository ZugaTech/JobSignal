import pytest
import asyncio
from backend.evidence.company_reviews import (
    get_company_reviews,
    extract_company_name_hardened,
    _process_reddit,
    _process_x,
    _template_summary,
    ReviewSource
)

@pytest.mark.asyncio
async def test_review_pipeline_partial_on_timeout():
    class DummyCoordinator:
        def __init__(self):
            self.calls = 0
        async def search(self, query: str, num: int = 5):
            self.calls += 1
            if self.calls <= 3:
                await asyncio.sleep(12.0) # trigger timeout
                return []
            return [{"snippet": "great company", "link": "https://glassdoor.com", "title": "Review"}]
            
    res = await get_company_reviews(DummyCoordinator(), "Acme Corp")
    assert res.status == "unavailable"
    assert res.timeout is True
    assert res.partial is True

def test_reddit_red_flag_mass_layoffs():
    source = ReviewSource(
        platform="Reddit", rating=None, review_count=None, sentiment="negative",
        snippet="They just announced mass layoffs today.", reliability="medium", post_title="Help"
    )
    res = _process_reddit([source])
    assert "mass layoffs" in res["red_flags_found"]

def test_x_corroboration_required():
    source1 = ReviewSource(
        platform="X/Twitter", rating=None, review_count=None, sentiment="negative",
        snippet="This company is a scam.", reliability="low", post_title="Tweet"
    )
    res1 = _process_x([source1])
    assert "scam" not in res1["red_flags_found"]
    
    source2 = ReviewSource(
        platform="X/Twitter", rating=None, review_count=None, sentiment="negative",
        snippet="scam scam scam", reliability="low", post_title="Tweet 2"
    )
    res2 = _process_x([source1, source2])
    assert "scam" in res2["red_flags_found"]

def test_company_name_extraction_safe_null():
    assert extract_company_name_hardened(None, None) is None
    assert extract_company_name_hardened(None, "Just some random text") is None

def test_plain_summary_template():
    res = _template_summary("Acme", 0, "unknown", None, None)
    assert res == "Based on 0 sources, Acme has a unknown employer reputation. No strong positive signals were found. No major red flags were detected."

@pytest.mark.asyncio
async def test_full_verify_returns_200_on_review_timeout(monkeypatch):
    from backend.api.main import app
    from httpx import AsyncClient, ASGITransport
    
    # Mock coordinator to timeout
    class TimeoutCoordinator:
        async def search(self, *args, **kwargs):
            await asyncio.sleep(12)
            return []

        async def close(self) -> None:
            pass

        def set_max_calls(self, count: int) -> None:
            pass
        
    monkeypatch.setattr(
        "backend.core.orchestrator.EvidenceCoordinator",
        lambda api_key, search_timeout_s=5.0: TimeoutCoordinator(),
    )
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/v1/verify", json={"job_url": "https://google.com/jobs/1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_summary"]["status"] == "unavailable"
        assert data["review_summary"]["timeout"] is True
