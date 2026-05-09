import time

import backend.core.orchestrator as orchestrator


import pytest

@pytest.mark.asyncio
async def test_verify_pipeline_completes_under_15_seconds_with_mocked_sources(monkeypatch):
    orchestrator._MEM_CACHE._data.clear()

    async def _fake_collect_serper_queries(base_query: str, company: str, title: str):
        return {
            "careers": ([], "verified", None),
            "board": ([], "verified", None),
            "rep": ([], "verified", None),
            "linkedin": ([], "verified", None),
            "registry": ([], "verified", None),
            "duplicates": ([], "verified", None),
        }

    monkeypatch.setattr("backend.core.evidence._collect_serper_queries", _fake_collect_serper_queries)
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "0")
    monkeypatch.setenv("ENABLE_JOB_FETCH", "0")

    started = time.perf_counter()
    report = await orchestrator.verify_job(
        "https://example.com/jobs/backend-engineer",
        "Backend Engineer. Salary $110000-$130000. Contact: hiring@example.com",
        skip_recommendations=True,
        recommendations_enabled=False,
    )
    elapsed = time.perf_counter() - started

    assert report["verdict"] in ("APPLY", "VERIFY", "SKIP")
    assert elapsed < 15.0

