from backend.core.cache_key import build_public_cache_key
from backend.core.cache_payload import SharedCachePayload, serialize_payload, strip_tenant_fields
from backend.core.cache_store import InMemoryCache
from backend.core.normalization import normalize_job_input


def test_cache_hit_before_ttl_expires():
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    cache = InMemoryCache(now_fn=now)
    norm = normalize_job_input("https://example.com/j", None)
    key = build_public_cache_key(norm, "1", "1").materialized
    payload: SharedCachePayload = {
        "schema_version": "1",
        "pipeline_version": "1",
        "source_set_version": "1",
        "normalization_version": norm.normalization_version,
        "signals": [],
        "warnings": [],
        "coverage": "partial",
    }
    cache.set(key, serialize_payload(payload), ttl_seconds=1000)
    assert cache.get(key) is not None


def test_cache_miss_after_ttl():
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    cache = InMemoryCache(now_fn=now)
    norm = normalize_job_input("https://example.com/z", None)
    key = build_public_cache_key(norm, "1", "1").materialized
    payload: SharedCachePayload = {
        "schema_version": "1",
        "pipeline_version": "1",
        "source_set_version": "1",
        "normalization_version": norm.normalization_version,
        "signals": [],
        "warnings": [],
        "coverage": "none",
    }
    cache.set(key, serialize_payload(payload), ttl_seconds=10)
    clock["t"] = 11
    assert cache.get(key) is None


def test_strip_tenant_fields_before_serialize():
    dirty = {
        "schema_version": "1",
        "pipeline_version": "1",
        "source_set_version": "1",
        "normalization_version": "2.1.0",
        "signals": [{"id": "x", "tenant_id": "nope"}],
        "warnings": [],
        "coverage": "partial",
        "tenant_id": "t1",
    }
    clean = strip_tenant_fields(dirty)
    assert "tenant_id" not in clean
    assert "tenant_id" not in clean["signals"][0]
    serialize_payload(clean)  # must not raise
