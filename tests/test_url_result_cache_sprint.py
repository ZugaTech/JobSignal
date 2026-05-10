"""Sprint: URL result cache, tracking-normalization, and admin cache bust."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.main import app
from backend.core.normalization import materialize_url_result_cache_key
from backend.core.url_result_cache import (
    RESULT_CACHE_KEY_PREFIX,
    should_store_url_result_cache,
    wrap_stored_payload,
)


def test_materialize_cache_key_ignores_tracking_params():
    a = "https://www.indeed.com/viewjob?jk=abc&utm_source=foo"
    b = "https://www.indeed.com/viewjob?jk=abc"
    assert materialize_url_result_cache_key(a) == materialize_url_result_cache_key(b)


def test_should_not_cache_low_confidence_verify():
    r = {
        "verdict": "VERIFY",
        "confidence_score": 35,
        "review_summary": {"plain_summary": "x"},
        "trust_signals": [{"status": "Strong Match"}] * 4,
    }
    assert should_store_url_result_cache(r) is False


def test_should_cache_apply_with_review_or_signals():
    r = {
        "verdict": "APPLY",
        "confidence_score": 72,
        "review_summary": {"plain_summary": "Solid employer signals.", "status": "ok"},
        "trust_signals": [{"status": "Strong Match"}, {"status": "Partial Match"}, {"status": "Verified"}],
    }
    assert should_store_url_result_cache(r) is True


@pytest.mark.asyncio
async def test_url_result_cache_roundtrip_and_bust(monkeypatch):
    from backend.core.cache_store import InMemoryCache

    mem = InMemoryCache()
    monkeypatch.setattr("backend.core.orchestrator._get_cache", lambda _cfg: mem)
    monkeypatch.setattr("backend.api.routes.verify._get_cache", lambda _cfg: mem)

    job_url = "https://example.com/jobs/123?ref=1"
    key_h = materialize_url_result_cache_key(job_url)
    assert key_h
    cache_key = RESULT_CACHE_KEY_PREFIX + key_h

    payload = {
        "verdict": "APPLY",
        "confidence_score": 80,
        "confidence_label": "High",
        "review_summary": {"plain_summary": "Good employer signals.", "status": "ok"},
        "trust_signals": [],
        "request_id": "00000000-0000-0000-0000-000000000001",
        "llm_summary": "Signals support applying for this role.",
        "reasons": [{"code": "GATES_PASSED", "message": "Checks passed."}],
        "warnings": [],
        "signals": [],
        "report_schema_version": "2.0.0",
        "cache": {"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        "meta": {"url_only_cache_eligible": True, "canonical_job_url": job_url},
    }
    env = wrap_stored_payload(report=payload, cached_at_iso="2020-01-01T00:00:00+00:00", ttl_seconds=604800)
    mem.set(cache_key, env, ttl_seconds=604800)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post("/v1/verify", json={"job_url": "https://example.com/jobs/123?utm_campaign=x"})
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1.get("cached") is True
        assert "cache_expires_in" in body1
        assert body1.get("original_analysis_date") == "2020-01-01T00:00:00+00:00"
        rs = body1.get("review_summary")
        assert isinstance(rs, dict) and str(rs.get("plain_summary") or "").strip()
        assert body1.get("cache_complete") is True

        d = await ac.delete("/v1/cache", params={"url": "https://example.com/jobs/123"})
        assert d.status_code == 200
        assert mem.get(cache_key) is None

        r2 = await ac.post("/v1/verify", json={"job_url": "https://example.com/jobs/123"})
        assert r2.status_code == 200
        assert r2.json().get("cached") is not True


@pytest.mark.asyncio
async def test_url_cache_hit_attaches_similar_jobs_when_requested(monkeypatch):
    """URL-result cache must not skip similar-job attachment when the client asks for it."""
    from backend.core.cache_store import InMemoryCache

    mem = InMemoryCache()
    monkeypatch.setattr("backend.core.orchestrator._get_cache", lambda _cfg: mem)
    monkeypatch.setattr("backend.api.routes.verify._get_cache", lambda _cfg: mem)

    async def fake_maybe_attach(
        report,
        norm=None,
        merged_fields=None,
        skip_recommendations=None,
        include_similar_jobs=None,
        coordinator=None,
    ):
        if include_similar_jobs:
            report["recommendations"] = [
                {
                    "url": "https://example.com/other-role",
                    "title": "Other role",
                    "company": "Example Co",
                    "platform": "example.com",
                    "verdict": "APPLY",
                    "confidence_score": 88,
                }
            ]

    monkeypatch.setattr("backend.core.orchestrator._maybe_attach_recommendations", fake_maybe_attach)

    job_url = "https://example.com/jobs/similar-flag-test"
    key_h = materialize_url_result_cache_key(job_url)
    assert key_h
    cache_key = RESULT_CACHE_KEY_PREFIX + key_h

    payload = {
        "verdict": "APPLY",
        "confidence_score": 80,
        "confidence_label": "High",
        "review_summary": {"plain_summary": "Good employer signals.", "status": "ok"},
        "trust_signals": [],
        "request_id": "00000000-0000-0000-0000-000000000099",
        "llm_summary": "Signals support applying for this role.",
        "reasons": [{"code": "GATES_PASSED", "message": "Checks passed."}],
        "warnings": [],
        "signals": [],
        "report_schema_version": "2.0.0",
        "cache": {"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        "meta": {"url_only_cache_eligible": True, "canonical_job_url": job_url},
        "similar_jobs": None,
    }
    env = wrap_stored_payload(report=payload, cached_at_iso="2020-01-01T00:00:00+00:00", ttl_seconds=604800)
    mem.set(cache_key, env, ttl_seconds=604800)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        body = await ac.post(
            "/v1/verify",
            json={"job_url": job_url, "include_similar_jobs": True},
        )
        assert body.status_code == 200
        data = body.json()
        assert data.get("cached") is True
        assert data.get("meta", {}).get("similar_jobs_requested") is True
        sj = data.get("similar_jobs")
        assert isinstance(sj, list) and len(sj) == 1
        assert sj[0].get("url") == "https://example.com/other-role"

        off = await ac.post(
            "/v1/verify",
            json={"job_url": job_url, "include_similar_jobs": False},
        )
        assert off.status_code == 200
        data_off = off.json()
        assert data_off.get("similar_jobs") is None
        assert not data_off.get("meta", {}).get("similar_jobs_requested")


@pytest.mark.asyncio
async def test_short_description_returns_verify(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "")
    monkeypatch.setenv("SEARCH_API_KEY", "")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/verify", json={"job_description": "short"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "VERIFY"
        assert any("too short" in str(x).lower() for x in (data.get("reasons") or []))


@pytest.mark.asyncio
async def test_report_detail_endpoint(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "")
    monkeypatch.setenv("SEARCH_API_KEY", "")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/verify", json={"job_description": "x" * 120})
        assert resp.status_code == 200
        rid = resp.json().get("request_id")
        assert rid
        det = await ac.get(f"/v1/report/{rid}")
        assert det.status_code == 200
        full = det.json()
        assert full.get("request_id") == rid
