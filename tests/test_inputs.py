import pytest

from backend.core.inputs import InputValidationError, validate_raw_job_inputs, validate_verify_inputs


def test_requires_some_input():
    with pytest.raises(InputValidationError) as ei:
        validate_raw_job_inputs(None, "   ")
    assert ei.value.code == "EMPTY"


def test_rejects_non_http_scheme():
    with pytest.raises(InputValidationError) as ei:
        validate_raw_job_inputs("ftp://example.com/job", None)
    assert ei.value.code == "URL_SCHEME"


def test_rejects_oversized_text():
    with pytest.raises(InputValidationError) as ei:
        validate_raw_job_inputs(None, "x" * 100_001)
    assert ei.value.code == "TEXT_TOO_LONG"


def test_rejects_nul_in_text():
    with pytest.raises(InputValidationError) as ei:
        validate_raw_job_inputs(None, "hello\x00world")
    assert ei.value.code == "TEXT_NUL"


def test_accepts_url_and_text():
    u, t = validate_raw_job_inputs(" https://example.com/a ", " Role ")
    assert u == "https://example.com/a"
    assert t == "Role"


def test_image_only_allows_empty_url_and_text():
    u, t = validate_verify_inputs(None, None, has_image=True)
    assert u is None and t is None
