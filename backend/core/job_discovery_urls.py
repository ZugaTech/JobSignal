"""Strict URL gate for similar-job discovery (organic search candidates).

Employer / company LinkedIn pages and Pulse/posts must never pass as job postings here.
Evidence-layer ``company_linkedin_presence`` remains separate and unchanged.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# LinkedIn: only concrete job view URLs (not company pages, feed, learning, pulse, posts).
_LINKEDIN_JOB_VIEW = re.compile(r"linkedin\.com/jobs/view/", re.I)

_INDEED_JOBISH = re.compile(
    r"indeed\.com/(viewjob|jobs/view|pagead/clk|rc/clk|job/)",
    re.I,
)

_LEVER_JOB = re.compile(r"jobs\.lever\.co/[^/]+/[^/?#]+", re.I)

_ZIP_JOB = re.compile(r"ziprecruiter\.com/jobs?/", re.I)

_SMARTRECRUITERS = re.compile(r"smartrecruiters\.com/[^?]*/job/", re.I)

_ASHBY = re.compile(r"jobs\.ashbyhq\.com/", re.I)

_LINKEDIN_REJECT_PATH = re.compile(
    r"/(company/|in/|pulse/|posts/|school/|showcase/|feed/|learning/|advice/|news/|jobs/search)",
    re.I,
)


def is_job_posting_discovery_candidate(raw_url: str) -> bool:
    """Return True only when URL looks like a concrete job posting on a known board/ATS."""

    if not raw_url or not isinstance(raw_url, str):
        return False
    u = raw_url.strip()
    if len(u) < 12:
        return False
    try:
        parsed = urlparse(u)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    path_low = (parsed.path or "").lower()
    combined = f"{host}{parsed.path or ''}"

    if "linkedin.com" in host:
        if _LINKEDIN_REJECT_PATH.search(parsed.path or ""):
            return False
        return bool(_LINKEDIN_JOB_VIEW.search(combined))

    if "indeed." in host:
        if "/cmp/" in path_low:
            return False
        return bool(_INDEED_JOBISH.search(combined))

    if "glassdoor." in host:
        return "/job-listing/" in path_low or "/job/" in path_low

    if "greenhouse.io" in host:
        return "/jobs/" in path_low or "/job/" in path_low

    if "lever.co" in host:
        return bool(_LEVER_JOB.search(combined))

    if "myworkdayjobs.com" in host:
        return "/job/" in path_low or "/jobs/" in path_low

    if "workday.com" in host and "myworkdayjobs" not in host:
        return "/job/" in path_low

    if "ziprecruiter." in host:
        return bool(_ZIP_JOB.search(combined))

    if "smartrecruiters.com" in host:
        return bool(_SMARTRECRUITERS.search(combined))

    if "ashbyhq.com" in host:
        return bool(_ASHBY.search(combined))

    # Conservative fallback: obvious job path segments on other domains.
    if any(
        seg in path_low
        for seg in (
            "/jobs/",
            "/job/",
            "/careers/job",
            "/careers/jobs",
            "/position/",
            "/opening/",
            "/vacancies/",
            "/vacancy/",
        )
    ):
        if any(b in host for b in ("wikipedia.org", "facebook.com", "medium.com")):
            return False
        return True

    return False
