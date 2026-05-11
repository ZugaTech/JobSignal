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

# Registrable domains (host → naive registrable) that must never be treated as the hiring employer.
_JOB_BOARD_REGISTRABLE_DOMAINS = frozenset(
    {
        "indeed.com",
        "linkedin.com",
        "glassdoor.com",
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "workday.com",
        "ziprecruiter.com",
        "monster.com",
        "careerbuilder.com",
        "simplyhired.com",
        "dice.com",
        "wellfound.com",
        "angel.co",
        "jobvite.com",
        "smartrecruiters.com",
        "ashbyhq.com",
        "recruitee.com",
        "bamboohr.com",
        "icims.com",
        "taleo.net",
        "successfactors.com",
        "hired.com",
        "remoteok.com",
        "weworkremotely.com",
        "ycombinator.com",
        "seek.com.au",
        "reed.co.uk",
        "brightermonday.co.ke",
        "brightermonday.co.ug",
        "brightermonday.co.tz",
        "brightermonday.com",
        "jobberman.com",
        "bayt.com",
        "naukri.com",
        "foundit.in",
        "foundit.com",
        "gulftalent.com",
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
        r"(^|\.)brightermonday\.",
        r"(^|\.)jobberman\.",
        r"seek\.com\.au",
        r"(^|\.)bayt\.com",
        r"(^|\.)naukri\.com",
        r"(^|\.)foundit\.(in|com)",
        r"(^|\.)gulftalent\.com",
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


def is_job_board_registrable_domain(domain: Optional[str]) -> bool:
    """True when naive registrable domain is a major job board / ATS aggregate (not an employer)."""

    if not domain:
        return False
    return domain.lower().strip(".") in _JOB_BOARD_REGISTRABLE_DOMAINS


# Display names from og:site_name / UI that must never be treated as the hiring employer.
_JOB_BOARD_BRAND_LABELS = frozenset(
    {
        "linkedin",
        "linkedin corporation",
        "indeed",
        "glassdoor",
        "greenhouse",
        "lever",
        "workday",
        "ziprecruiter",
        "monster",
        "careerbuilder",
        "simplyhired",
        "dice",
        "wellfound",
        "angel list",
        "angellist",
        "remote ok",
        "remoteok",
        "y combinator",
        "seek",
        "reed",
        "icims",
        "bamboohr",
        "smartrecruiters",
        "ashby",
        "recruitee",
        "jobvite",
        "taleo",
        "successfactors",
        "hired",
        "monster worldwide",
        "myworkdayjobs",
        "brighter monday",
        "brightermonday",
        "brighter monday kenya",
        "brightermonday kenya",
        "jobberman",
        "bayt",
        "naukri",
        "foundit",
        "gulf talent",
        "gulftalent",
    }
)


def is_job_board_brand_label(label: Optional[str]) -> bool:
    """True when text is a job-board / ATS brand, not an employer (e.g. og:site_name \"LinkedIn\")."""

    if not label:
        return False
    s = re.sub(r"[^\w\s]+", " ", label.strip().lower())
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return False
    if s in _JOB_BOARD_BRAND_LABELS:
        return True
    first = s.split()[0] if s.split() else ""
    if first in _JOB_BOARD_BRAND_LABELS:
        return True
    return False


def pick_employer_display_name(*candidates: Optional[str]) -> Optional[str]:
    """First candidate that looks like a real employer name (skips job-board brands)."""

    for c in candidates:
        if not c:
            continue
        t = c.strip()
        if not t or is_job_board_brand_label(t):
            continue
        return t
    return None


def is_scam_domain_url(url: str) -> bool:
    dom = registrable_domain_from_url(url)
    if not dom:
        return False
    return dom.lower() in _SCAM_REGISTRABLE_DOMAINS
