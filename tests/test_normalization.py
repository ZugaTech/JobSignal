import pytest

from backend.core.normalization import (
    NORMALIZATION_VERSION,
    normalize_job_input,
    normalize_job_url,
    normalize_job_text,
)


def test_url_strips_utm_and_lowercases_host():
    raw = "HTTPS://Example.COM/path?utm_source=x&utm_medium=email&gclid=1&ok=1"
    canon, h = normalize_job_url(raw)
    assert canon == "https://example.com/path?ok=1"
    assert h is not None
    canon2, h2 = normalize_job_url("https://example.com/path?ok=1")
    assert h == h2


def test_url_invalid_scheme_returns_none():
    assert normalize_job_url("ftp://example.com") == (None, None)


def test_text_nfkc_and_whitespace():
    raw = "  caf\u00e9  \n  engineer  "
    text, full_hash = normalize_job_text(raw)
    assert text == "café engineer"
    assert full_hash is not None


def test_normalize_job_input_composite_domain():
    n = normalize_job_input("https://careers.example.com/jobs/1", "Title: Widget")
    assert n.normalization_version == NORMALIZATION_VERSION
    assert n.canonical_url is not None
    assert n.canonical_url_sha256 is not None
    assert n.description_full_sha256 is not None
    assert n.registrable_domain == "example.com"
