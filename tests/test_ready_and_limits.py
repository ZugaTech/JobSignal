from fastapi.testclient import TestClient

import backend.api.main as main_mod
from backend.api.main import create_app


def test_ready_unavailable_when_redis_configured_but_unreachable(monkeypatch):
    monkeypatch.setenv("CACHE_URL", "redis://localhost:6379/0")
    import backend.api.routes.health as health_route

    health_route.cache_ping = lambda _url: False  # type: ignore[assignment]
    c = TestClient(create_app())
    r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable"


def test_ready_degraded_when_no_provider_keys(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("RECOMMENDATIONS_ENABLED", "0")
    import backend.api.routes.health as health_route

    health_route.cache_ping = lambda _url: True  # type: ignore[assignment]
    c = TestClient(create_app())
    r = c.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["llm_key"] == "fail"
    assert body["live_probe"] is False


def test_ready_skips_provider_probe_when_disabled(monkeypatch):
    monkeypatch.setenv("PROBE_PROVIDERS_ON_READY", "0")
    import backend.api.routes.health as health_route

    health_route.cache_ping = lambda _url: True  # type: ignore[assignment]

    def _boom():
        raise AssertionError("provider probe should not run")

    health_route.fireworks_api_reachable = _boom  # type: ignore[assignment]
    health_route.serper_api_reachable = _boom  # type: ignore[assignment]

    c = TestClient(create_app())
    r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["live_probe"] is False


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    main_mod.APP_CFG.values["RATE_LIMIT_REQUESTS_PER_MINUTE"] = 1
    main_mod.APP_CFG.values["RATE_LIMIT_BURST"] = 0
    c = TestClient(create_app())
    payload = {"job_url": "https://example.com/job/1", "job_description": None}
    got_429 = None
    for _ in range(6):
        res = c.post("/v1/verify", json=payload, headers={"x-forwarded-for": "203.0.113.9"})
        if res.status_code == 429:
            got_429 = res
            break
    assert got_429 is not None
    assert "Retry-After" in got_429.headers
