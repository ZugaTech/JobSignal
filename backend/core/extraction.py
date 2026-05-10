"""Conservative company / title / location hints from URL + normalized text.

Sprint 2 is heuristic-only: empty fields are common and **never** back-filled
with invented names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from backend.core.normalization import NormalizationResult


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    company_hint: Optional[str]
    title_hint: Optional[str]
    location_hint: Optional[str]
    posting_url_hint: Optional[str]
    date_hint: Optional[str]
    recruiter_name_hint: Optional[str]


_TITLE_PREFIX = re.compile(r"^\s*(title|job title|position)\s*:\s*", re.I)
_LOCATIONISH = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})\b"  # City, ST
)
_DATE_REGEX = re.compile(r"\b(posted|published)\s+on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\b", re.I)
_RECRUITER_REGEX = re.compile(r"(?:recruiter|hiring manager)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.I)
_COMPANY_LINE = re.compile(r"\b(company|employer|organization)\s*:\s*([^\n\r|•]{2,120})", re.I)


def _company_from_domain(domain: Optional[str]) -> Optional[str]:
    if not domain:
        return None
    label = domain.split(".")[0]
    if label in ("www", "careers", "jobs"):
        return None
    return label.replace("-", " ").title() or None


def _first_meaningful_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip()
        if len(s) < 3:
            continue
        s = _TITLE_PREFIX.sub("", s).strip()
        return s[:256] or None
    return None


def extract_entities(norm: NormalizationResult) -> ExtractionResult:
    company = _company_from_domain(norm.registrable_domain)
    if not company and norm.canonical_url:
        host = urlparse(norm.canonical_url).hostname or ""
        company = _company_from_domain(host)

    title = _first_meaningful_line(norm.description_text)
    loc = None
    date_hint = None
    rec_hint = None
    
    if norm.description_text:
        m_company = _COMPANY_LINE.search(norm.description_text)
        if m_company:
            maybe_company = m_company.group(2).strip(" -–—:\t")
            if maybe_company:
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
