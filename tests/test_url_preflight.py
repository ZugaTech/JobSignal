"""Regression: job URLs with long query strings must not false-positive as SQL injection."""

import pytest

from backend.core.env import EnvConfig
from backend.core.normalization import normalize_job_url
from backend.core.url_preflight import validate_url_format
from backend.core.url_preflight import evaluate_job_url_preflight

LINKEDIN_TRACKING_URL = (
    "https://www.linkedin.com/jobs/view/4403231467/?alternateChannel=search"
    "&eBP=CwEAAAGeDKwlcovpRhg5UV0oxAY598QzeeJRFeKffNub0NmCI-l6vIwrKgdkEt8G1XIjSM2-ocXvgm20SwOEQVuvjABVS7N_Cpeq07i0q9jN9H3EewC1So7qLkSpgNKYIYmDFqRZg5BCb2BrrumZUvwOYowNEKwoQpMz9n1EF7egomXVFNOIQ4qVeicE7dN4iQp-Hzntvy6z6Jc1-UCs1wlpP7pP6L1DxbetuH-vTXNt--WsUg8u6_srJ4Wh9cjdz4tn74oFCS7wAldmDN_KPc0_8zEbCUDyo7UOFR3elIuDTSJ_ob6hTaKbcUiskKMsph4D76XpO4yDc-0YbblIXyLOb69k2w2U482tp4vOKJN3LfxPYL0obQCtCcsAYe0YPQom5Gl40Qfa1TSMwcgLMFlshzV7OIR5EmdCefkzofJpC9flT2YJ_GoBi7649yeYNabP3Oo9w4go5roWA9H9Toz4m3KX1uUj5EAtTw6EH1c"
    "&refId=a1A41ji5xBcWFA%2FOExOERg%3D%3D&trackingId=u%2Bl0xxE709oGIxTBv7XOMA%3D%3D"
)


def test_linkedin_job_url_with_tracking_query_not_rejected():
    assert validate_url_format(LINKEDIN_TRACKING_URL) is None


def test_plain_https_job_path_accepted():
    assert validate_url_format("https://www.linkedin.com/jobs/view/12345/") is None


def test_union_select_in_path_still_rejected():
    bad = "https://evil.example/hack/union%20select%201"
    assert validate_url_format(bad) is not None


def test_double_hyphen_only_in_query_does_not_reject():
    assert validate_url_format("https://jobs.example.com/posting?token=ab--cd") is None


def test_normalization_strips_linkedin_tracking_params():
    clean, _hash = normalize_job_url(LINKEDIN_TRACKING_URL)
    assert clean == "https://www.linkedin.com/jobs/view/4403231467/"


@pytest.mark.asyncio
async def test_brightermonday_listings_url_proceeds_when_job_fetch_disabled(monkeypatch):
    """Board listing paths like ``/listings/…`` are not in ``_JOB_PATH_RE``; host must still preflight as a job URL."""
    monkeypatch.setenv("ENABLE_JOB_FETCH", "0")
    cfg = EnvConfig.load(strict=False)
    url = "https://www.brightermonday.co.ke/listings/business-development-manager-vdm99p"
    result = await evaluate_job_url_preflight(url, None, cfg=cfg)
    assert result.outcome == "proceed"
    assert result.plain_reason == ""


@pytest.mark.asyncio
async def test_known_job_platform_does_not_depend_on_head(monkeypatch):
    async def fail_head(_url: str):
        raise AssertionError("known job platforms should not require HEAD preflight")

    monkeypatch.setattr("backend.core.url_preflight.head_domain_root", fail_head)
    cfg = EnvConfig.load(strict=False)
    result = await evaluate_job_url_preflight(LINKEDIN_TRACKING_URL, None, cfg=cfg)
    assert result.outcome == "proceed"


@pytest.mark.asyncio
async def test_unknown_domain_dns_failure_degrades_to_verify(monkeypatch):
    monkeypatch.setattr("backend.core.url_preflight.domain_resolves", lambda _url: False)
    cfg = EnvConfig.load(strict=False)
    result = await evaluate_job_url_preflight("https://example.invalid/anything", None, cfg=cfg)
    assert result.outcome == "verify_weak"
    assert "could not be reached" in result.plain_reason


@pytest.mark.asyncio
async def test_jobs_subdomain_hosted_ats_o_path_proceeds():
    cfg = EnvConfig.load(strict=False)
    result = await evaluate_job_url_preflight(
        "https://jobs.sofatutor.com/o/junior-full-stack-engineer-gn/c/new?source=LinkedIn+Basic+Jobs",
        None,
        cfg=cfg,
    )
    assert result.outcome == "proceed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://company.teamtailor.com/jobs/12345-engineer",
        "https://company.jobs.personio.com/job/123456?display=en",
        "https://apply.workable.com/acme/j/backend-engineer/",
        "https://careers.example.com/roles/backend-engineer",
        "https://talent.example.com/openings/123",
        "https://example.com/job-detail/backend-engineer",
    ],
)
async def test_common_ats_and_careers_url_shapes_proceed(url):
    cfg = EnvConfig.load(strict=False)
    result = await evaluate_job_url_preflight(url, None, cfg=cfg)
    assert result.outcome == "proceed"


@pytest.mark.asyncio
async def test_unknown_reachable_url_proceeds_to_pipeline_when_fetch_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_JOB_FETCH", "1")
    monkeypatch.setattr("backend.core.url_preflight.domain_resolves", lambda _url: True)

    async def fake_head(_url: str):
        return "ok"

    monkeypatch.setattr("backend.core.url_preflight.head_domain_root", fake_head)

    class FetchOutcome:
        signals = [{"details": "HTTP 200; page fetched but no obvious keyword in preflight metadata"}]

    monkeypatch.setattr("backend.core.url_preflight.run_job_page_fetch", lambda _url, _cfg: FetchOutcome())

    cfg = EnvConfig.load(strict=False)
    result = await evaluate_job_url_preflight("https://example.com/custom-role-page/abc", None, cfg=cfg)
    assert result.outcome == "proceed"
