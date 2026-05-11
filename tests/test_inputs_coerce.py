"""Deterministic job URL coercion (no LLM)."""

from backend.core.inputs import coerce_http_job_url, validate_verify_inputs


def test_coerce_schemeless_linkedin():
    assert coerce_http_job_url("linkedin.com/jobs/view/123") == "https://linkedin.com/jobs/view/123"


def test_coerce_protocol_relative():
    assert coerce_http_job_url("//example.com/job") == "https://example.com/job"


def test_coerce_angle_brackets():
    assert coerce_http_job_url("<https://example.com/a>") == "https://example.com/a"


def test_https_unchanged():
    assert coerce_http_job_url("https://Example.COM/path") == "https://Example.COM/path"


def test_validate_applies_coerce():
    url, text = validate_verify_inputs("indeed.com/viewjob?jk=abc", None, has_image=False)
    assert url == "https://indeed.com/viewjob?jk=abc"
