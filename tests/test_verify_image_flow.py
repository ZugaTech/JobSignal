import base64

import pytest

import backend.core.orchestrator as orchestrator
from backend.api.main import app
from fastapi.testclient import TestClient

MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6XKp6sAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def _clear_verify_cache():
    orchestrator._MEM_CACHE._data.clear()
    yield
    orchestrator._MEM_CACHE._data.clear()


def _fake_vision_ok(**kwargs):
    return (
        {
            "extraction_confidence": "high",
            "job_title": "Software Engineer",
            "company_name": "Acme Inc",
            "job_url_hint": "https://example.com/jobs/1",
            "extracted_job_text": "We are hiring for a backend role with Python experience. " * 4,
            "notes": "readable screenshot",
        },
        [],
    )


def test_verify_job_image_only_blocked_when_vision_empty(monkeypatch):
    monkeypatch.setattr(
        "backend.core.image_ingest.extract_job_fields_from_image_vision",
        lambda **kwargs: (None, [{"code": "VISION_DISABLED", "message": "disabled"}]),
    )
    r = orchestrator.verify_job(None, None, image_bytes=MINI_PNG, image_media_type="image/png")
    assert r["verdict"] == "VERIFY"
    assert r["ingestion"]["status"] == "insufficient"


def test_verify_job_image_only_proceeds_with_stubbed_vision(monkeypatch):
    monkeypatch.setattr("backend.core.image_ingest.extract_job_fields_from_image_vision", _fake_vision_ok)
    r = orchestrator.verify_job(None, None, image_bytes=MINI_PNG, image_media_type="image/png")
    assert r["verdict"] in ("APPLY", "VERIFY", "SKIP")
    assert r.get("ingestion", {}).get("status") == "ok"
    assert r["report_schema_version"] == "1.1.0"


def test_api_multipart_image_hits_verify(monkeypatch):
    monkeypatch.setattr("backend.core.image_ingest.extract_job_fields_from_image_vision", _fake_vision_ok)
    c = TestClient(app)
    files = {"job_image": ("one.png", MINI_PNG, "image/png")}
    res = c.post("/v1/verify", files=files)
    assert res.status_code == 200
    body = res.json()
    assert "verdict" in body
    assert body.get("ingestion", {}).get("status") == "ok"
