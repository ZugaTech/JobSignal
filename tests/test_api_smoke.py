from fastapi.testclient import TestClient

from backend.api.main import app


def test_health_ok():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_returns_json():
    c = TestClient(app)
    r = c.get("/ready")
    assert r.status_code in (200, 503)
    assert "status" in r.json()


def test_verify_rejects_empty_payload():
    c = TestClient(app)
    r = c.post("/v1/verify", json={"job_url": None, "job_description": None})
    assert r.status_code == 400

