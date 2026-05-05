import pytest

from backend.core.cache_payload import assert_shared_cache_json_safe, strip_tenant_fields


def test_nested_tenant_field_removed():
    dirty = {
        "schema_version": "1",
        "pipeline_version": "1",
        "source_set_version": "1",
        "normalization_version": "2.0.0",
        "signals": [{"id": "x", "nested": {"tenant_id": "leak"}}],
        "warnings": [],
        "coverage": "partial",
    }
    clean = strip_tenant_fields(dirty)
    assert "tenant_id" not in str(clean)


def test_assert_shared_rejects_password_before_strip():
    bad = {
        "schema_version": "1",
        "pipeline_version": "1",
        "source_set_version": "1",
        "normalization_version": "2.0.0",
        "signals": [],
        "warnings": [],
        "coverage": "partial",
        "password": "nope",
    }
    with pytest.raises(ValueError):
        assert_shared_cache_json_safe(bad)
