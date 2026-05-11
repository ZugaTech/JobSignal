"""Fast-path URL checks before expensive evidence gathering."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

_WEAK_EMPLOYER_LABELS = frozenset(
    {
        "apply",
        "career",
        "careers",
        "hiring",
        "job",
        "jobs",
        "recruiter",
        "recruitment",
        "vacancy",
        "vacancies",
    }
)

_ROLE_WORDS = re.compile(
    r"\b(engineer|developer|manager|analyst|designer|director|specialist|consultant|intern|remote|"
    r"full\s*time|part\s*time|contract|salary|apply|job|role|position)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class EmployerIdentityResolution:
    name: Optional[str]
    confirmed: bool
    confidence: str
    reason: str


def _clean_employer_candidate(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    t = re.sub(r"\s+", " ", label.strip(" \t\r\n:-–—|"))
    if not t or len(t) < 2 or len(t) > 120:
        return None
    if is_job_board_brand_label(t):
        return None
    low = re.sub(r"[^\w\s]+", " ", t.lower())
    low = re.sub(r"\s+", " ", low).strip()
    if low in _WEAK_EMPLOYER_LABELS:
        return None
    if _ROLE_WORDS.search(low) and not re.search(r"\b(inc|llc|ltd|limited|corp|corporation|company|group|plc)\b", low):
        return None
    return t


def _employer_key(label: str) -> str:
    s = re.sub(r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|company|co|plc|group)\b", "", label.lower())
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


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
        t = _clean_employer_candidate(c)
        if not t:
            continue
        return t
    return None


def resolve_employer_identity(
    *,
    is_job_board_url: bool,
    url_domain_candidate: Optional[str] = None,
    structured_candidate: Optional[str] = None,
    hardened_candidate: Optional[str] = None,
    heuristic_candidate: Optional[str] = None,
) -> EmployerIdentityResolution:
    """Resolve employer identity conservatively before reputation lookup.

    Job-board pages often expose board names, page chrome, or title fragments. For those URLs,
    require either a structured company field or corroborating employer candidates.
    """

    cleaned: list[tuple[str, str, str]] = []
    for source, cand in (
        ("structured", structured_candidate),
        ("url_domain", url_domain_candidate),
        ("hardened", hardened_candidate),
        ("heuristic", heuristic_candidate),
    ):
        t = _clean_employer_candidate(cand)
        if not t:
            continue
        key = _employer_key(t)
        if len(key) < 3:
            continue
        cleaned.append((source, t, key))

    if not cleaned:
        return EmployerIdentityResolution(None, False, "none", "No usable employer candidate.")

    # Employer-owned domains are specific enough to identify the employer unless contradicted by
    # a structured company field.
    if not is_job_board_url:
        domain_rows = [r for r in cleaned if r[0] == "url_domain"]
        if domain_rows:
            domain = domain_rows[0]
            structured = [r for r in cleaned if r[0] == "structured"]
            if structured and structured[0][2] != domain[2]:
                return EmployerIdentityResolution(None, False, "ambiguous", "Employer domain and structured company differ.")
            return EmployerIdentityResolution(domain[1], True, "confirmed", "Employer-owned domain.")

    structured = [r for r in cleaned if r[0] == "structured"]
    if structured:
        primary = structured[0]
        conflicting = [r for r in cleaned if r[2] != primary[2]]
        if conflicting:
            return EmployerIdentityResolution(None, False, "ambiguous", "Multiple employer candidates differ.")
        return EmployerIdentityResolution(primary[1], True, "confirmed", "Structured company field.")

    by_key: dict[str, list[tuple[str, str, str]]] = {}
    for row in cleaned:
        by_key.setdefault(row[2], []).append(row)
    corroborated = [rows for rows in by_key.values() if len({r[0] for r in rows}) >= 2]
    if len(corroborated) == 1:
        return EmployerIdentityResolution(corroborated[0][0][1], True, "confirmed", "Employer corroborated by multiple signals.")
    if len(by_key) > 1:
        return EmployerIdentityResolution(None, False, "ambiguous", "Multiple employer candidates differ.")
    return EmployerIdentityResolution(None, False, "weak", "Employer candidate was not corroborated.")


def is_scam_domain_url(url: str) -> bool:
    dom = registrable_domain_from_url(url)
    if not dom:
        return False
    return dom.lower() in _SCAM_REGISTRABLE_DOMAINS
