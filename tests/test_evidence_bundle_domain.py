"""Careers domain alignment uses resolved official URL + page-fetch extraction."""

from urllib.parse import urlparse

from backend.core.evidence import build_evidence_bundle
from backend.core.extraction import ExtractionResult
from backend.core.fetch_job_page import JobPageFetchOutcome, extract_employer_urls_from_html
from backend.core.normalization import NORMALIZATION_VERSION, NormalizationResult, registrable_domain_naive


def _empty_serp() -> dict:
    return {
        "careers": ([], "unverified", None),
        "board": ([], "unverified", None),
        "rep": ([], "unverified", None),
        "linkedin": ([], "unverified", None),
        "registry": ([], "unverified", None),
        "duplicates": ([], "unverified", None),
    }


def _norm(url: str) -> NormalizationResult:
    host = urlparse(url).hostname or ""
    return NormalizationResult(
        normalization_version=NORMALIZATION_VERSION,
        canonical_url=url,
        canonical_url_sha256="test",
        description_text=None,
        description_full_sha256=None,
        registrable_domain=registrable_domain_naive(host),
    )


def _domain_signal(bundle):
    return next(s for s in bundle.signals if s["id"] == "careers_domain_match")


def test_domain_match_passes_when_fetch_surfaces_same_registrable_careers_url():
    norm = _norm("https://jobs.acme-example.com/positions/1")
    ext = ExtractionResult("Acme Example", None, None, None, None, None)
    fx = JobPageFetchOutcome(
        attempted=True,
        employer_page_urls=("https://careers.acme-example.com/openings",),
    )
    bundle = build_evidence_bundle(norm, ext, _empty_serp(), page_fetch=fx)
    sig = _domain_signal(bundle)
    assert sig["status"] == "pass"
    assert bundle.official_url == "https://careers.acme-example.com/openings"


def test_domain_match_fails_when_official_differs_from_posting_registrable():
    norm = _norm("https://www.indeed.com/viewjob?jk=abc")
    ext = ExtractionResult("Acme Example", "Engineer", None, None, None, None)
    serp = _empty_serp()
    serp["careers"] = (
        [{"link": "https://jobs.acme-example.com/", "title": "Careers", "snippet": ""}],
        "verified",
        None,
    )
    bundle = build_evidence_bundle(norm, ext, serp, page_fetch=None)
    sig = _domain_signal(bundle)
    assert sig["status"] == "fail"
    assert bundle.official_url == "https://jobs.acme-example.com/"


def test_extract_employer_urls_canonical_relative():
    html = b'<html><head><link rel="canonical" href="/careers/software-engineer"/></head></html>'
    urls = extract_employer_urls_from_html(html, "https://jobs.bigco.com/job/99")
    assert "https://jobs.bigco.com/careers/software-engineer" in urls


def test_posting_duplication_signal_unknown_when_search_returns_no_domains():
    norm = _norm("https://apply.example.com/job/1")
    ext = ExtractionResult("Example", "Engineer", None, None, None, None)
    serp = _empty_serp()
    serp["duplicates"] = ([], "verified", None)
    bundle = build_evidence_bundle(norm, ext, serp)
    dup = next(s for s in bundle.signals if s["id"] == "posting_duplication_signal")
    assert dup["status"] == "unknown"
    assert dup["strength"] == "low"
