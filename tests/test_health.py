from backend.core.env import EnvConfig
from backend.core.health import build_health_payload, build_ready_payload


def test_health_always_ok():
    h = build_health_payload()
    assert h["status"] == "ok"


def test_ready_dev_without_cache_still_ready(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.delenv("CACHE_URL", raising=False)
    cfg = EnvConfig.load(strict=False)
    r = build_ready_payload(cfg, cache_ping_ok=None)
    assert r["status"] == "ready"
    assert r["checks"]["search_configured"] in (True, False)
    assert r["checks"]["recommendations_default_enabled"] in (True, False)
    assert r["checks"]["job_fetch_enabled"] in (True, False)
    assert r["checks"]["image_verify_enabled"] in (True, False)
    assert r["checks"]["llm_signals_enabled"] in (True, False)
    assert r["checks"]["fireworks_key_present"] in (True, False)


def test_ready_staging_without_cache_not_ready():
    cfg = EnvConfig(
        node_env="staging",
        cache_ttl_days=14,
        source_pipeline_version="1",
        scorer_version="1",
        fetch_max_bytes=2_097_152,
        fetch_max_redirects=5,
        cache_url=None,
        search_api_endpoint=None,
        log_level="info",
    )
    r = build_ready_payload(cfg)
    assert r["status"] == "not_ready"
    assert r["http"] == 503


def test_ready_fails_when_cache_ping_false():
    cfg = EnvConfig(
        node_env="development",
        cache_ttl_days=14,
        source_pipeline_version="1",
        scorer_version="1",
        fetch_max_bytes=2_097_152,
        fetch_max_redirects=5,
        cache_url="redis://localhost",
        search_api_endpoint=None,
        log_level="info",
    )
    r = build_ready_payload(cfg, cache_ping_ok=False)
    assert r["status"] == "not_ready"


def test_ready_includes_cache_ping_when_provided():
    cfg = EnvConfig(
        node_env="development",
        cache_ttl_days=14,
        source_pipeline_version="1",
        scorer_version="1",
        fetch_max_bytes=2_097_152,
        fetch_max_redirects=5,
        cache_url="redis://localhost",
        search_api_endpoint=None,
        log_level="info",
    )
    r = build_ready_payload(cfg, cache_ping_ok=True)
    assert r["checks"]["cache_ping"] == "ok"
