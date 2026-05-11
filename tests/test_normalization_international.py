"""Registrable-domain extraction for common international suffixes (no bundled PSL file)."""

from backend.core.normalization import NORMALIZATION_VERSION, normalize_job_input, registrable_domain_naive


def test_version_bumped_with_suffix_table():
    assert NORMALIZATION_VERSION == "2.1.0"


def test_co_uk_etld_plus_one():
    assert registrable_domain_naive("careers.acme.co.uk") == "acme.co.uk"
    assert registrable_domain_naive("jobs.bigco.co.uk") == "bigco.co.uk"


def test_com_ng_etld_plus_one():
    assert registrable_domain_naive("apply.startup.com.ng") == "startup.com.ng"


def test_com_au_etld_plus_one():
    assert registrable_domain_naive("seek.company.com.au") == "company.com.au"


def test_simple_com_unchanged():
    assert registrable_domain_naive("jobs.example.com") == "example.com"


def test_normalize_job_input_uses_suffix_for_registrable_field():
    n = normalize_job_input("https://roles.widget.co.uk/job/1", None)
    assert n.registrable_domain == "widget.co.uk"
