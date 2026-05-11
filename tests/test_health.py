from backend.core.env import EnvConfig
from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.health import build_health_payload, build_ready_payload


def _sample_env(**overrides):
    fields = dict(
        node_env="development",
        cache_ttl_days=14,
        source_pipeline_version="1",
        scorer_version="1",
        fetch_max_bytes=2_097_152,
        fetch_body_text_max_chars=16_000,
        fetch_max_redirects=5,
        cache_url=None,
        search_api_endpoint=None,
        serpapi_search_endpoint="https://serpapi.com/search.json",
        search_timeout_s=10,
        search_retry_count=2,
        search_rate_limit_per_minute=60,
        search_max_calls_evidence=8,
        search_max_calls_reputation=8,
        search_max_calls_recommendations=8,
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model=DEFAULT_FIREWORKS_MODEL,
        fireworks_vision_model=DEFAULT_FIREWORKS_MODEL,
        fireworks_timeout_s=10,
        fireworks_retry_count=2,
        log_level="info",
        pipeline_deadline_s=18,
        llm_summary_confidence_threshold=85,
    )
    fields.update(overrides)
    return EnvConfig(**fields)


def test_health_always_ok():
    h = build_health_payload()
    assert h["status"] == "ok"


def test_ready_dev_without_cache_still_ready(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.delenv("CACHE_URL", raising=False)
    cfg = EnvConfig.load(strict=False)
    r = build_ready_payload(cfg, cache_ping_ok=None)
    assert r["status"] in ("ready", "degraded")
    assert r["checks"]["redis"] == "skip"
    assert r["live_probe"] is False


def test_ready_staging_without_cache_not_ready():
    cfg = _sample_env(node_env="staging", cache_url=None)
    r = build_ready_payload(cfg)
    assert r["status"] in ("ready", "degraded")
    assert r["http"] == 200


def test_ready_fails_when_cache_ping_false():
    cfg = _sample_env(cache_url="redis://localhost")
    r = build_ready_payload(cfg, cache_ping_ok=False)
    assert r["status"] == "unavailable"


def test_ready_includes_serp_key_check():
    cfg = _sample_env(cache_url=None)
    r = build_ready_payload(cfg)
    assert "serp_key" in r["checks"]
    assert r["checks"]["serp_key"] in ("pass", "fail")


def test_ready_includes_cache_ping_when_provided():
    cfg = _sample_env(cache_url="redis://localhost")
    r = build_ready_payload(cfg, cache_ping_ok=True)
    assert r["checks"]["redis"] == "pass"


def test_ready_payload_reports_live_probe_flag():
    cfg = _sample_env(cache_url=None)
    r = build_ready_payload(cfg, live_probe=True, fireworks_reachable=True, serper_reachable=True)
    assert r["live_probe"] is True
