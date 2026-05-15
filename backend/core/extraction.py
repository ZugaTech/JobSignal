"""Conservative company / title / location hints from URL + normalized text.

Sprint 2 is heuristic-only: empty fields are common and **never** back-filled
with invented names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from backend.core.job_url_shortcuts import (
    is_job_board_brand_label,
    is_job_board_registrable_domain,
    is_known_job_platform_url,
)
from backend.core.normalization import NormalizationResult, registrable_domain_naive
from backend.core.employer_llm_noise import employer_label_is_llm_noise


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    company_hint: Optional[str]
    title_hint: Optional[str]
    location_hint: Optional[str]
    posting_url_hint: Optional[str]
    date_hint: Optional[str]
    recruiter_name_hint: Optional[str]


_TITLE_PREFIX = re.compile(r"^\s*(title|job title|position)\s*:\s*", re.I)
# After NFKC/collapse, LLM prefaces and real titles often land in one line; split only when the
# whole line is monologue-like so we do not chop legitimate "Dr. …" titles on every period.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_LOCATIONISH = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})\b"  # City, ST
)
_DATE_REGEX = re.compile(r"\b(posted|published)\s+on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\b", re.I)
_RECRUITER_REGEX = re.compile(r"(?:recruiter|hiring manager)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.I)
_COMPANY_LINE = re.compile(r"\b(company|employer|organization)\s*:\s*([^\n\r|•]{2,120})", re.I)
_WEAK_DOMAIN_LABELS = {
    "www",
    "careers",
    "jobs",
    "job",
    "apply",
    "app",
    "co",
    "com",
    "org",
    "net",
    "ac",
    "go",
    "gov",
}


def _company_from_domain(domain: Optional[str]) -> Optional[str]:
    if not domain:
        return None
    labels = [p for p in domain.lower().strip(".").split(".") if p]
    if not labels:
        return None
    label = labels[0]
    if label in _WEAK_DOMAIN_LABELS or len(label) < 3:
        return None
    return label.replace("-", " ").title() or None


def _first_meaningful_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 3]
    fragments: list[str] = []
    if len(lines) <= 1:
        one = (lines[0] if lines else text.strip())
        if not one:
            return None
        stripped = _TITLE_PREFIX.sub("", one).strip()
        if employer_label_is_llm_noise(stripped):
            fragments = [p.strip() for p in _SENTENCE_BOUNDARY.split(one) if p.strip()]
        else:
            fragments = [one]
    else:
        fragments = lines

    for raw in fragments:
        s = _TITLE_PREFIX.sub("", raw).strip()
        if len(s) < 3:
            continue
        if employer_label_is_llm_noise(s):
            continue
        return s[:256] or None
    return None


def extract_entities(norm: NormalizationResult) -> ExtractionResult:
    company = None
    cu = (norm.canonical_url or "").strip()
    board_like_url = cu.startswith(("http://", "https://")) and is_known_job_platform_url(cu)

    if (
        norm.registrable_domain
        and not is_job_board_registrable_domain(norm.registrable_domain)
        and not board_like_url
    ):
        company = _company_from_domain(norm.registrable_domain)
    if not company and norm.canonical_url:
        host = urlparse(norm.canonical_url).hostname or ""
        reg = registrable_domain_naive(host) if host else None
        if reg and not is_job_board_registrable_domain(reg) and not board_like_url:
            company = _company_from_domain(host)

    title = _first_meaningful_line(norm.description_text)
    loc = None
    date_hint = None
    rec_hint = None
    
    if norm.description_text:
        m_company = _COMPANY_LINE.search(norm.description_text)
        if m_company:
            maybe_company = m_company.group(2).strip(" -–—:\t")
            if maybe_company and not is_job_board_brand_label(maybe_company):
                company = maybe_company[:120]

        m_loc = _LOCATIONISH.search(norm.description_text)
        if m_loc:
            loc = m_loc.group(1)
            
        m_date = _DATE_REGEX.search(norm.description_text)
        if m_date:
            date_hint = m_date.group(2)
            
        m_rec = _RECRUITER_REGEX.search(norm.description_text)
        if m_rec:
            rec_hint = m_rec.group(1)

    return ExtractionResult(
        company_hint=company,
        title_hint=title,
        location_hint=loc,
        posting_url_hint=norm.canonical_url,
        date_hint=date_hint,
        recruiter_name_hint=rec_hint,
    )
