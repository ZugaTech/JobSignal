"""Employer name extraction must not treat job boards (Indeed, etc.) as the company."""

from __future__ import annotations

from backend.core.evidence import _resolve_official_careers_url
from backend.core.extraction import extract_entities
from backend.core.fetch_job_page import JobPageFetchOutcome
from backend.core.fetch_job_page import extract_job_text_hints_from_html
from backend.core.job_url_shortcuts import is_job_board_brand_label, is_known_job_platform_url, pick_employer_display_name
from backend.core.normalization import normalize_job_input
from backend.evidence.company_reviews import extract_company_name_hardened


def test_board_hostname_not_used_as_company_name():
    assert extract_company_name_hardened("https://ng.indeed.com/viewjob?jk=abc", None) is None


def test_brightermonday_hostname_not_used_as_company_name():
    url = "https://www.brightermonday.co.ke/jobs/software-engineer"
    assert is_known_job_platform_url(url)
    assert extract_company_name_hardened(url, None) is None


def test_board_url_still_allows_text_company_line():
    text = "Company: Acme Robotics Inc.\nSenior Software Engineer"
    assert extract_company_name_hardened("https://www.indeed.com/viewjob?jk=1", text) == "Acme Robotics Inc."


def test_extract_entities_skips_job_board_registrable_domain():
    norm = normalize_job_input("https://ng.indeed.com/viewjob?jk=abc", None)
    assert norm.registrable_domain == "indeed.com"
    ext = extract_entities(norm)
    assert ext.company_hint is None


def test_extract_entities_skips_brightermonday_board_domain():
    norm = normalize_job_input("https://www.brightermonday.co.ke/jobs/software-engineer", None)
    ext = extract_entities(norm)
    assert ext.company_hint is None


def test_extract_entities_keeps_real_employer_domain():
    norm = normalize_job_input("https://careers.example.com/jobs/123", None)
    assert norm.registrable_domain == "example.com"
    ext = extract_entities(norm)
    assert ext.company_hint == "Example"


def test_extract_entities_rejects_cctld_shortcut_domain_hint():
    norm = normalize_job_input("https://www.co.ke/jobs/software-engineer", None)
    ext = extract_entities(norm)
    assert ext.company_hint is None


def test_linkedin_og_site_name_not_emitted_as_company_hint():
    html = b"""
    <html><head>
    <meta property="og:site_name" content="LinkedIn" />
    <meta property="og:title" content="Full Stack Developer | hackajob | LinkedIn" />
    </head><body></body></html>
    """
    title, _desc, site_name, extracted, jsonld_name = extract_job_text_hints_from_html(html)
    assert site_name == "LinkedIn"
    assert extracted is not None
    assert "Company:" not in extracted
    assert jsonld_name is None
    assert "hackajob" in (title or "").lower() or "hackajob" in extracted.lower()


def test_regex_skips_company_linkedin_then_accepts_real_company():
    text = "Company: LinkedIn\nCompany: hackajob\nMore copy here."
    assert extract_company_name_hardened("https://www.linkedin.com/jobs/view/1", text) == "hackajob"


def test_brand_label_detection():
    assert is_job_board_brand_label("LinkedIn")
    assert is_job_board_brand_label("Indeed Jobs")
    assert not is_job_board_brand_label("hackajob")


def test_pick_employer_prefers_non_board():
    assert pick_employer_display_name("LinkedIn", "hackajob") == "hackajob"
    assert pick_employer_display_name("LinkedIn", None) is None
    assert pick_employer_display_name("Acme Ltd", "BrighterMonday") == "Acme Ltd"


def test_json_ld_jobposting_surfaces_in_extracted_text():
    html = b"""<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"GenAI Engineer","identifier":"340395",
"hiringOrganization":{"@type":"Organization","name":"Deloitte Consulting LLP"},
"jobLocation":{"@type":"Place","address":{"addressRegion":"VA","addressCountry":"US"}}}
</script></head><body><p>Extra body text for minimum length requirements here.</p></body></html>"""
    title, _desc, _site, extracted, jsonld_name = extract_job_text_hints_from_html(html, body_text_max_chars=4000)
    assert extracted
    assert jsonld_name == "Deloitte Consulting LLP"
    assert "340395" in extracted
    assert "GenAI" in extracted or "GenAI Engineer" in extracted
    assert "Deloitte" in extracted


def test_fetch_hints_meta_site_never_emits_company_prefix():
    html = b"""<html><head>
    <meta property="og:site_name" content="Acme Robotics" />
    <title>Software Engineer</title>
    </head><body></body></html>"""
    _t, _d, _s, extracted, jl = extract_job_text_hints_from_html(
        html,
        canonical_url="https://careers.acme-example.com/job/1",
    )
    assert extracted
    assert "Company:" not in extracted
    assert "Meta site_name: Acme Robotics" in extracted
    assert jl is None


def test_board_url_skips_meta_site_when_jsonld_names_employer():
    html = b"""<html><head>
    <meta property="og:site_name" content="RegionalJobsPortal" />
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Backend Engineer",
    "hiringOrganization":{"@type":"Organization","name":"True Employer LLC"}}
    </script></head><body><p>More body.</p></body></html>"""
    _t, _d, site, extracted, jl = extract_job_text_hints_from_html(
        html,
        canonical_url="https://www.indeed.com/viewjob?jk=abc",
    )
    assert jl == "True Employer LLC"
    assert extracted
    assert "Company:" not in extracted
    assert "Meta site_name" not in extracted
    assert site == "RegionalJobsPortal"


def test_board_url_does_not_self_promote_as_official_careers_page():
    norm = normalize_job_input("https://www.brightermonday.co.ke/jobs/software-engineer", None)
    ext = extract_entities(norm)
    fx = JobPageFetchOutcome(
        attempted=True,
        employer_page_urls=("https://www.brightermonday.co.ke/listings/software-engineer",),
    )

    official_url, reason = _resolve_official_careers_url(norm, ext, None, fx)

    assert official_url is None
    assert reason == ""
