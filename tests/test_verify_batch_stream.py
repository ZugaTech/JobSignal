"""Streaming batch verify route — NDJSON lines."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.response_contract import build_preflight_skip_report


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_verify_batch_empty_returns_400(client: TestClient) -> None:
    r = client.post("/v1/verify/batch", json={"urls": [], "options": {}})
    assert r.status_code == 400


def test_verify_batch_too_many_urls(client: TestClient) -> None:
    r = client.post(
        "/v1/verify/batch",
        json={"urls": [f"https://example{i}.com/j" for i in range(41)], "options": {}},
    )
    assert r.status_code == 422


def test_verify_batch_streams_ndjson(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def fake_verify(job_url, job_description, **kwargs):  # type: ignore[no-untyped-def]
        _ = job_url
        _ = job_description
        return build_preflight_skip_report(reason="Batch stub.", request_id=str(uuid.uuid4()))

    monkeypatch.setattr("backend.api.routes.verify.verify_job", fake_verify)

    with client.stream(
        "POST",
        "/v1/verify/batch",
        json={"urls": ["https://example.com/a", "https://example.com/b"], "options": {}},
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    lines = [ln for ln in body.split("\n") if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        obj = json.loads(ln)
        assert obj["ok"] is True
        assert "report" in obj
        assert obj["report"]["verdict"] == "SKIP"
