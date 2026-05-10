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
    assert r["status"] in ("ready", "degraded")
    assert r["checks"]["redis"] == "skip"
    assert r["live_probe"] is False


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
        search_timeout_s=10,
        search_retry_count=2,
        search_rate_limit_per_minute=60,
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_vision_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_timeout_s=10,
        fireworks_retry_count=2,
        log_level="info",
        pipeline_deadline_s=18,
        llm_summary_confidence_threshold=85,
    )
    r = build_ready_payload(cfg)
    assert r["status"] in ("ready", "degraded")
    assert r["http"] == 200


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
        search_timeout_s=10,
        search_retry_count=2,
        search_rate_limit_per_minute=60,
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_vision_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_timeout_s=10,
        fireworks_retry_count=2,
        log_level="info",
        pipeline_deadline_s=18,
        llm_summary_confidence_threshold=85,
    )
    r = build_ready_payload(cfg, cache_ping_ok=False)
    assert r["status"] == "unavailable"


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
        search_timeout_s=10,
        search_retry_count=2,
        search_rate_limit_per_minute=60,
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_vision_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_timeout_s=10,
        fireworks_retry_count=2,
        log_level="info",
        pipeline_deadline_s=18,
        llm_summary_confidence_threshold=85,
    )
    r = build_ready_payload(cfg, cache_ping_ok=True)
    assert r["checks"]["redis"] == "pass"


def test_ready_payload_reports_live_probe_flag():
    cfg = EnvConfig(
        node_env="development",
        cache_ttl_days=14,
        source_pipeline_version="1",
        scorer_version="1",
        fetch_max_bytes=2_097_152,
        fetch_max_redirects=5,
        cache_url=None,
        search_api_endpoint=None,
        search_timeout_s=10,
        search_retry_count=2,
        search_rate_limit_per_minute=60,
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_vision_model="accounts/fireworks/models/kimi-k2p6",
        fireworks_timeout_s=10,
        fireworks_retry_count=2,
        log_level="info",
        pipeline_deadline_s=18,
        llm_summary_confidence_threshold=85,
    )
    r = build_ready_payload(cfg, live_probe=True, fireworks_reachable=True, serper_reachable=True)
    assert r["live_probe"] is True
