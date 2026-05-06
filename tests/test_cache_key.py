from backend.core.cache_key import build_public_cache_key
from backend.core.normalization import normalize_job_input


def test_same_input_same_key():
    n1 = normalize_job_input("https://example.com/job?utm_source=1", "Hello")
    n2 = normalize_job_input("https://example.com/job", "Hello")
    k1 = build_public_cache_key(n1, pipeline_version="1", source_set_version="a")
    k2 = build_public_cache_key(n2, pipeline_version="1", source_set_version="a")
    assert k1.materialized == k2.materialized


def test_version_bump_changes_key():
    n = normalize_job_input("https://example.com/", None)
    k1 = build_public_cache_key(n, pipeline_version="1", source_set_version="a")
    k2 = build_public_cache_key(n, pipeline_version="2", source_set_version="a")
    assert k1.materialized != k2.materialized


def test_fingerprint_includes_text_when_url_missing():
    n = normalize_job_input(None, "Only pasted body")
    key = build_public_cache_key(n, "1", "a")
    assert "t:" in key.materialized
    assert "u:" not in key.materialized


def test_image_sha_changes_materialized_key():
    n = normalize_job_input("https://example.com/job", "Hello")
    k0 = build_public_cache_key(n, "1", "a", image_bytes_sha256=None)
    k1 = build_public_cache_key(n, "1", "a", image_bytes_sha256="abc")
    assert k0.materialized != k1.materialized
    assert "img:abc" in k1.materialized


def test_fetch_profile_live_changes_key():
    n = normalize_job_input("https://example.com/job", "Hello")
    k0 = build_public_cache_key(n, "1", "a", fetch_profile="off")
    k1 = build_public_cache_key(n, "1", "a", fetch_profile="live")
    assert k0.materialized != k1.materialized
    assert "fetch:live" in k1.materialized
