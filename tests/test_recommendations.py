import pytest

from backend.core.normalization import normalize_job_input
from backend.core.recommendations import (
    any_search_configured,
    build_provider_chain,
    build_recommendations,
    collect_search_urls,
    effective_recommendations_max,
    extend_report_with_recommendations,
)


@pytest.fixture
def stub_path(tmp_path, monkeypatch) -> str:
    p = tmp_path / "search.json"
    p.write_text(
        """{"urls": ["https://a.example/job1", "https://b.example/job2", "https://c.example/job3", "https://d.example/job4"]}""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JOBSIGNAL_SEARCH_FIXTURE_PATH", str(p))
    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "fixture")
    return str(p)


def test_effective_max_hard_caps_at_three(monkeypatch):
    monkeypatch.setenv("RECOMMENDATIONS_MAX", "99")
    assert effective_recommendations_max() == 3


def test_collect_search_returns_urls(stub_path):
    _ = stub_path
    urls, _w = collect_search_urls(["acme hiring"], limit=4)
    assert len(urls) == 4
    assert all(u.startswith("https://") for u in urls)


def test_build_recommendations_max_three_and_high_first(stub_path):
    _ = stub_path
    norm = normalize_job_input("https://seed.example/posting", "We need a senior engineer for acme")
    calls: list[str] = []

    def verify_candidate(url: str) -> dict:
        calls.append(url)
        if "job1" in url or "job3" in url:
            return {
                "verdict": "VERIFY",
                "confidence": "high",
                "warnings": [],
                "signals": [],
                "reasons": [{"code": "r1", "message": "m1"}, {"code": "r2", "message": "m2"}],
            }
        return {
            "verdict": "VERIFY",
            "confidence": "medium",
            "warnings": [],
            "signals": [],
            "reasons": [{"code": "r1", "message": "m1"}, {"code": "r2", "message": "m2"}],
        }

    recs, _w = build_recommendations(norm, None, verify_candidate=verify_candidate)
    assert len(recs) <= 3
    bands = [r["confidence_band"] for r in recs]
    assert bands[0] == "HIGH"
    if len(bands) > 1:
        assert "HIGH" not in bands[1:] or bands.count("HIGH") >= 1


def test_provider_fallback_empty_then_fixture(monkeypatch, stub_path):
    _ = stub_path
    class EmptySerp:
        name = "serpapi"

        def search(self, _query: str, *, limit: int) -> list[str]:
            return []

    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "serpapi,fixture")
    monkeypatch.setattr("backend.core.recommendations.SerpApiSearchProvider", EmptySerp)
    chain = build_provider_chain()
    assert [p.name for p in chain] == ["serpapi", "fixture"]
    urls, _ = collect_search_urls(["test"], limit=3)
    assert len(urls) >= 1


def test_extend_report_respects_explicit_false(monkeypatch, stub_path):
    _ = stub_path
    monkeypatch.setenv("RECOMMENDATIONS_ENABLED", "1")
    norm = normalize_job_input("https://x.example/j", "role")
    report: dict = {"verdict": "VERIFY", "confidence": "low", "warnings": [], "reasons": [], "signals": []}

    extend_report_with_recommendations(
        report,
        norm,
        None,
        user_requested=False,
        verify_candidate=lambda u: report,
    )
    assert "recommendations" not in report


def test_extend_report_unavailable_without_config(monkeypatch):
    monkeypatch.delenv("JOBSIGNAL_SEARCH_FIXTURE_PATH", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    assert any_search_configured() is False
    norm = normalize_job_input("https://x.example/j", "role")
    report: dict = {
        "verdict": "VERIFY",
        "confidence": "low",
        "warnings": [],
        "reasons": [],
        "signals": [],
        "meta": {"pipeline_version": "1", "scorer_version": "1"},
    }
    extend_report_with_recommendations(
        report,
        norm,
        None,
        user_requested=True,
        verify_candidate=lambda u: report,
    )
    assert report.get("recommendations") == []
    assert report["meta"].get("recommendations_status") == "unavailable"


def test_by_query_substring_fixture(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    p.write_text(
        '{"urls": [], "by_query_substring": {"widget": ["https://widget.co/a", "https://widget.co/b"]}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("JOBSIGNAL_SEARCH_FIXTURE_PATH", str(p))
    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "fixture")
    urls, _ = collect_search_urls(["widget engineer"], limit=5)
    assert urls == ["https://widget.co/a", "https://widget.co/b"]


def test_search_empty_sets_empty_status(monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{\"urls\": []}", encoding="utf-8")
    monkeypatch.setenv("JOBSIGNAL_SEARCH_FIXTURE_PATH", str(p))
    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "fixture")
    monkeypatch.setenv("RECOMMENDATIONS_ENABLED", "1")

    norm = normalize_job_input("https://seed.example/posting", "some role text")
    report: dict = {
        "verdict": "VERIFY",
        "confidence": "low",
        "warnings": [],
        "reasons": [{"code": "r1", "message": "m1"}, {"code": "r2", "message": "m2"}],
        "signals": [],
        "meta": {"pipeline_version": "1", "scorer_version": "1"},
    }
    extend_report_with_recommendations(report, norm, None, user_requested=None, verify_candidate=lambda u: report)
    assert report.get("recommendations") == []
    assert report["meta"].get("recommendations_status") == "empty"
