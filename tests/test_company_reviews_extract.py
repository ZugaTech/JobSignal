"""Employer name extraction must not treat job boards (Indeed, etc.) as the company."""

from __future__ import annotations

from backend.core.extraction import extract_entities
from backend.core.fetch_job_page import extract_job_text_hints_from_html
from backend.core.job_url_shortcuts import is_job_board_brand_label, pick_employer_display_name
from backend.core.normalization import normalize_job_input
from backend.evidence.company_reviews import extract_company_name_hardened


def test_board_hostname_not_used_as_company_name():
    assert extract_company_name_hardened("https://ng.indeed.com/viewjob?jk=abc", None) is None


def test_board_url_still_allows_text_company_line():
    text = "Company: Acme Robotics Inc.\nSenior Software Engineer"
    assert extract_company_name_hardened("https://www.indeed.com/viewjob?jk=1", text) == "Acme Robotics Inc."


def test_extract_entities_skips_job_board_registrable_domain():
    norm = normalize_job_input("https://ng.indeed.com/viewjob?jk=abc", None)
    assert norm.registrable_domain == "indeed.com"
    ext = extract_entities(norm)
    assert ext.company_hint is None


def test_extract_entities_keeps_real_employer_domain():
    norm = normalize_job_input("https://careers.example.com/jobs/123", None)
    assert norm.registrable_domain == "example.com"
    ext = extract_entities(norm)
    assert ext.company_hint == "Example"


def test_linkedin_og_site_name_not_emitted_as_company_hint():
    html = b"""
    <html><head>
    <meta property="og:site_name" content="LinkedIn" />
    <meta property="og:title" content="Full Stack Developer | hackajob | LinkedIn" />
    </head><body></body></html>
    """
    title, desc, site_name, extracted = extract_job_text_hints_from_html(html)
    assert site_name == "LinkedIn"
    assert extracted is not None
    assert "Company: LinkedIn" not in extracted
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


def test_json_ld_jobposting_surfaces_in_extracted_text():
    html = b"""<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"GenAI Engineer","identifier":"340395",
"hiringOrganization":{"@type":"Organization","name":"Deloitte Consulting LLP"},
"jobLocation":{"@type":"Place","address":{"addressRegion":"VA","addressCountry":"US"}}}
</script></head><body><p>Extra body text for minimum length requirements here.</p></body></html>"""
    title, desc, site, extracted = extract_job_text_hints_from_html(html, body_text_max_chars=4000)
    assert extracted
    assert "340395" in extracted
    assert "GenAI" in extracted or "GenAI Engineer" in extracted
    assert "Deloitte" in extracted
