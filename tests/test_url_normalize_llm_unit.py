"""URL LLM recovery runs only as fallback (flag + credentials gated)."""

import pytest

from backend.core.url_normalize_llm import (
    llm_url_normalize_enabled,
    recover_job_url_with_llm_fallback,
)


@pytest.mark.asyncio
async def test_recovery_disabled_when_flag_off(monkeypatch):
    monkeypatch.delenv("ENABLE_LLM_URL_NORMALIZE", raising=False)
    assert llm_url_normalize_enabled() is False
    out = await recover_job_url_with_llm_fallback("https://example.com/job/1", request_id="t-unit")
    assert out.outcome == "disabled"
    assert out.canonical_url is None


@pytest.mark.asyncio
async def test_recovery_empty_input():
    out = await recover_job_url_with_llm_fallback("   ", request_id="t-empty")
    assert out.outcome == "uncertain"
