"""URL LLM refine helper (disabled unless ENABLE_LLM_URL_NORMALIZE)."""

import pytest

from backend.core.url_normalize_llm import llm_url_normalize_enabled, maybe_refine_job_url_with_llm


@pytest.mark.asyncio
async def test_refine_no_op_when_flag_off(monkeypatch):
    monkeypatch.delenv("ENABLE_LLM_URL_NORMALIZE", raising=False)
    assert llm_url_normalize_enabled() is False
    out = await maybe_refine_job_url_with_llm("https://example.com/job/1", request_id="t-unit")
    assert out is None


@pytest.mark.asyncio
async def test_refine_no_op_when_empty_url():
    out = await maybe_refine_job_url_with_llm("   ", request_id="t-empty")
    assert out is None
