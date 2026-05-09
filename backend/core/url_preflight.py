"""URL preflight checks before spending search/LLM budget (live pipeline only)."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx

from backend.core.env import EnvConfig
from backend.core.fetch_job_page import job_fetch_enabled, run_job_page_fetch
from backend.core.llm_safe import under_pytest

_JOB_PATH_RE = re.compile(
    r"(/jobs?/|/careers?/|/position/|/opening/|/vacancy/|/apply/|/posting/|"
    r"linkedin\.com/jobs|indeed\.com|glassdoor\.com/job|greenhouse\.io|lever\.co|"
    r"workday|wellfound\.com|jobvite|smartrecruiters|myworkdayjobs)",
    re.I,
)
_JOB_KEYWORD_RE = re.compile(
    r"\b(salary|responsibilities|requirements|apply|hiring|position|experience)\b",
    re.I,
)
_SQLISH = re.compile(r"(--|;|--|\bunion\b\s+\bselect\b|\bdrop\b\s+\btable\b)", re.I)
_TRAVERSAL = re.compile(r"(\.\./|%2e%2e|%252e|\\\\|\.\.\\)", re.I)

_SHORTENERS = (
    "bit.ly/",
    "tinyurl.com/",
    "t.co/",
    "goo.gl/",
    "ow.ly/",
    "buff.ly/",
    "short.link/",
)

_REASON_SKIP_FORMAT = "This does not appear to be a valid URL. Please check the link and try again."
_REASON_SKIP_DOMAIN = "This domain could not be reached. The link may be broken or the site may be down."
_REASON_SKIP_SHORTENER = "Please paste the final destination URL, not a shortened link."
_REASON_SKIP_GOOGLE = "Please paste the direct link to the job posting, not a search results page."
_REASON_SKIP_OTHER = "This link format cannot be verified automatically. Paste the direct job posting URL instead."
_REASON_VERIFY_JOBISH = (
    "We could not confirm this is a job posting. If it is, paste the job description directly for a better result."
)


@dataclass(frozen=True, slots=True)
class UrlPreflightResult:
    outcome: Literal["proceed", "skip", "verify_weak"]
    plain_reason: str


def _host_is_literal_blocked_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved


def validate_url_format(url: str) -> Optional[str]:
    """Return plain-English failure reason or ``None`` if format is acceptable."""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return _REASON_SKIP_FORMAT

    if _TRAVERSAL.search(u):
        return _REASON_SKIP_FORMAT

    if _SQLISH.search(u):
        return _REASON_SKIP_FORMAT

    parsed = urlparse(u)
    host = (parsed.hostname or "").lower()
    if not host:
        return _REASON_SKIP_FORMAT

    if host in ("localhost",):
        return _REASON_SKIP_FORMAT

    if _host_is_literal_blocked_ip(host):
        return _REASON_SKIP_FORMAT

    # registrable-ish TLD check: last label has at least 2 chars
    labels = host.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2:
        return _REASON_SKIP_FORMAT

    lu = u.lower()
    if "google." in host and ("/search" in parsed.path or "google.com/url" in lu):
        return _REASON_SKIP_GOOGLE

    for s in _SHORTENERS:
        if s in lu:
            return _REASON_SKIP_SHORTENER

    if parsed.scheme == "mailto" or lu.startswith("mailto:"):
        return _REASON_SKIP_OTHER

    return None


async def head_domain_root(url: str) -> Literal["ok", "unreachable"]:
    """Lightweight HEAD to origin; unreachable on DNS/connect/TLS failures."""
    if under_pytest():
        return "ok"

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    host = parsed.hostname or ""
    if not host:
        return "unreachable"
    origin = f"{scheme}://{host}/"
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=4.0) as client:
            r = await client.head(origin)
            # Any HTTP response means transport worked
            _ = r.status_code
            return "ok"
    except httpx.RequestError:
        return "unreachable"


def _url_matches_job_heuristic(url: str) -> bool:
    return bool(_JOB_PATH_RE.search(url))


def _description_matches_job_keywords(desc: Optional[str]) -> bool:
    if not desc:
        return False
    return bool(_JOB_KEYWORD_RE.search(desc))


async def evaluate_job_url_preflight(
    url: str,
    description_text: Optional[str],
    *,
    cfg: EnvConfig,
) -> UrlPreflightResult:
    """Ordered checks; returns proceed or earliest terminal outcome."""

    fmt = validate_url_format(url)
    if fmt:
        return UrlPreflightResult(outcome="skip", plain_reason=fmt)

    reach = await head_domain_root(url)
    if reach == "unreachable":
        return UrlPreflightResult(outcome="skip", plain_reason=_REASON_SKIP_DOMAIN)

    if _url_matches_job_heuristic(url) or _description_matches_job_keywords(description_text):
        return UrlPreflightResult(outcome="proceed", plain_reason="")

    page_blob = ""
    if job_fetch_enabled():
        fx = run_job_page_fetch(url.strip(), cfg)
        # Concatenate signal details / warnings text — conservative keyword scan only
        parts: list[str] = []
        for s in fx.signals:
            parts.append(str(s.get("details", "")))
        page_blob = " ".join(parts)

    if _JOB_KEYWORD_RE.search(page_blob):
        return UrlPreflightResult(outcome="proceed", plain_reason="")

    return UrlPreflightResult(outcome="verify_weak", plain_reason=_REASON_VERIFY_JOBISH)
