import pytest

from backend.core.coordinator import EvidenceCoordinator
from backend.core.normalization import normalize_job_input
from backend.core.recommendations import (
    SerperDiscoveryProvider,
    any_search_configured,
    build_recommendations,
    effective_recommendations_max,
    extend_report_with_recommendations,
)


def test_effective_max_hard_caps_at_three(monkeypatch):
    monkeypatch.setenv("RECOMMENDATIONS_MAX", "99")
    assert effective_recommendations_max() == 3


def test_any_search_configured_requires_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    assert any_search_configured() is False
    monkeypatch.setenv("SERPER_API_KEY", "x")
    assert any_search_configured() is True


@pytest.mark.asyncio
async def test_build_recommendations_returns_empty_without_search_config(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    norm = normalize_job_input("https://example.com/jobs/1", "Senior engineer role")
    out = await build_recommendations(EvidenceCoordinator(api_key=""), norm)
    assert out == []


@pytest.mark.asyncio
async def test_extend_report_skips_when_user_not_requested():
    report: dict = {"verdict": "VERIFY"}
    norm = normalize_job_input("https://example.com/jobs/1", "Role")
    async def verify_candidate(_u: str):
        return report

    await extend_report_with_recommendations(
        report,
        norm,
        None,
        user_requested=False,
        verify_candidate=verify_candidate,
        coordinator=None,
    )
    assert "recommendations" not in report


@pytest.mark.asyncio
async def test_serper_discovery_maps_missing_title_to_plain_language():
    class Coord:
        async def search(self, query: str, num: int = 5):
            return [{"title": "", "link": "https://jobs.example.com/x", "snippet": "", "source": "example"}]

    prov = SerperDiscoveryProvider()
    rows = await prov.search(Coord(), "test", limit=3)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert "not provided by search" in rows[0]["title"].lower()
