"""Fast-path URL checks before expensive evidence gathering."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from backend.core.normalization import registrable_domain_naive

# Hardcoded high-risk recruiter scam patterns (extend carefully).
_SCAM_REGISTRABLE_DOMAINS = frozenset(
    {
        "job-phishing-demo.invalid",
        "fake-recruiter-chain.invalid",
    }
)

_KNOWN_JOB_BOARD_NETLOCS = tuple(
    re.compile(p, re.I)
    for p in (
        r"linkedin\.com",
        r"(^|\.)indeed\.com",
        r"glassdoor\.com",
        r"greenhouse\.io",
        r"lever\.co",
        r"myworkdayjobs\.com",
        r"workday\.com",
    )
)


def registrable_domain_from_url(url: str) -> Optional[str]:
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
        if not host:
            return None
        return registrable_domain_naive(host)
    except Exception:  # noqa: BLE001
        return None


def is_known_job_platform_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(p.search(host) for p in _KNOWN_JOB_BOARD_NETLOCS)


def is_scam_domain_url(url: str) -> bool:
    dom = registrable_domain_from_url(url)
    if not dom:
        return False
    return dom.lower() in _SCAM_REGISTRABLE_DOMAINS
