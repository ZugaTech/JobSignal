"""Employer display names must never surface model monologue as the company string."""

from backend.evidence.company_reviews import (
    _employer_label_is_llm_noise,
    _safe_reputation_company_label,
    resolve_reputation_query_name,
)


def test_noise_label_detected():
    assert _employer_label_is_llm_noise("Let me look at the provided text carefully") is True
    assert _employer_label_is_llm_noise("Acme Corp") is False


def test_resolve_falls_back_to_domain_when_name_is_noise():
    url = "https://www.brightermonday.co.ke/listings/some-job-123"
    out = resolve_reputation_query_name("Let me look at the provided text carefully", url)
    assert out is None


def test_safe_label_never_injects_noise():
    u = "https://careers.example.co.ke/jobs/1"
    assert _safe_reputation_company_label("Let me analyze the input", u) == "Example"


def test_safe_label_this_employer_when_only_board():
    u = "https://www.brightermonday.co.ke/listings/x"
    assert _safe_reputation_company_label("Let me look at the provided text carefully", u) == "this employer"
