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


_TITLE_PREFIX = re.compile(r"^\s*(title|job title|position)\s*:\s*", re.I)
_LOCATIONISH = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})\b"  # City, ST
)


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
    if norm.description_text:
        m = _LOCATIONISH.search(norm.description_text)
        if m:
            loc = m.group(1)

    return ExtractionResult(
        company_hint=company,
        title_hint=title,
        location_hint=loc,
    )
