import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.evidence.company_reviews import get_company_reviews
from backend.core.orchestrator import verify_job

class DummyCoordinator:
    def __init__(self, ret=None):
        self.ret = ret or []
    async def search(self, *args, **kwargs):
        return self.ret

@pytest.mark.asyncio
async def test_review_signals_with_sources():
    mock_serper = [
        {"title": "Test Company Glassdoor Reviews", "snippet": "Test Company rating: 4.5 - 100 reviews. Great place to work, very stable culture.", "link": "https://glassdoor.com/reviews/test"},
        {"title": "Test Company Indeed Reviews", "snippet": "Test Company rating: 4.2 - 50 reviews. Highly recommended for growth.", "link": "https://indeed.com/reviews/test"}
    ]
    
    with patch.dict("os.environ", {"SERPER_API_KEY": "test_key", "FIREWORKS_API_KEY": "test_key"}):
        with patch("backend.core.llm_fireworks._client") as mock_llm:
            mock_llm.return_value.chat.completions.create.return_value.choices[0].message.content = "This company has a stellar reputation."
            
            res = await get_company_reviews(DummyCoordinator(mock_serper), "Test Company")
            assert res is not None
            assert res.sources_found >= 2
            assert res.review_confidence_score > 70
            assert "Glassdoor" in [h["platform"] for h in res.highlights]
            assert res.overall_sentiment == "mostly positive"

@pytest.mark.asyncio
async def test_review_signals_zero_sources():
    with patch.dict("os.environ", {"SERPER_API_KEY": "test_key"}):
        res = await get_company_reviews(DummyCoordinator([]), "NonExistentCompanyXYZ")
        assert res is not None
        assert res.sources_found == 0
        assert res.review_confidence_score is None
        assert res.overall_sentiment == "unknown"

@pytest.mark.asyncio
async def test_full_orchestration_with_reviews():
    mock_ext = MagicMock()
    mock_ext.company_hint = "Google"
    
    with patch.dict("os.environ", {"SERPER_API_KEY": "test_key", "FIREWORKS_API_KEY": "test_key"}):
        # Patching where it is USED, but since it is a local import, we patch the source or the orchestrator module if we can.
        # Actually patching backend.core.orchestrator.extract_entities fails because it's local.
        # We can patch backend.core.extraction.extract_entities instead.
        with patch("backend.core.extraction.extract_entities", return_value=mock_ext):
            with patch("backend.core.orchestrator.get_company_reviews") as mock_reviews:
                mock_reviews.return_value = AsyncMock()
                mock_reviews.return_value = {
                    "review_confidence_score": 85,
                    "plain_summary": "Top-tier employer."
                }
                pass
