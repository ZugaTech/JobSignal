"""Production-oriented checks for URL admission and classification (no external I/O).

These tests guard the surface area users hit with real job links across ATS hosts.
They do not call Serper/Fireworks — only urlparse-style validation and regex hints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("url", "expect_job_hint"),
    [
        ("https://www.linkedin.com/jobs/view/123456789/", True),
        ("https://linkedin.com/job/live/abc", True),
        ("https://www.indeed.com/viewjob?jk=abc123", True),
        ("https://myworkdayjobs.com/acme/job/engineer", True),
        ("https://boards.greenhouse.io/acme/jobs/123", True),
        ("https://jobs.lever.co/acme/uuid", True),
        ("https://job-boards.greenhouse.io/acme/jobs/123", True),
        ("https://jobs.ashbyhq.com/acme/uuid", True),
        ("https://careers.smartrecruiters.com/acme/job/uuid", True),
        ("https://example.com/products", False),
        ("https://acme.teamtailor.com/jobs/123", True),
        ("https://apply.workable.com/acme/j/123", True),
        ("https://www.ziprecruiter.com/job/xyz", True),
    ],
)
def test_classify_url_expect_job_posting_hint(client: TestClient, url: str, expect_job_hint: bool):
    r = client.get("/v1/classify-url", params={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body.get("is_job_posting") is expect_job_hint


def test_validate_urls_batch_real_world_shapes(client: TestClient):
    """Strip-valid URLs with tracking params must pass format validation."""
    r = client.post(
        "/v1/validate-urls",
        json={
            "urls": [
                "https://boards.greenhouse.io/acme/jobs/123?utm_source=linkedin&utm_medium=share",
                "https://myworkdayjobs.com/acme/job/London-Software-Engineer_JR123",
                "https://apply.workable.com/acme/j/ABCDEF?view=full",
                "",
            ]
        },
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["ok"] is True
    assert results[1]["ok"] is True
    assert results[2]["ok"] is True
    assert results[3]["ok"] is False


def test_classify_url_rejects_obviously_invalid_scheme(client: TestClient):
    r = client.get("/v1/classify-url", params={"url": "ftp://example.com/job/1"})
    assert r.status_code == 200
    assert r.json()["is_job_posting"] is False


def test_classify_url_platform_labels_major_ats(client: TestClient):
    checks = [
        ("https://jobs.lever.co/foo/bar", "lever"),
        ("https://myworkdayjobs.com/x/y", "workday"),
        ("https://jobs.ashbyhq.com/foo", "ashby"),
        ("https://greenhouse.io/foo", "greenhouse"),
    ]
    for url, expect_platform in checks:
        r = client.get("/v1/classify-url", params={"url": url})
        assert r.status_code == 200
        body = r.json()
        assert body.get("is_job_posting") is True
        assert body.get("platform") == expect_platform
