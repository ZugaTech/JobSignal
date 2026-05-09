import pytest

from backend.core.coordinator import EvidenceCoordinator
from backend.core.normalization import normalize_job_input
from backend.core import recommendations as rec_mod
from backend.core.recommendations import (
    SerperDiscoveryProvider,
    any_search_configured,
    build_recommendations,
    effective_recommendations_max,
    extend_report_with_recommendations,
    recommendations_min_verify_score,
)


def test_effective_max_hard_caps_at_three(monkeypatch):
    monkeypatch.setenv("RECOMMENDATIONS_MAX", "99")
    assert effective_recommendations_max() == 3


def test_recommendations_min_verify_score_default(monkeypatch):
    monkeypatch.delenv("RECOMMENDATIONS_MIN_VERIFY_SCORE", raising=False)
    assert recommendations_min_verify_score() == 70


def test_recommendations_min_verify_score_env(monkeypatch):
    monkeypatch.setenv("RECOMMENDATIONS_MIN_VERIFY_SCORE", "80")
    assert recommendations_min_verify_score() == 80


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


@pytest.mark.asyncio
async def test_build_recommendations_url_only_emits_discovery_query(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    captured: list[str] = []

    class Coord:
        async def search(self, query: str, num: int = 5):
            captured.append(query)
            return [
                {
                    "title": "Other role",
                    "link": "https://jobs.other.com/listing/99",
                    "snippet": "",
                    "source": "other",
                }
            ]

    norm = normalize_job_input("https://widgets.example.com/careers/role-123", None)
    out = await build_recommendations(Coord(), norm, max_collect=5)  # type: ignore[arg-type]
    assert captured
    q = captured[0].lower()
    assert "example" in q or "jobs" in q or "careers" in q
    assert len(out) == 1


@pytest.mark.asyncio
async def test_build_recommendations_dedupes_primary_canonical(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")

    class Coord:
        async def search(self, query: str, num: int = 5):
            return [
                {
                    "title": "Same job",
                    "link": "https://acme.example.com/open-positions/55?utm_source=x",
                    "snippet": "",
                    "source": "web",
                }
            ]

    norm = normalize_job_input("https://acme.example.com/open-positions/55", None)
    out = await build_recommendations(Coord(), norm, max_collect=5)  # type: ignore[arg-type]
    assert out == []


@pytest.mark.asyncio
async def test_extend_filters_by_confidence_and_skip(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("RECOMMENDATIONS_MIN_VERIFY_SCORE", "70")

    norm = normalize_job_input("https://co.example.com/jobs/1", "Software Engineer")

    async def fake_build(*_a, **_kw):
        return [
            {
                "url": "https://good.example/j",
                "title": "A",
                "company": "Co",
                "platform": "x",
                "snippet": "",
            },
            {
                "url": "https://weak.example/j",
                "title": "B",
                "company": "Co",
                "platform": "x",
                "snippet": "",
            },
            {
                "url": "https://skip.example/j",
                "title": "C",
                "company": "Co",
                "platform": "x",
                "snippet": "",
            },
        ]

    monkeypatch.setattr(rec_mod, "build_recommendations", fake_build)

    async def verify_candidate(url: str):
        if "good.example" in url:
            return {"verdict": "APPLY", "confidence_score": 85}
        if "weak.example" in url:
            return {"verdict": "VERIFY", "confidence_score": 50}
        return {"verdict": "SKIP", "confidence_score": 90}

    report: dict = {"verdict": "VERIFY", "meta": {}}
    await extend_report_with_recommendations(
        report,
        norm,
        None,
        user_requested=True,
        verify_candidate=verify_candidate,
        coordinator=EvidenceCoordinator(api_key="k"),
    )
    recs = report.get("recommendations") or []
    assert len(recs) == 1
    assert recs[0]["url"] == "https://good.example/j"
    assert recs[0]["verdict"] == "APPLY"
    assert recs[0]["confidence_score"] == 85
    assert "recommendation_note" in recs[0]
