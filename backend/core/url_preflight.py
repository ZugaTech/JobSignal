"""URL preflight checks before spending search/LLM budget (live pipeline only)."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import unquote, urlparse

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
_KNOWN_JOB_PLATFORMS = frozenset(
    {
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "workday.com",
        "wellfound.com",
        "angel.co",
        "jobvite.com",
        "smartrecruiters.com",
        "ashbyhq.com",
        "recruitee.com",
        "breezy.hr",
        "bamboohr.com",
        "icims.com",
        "taleo.net",
        "successfactors.com",
        "ziprecruiter.com",
        "monster.com",
        "careerbuilder.com",
        "simplyhired.com",
        "dice.com",
        "hired.com",
        "remote.co",
        "weworkremotely.com",
        "remoteok.com",
        "ycombinator.com",
    }
)
# Never scan the raw full URL for "--" or ";": tracking/query tokens (LinkedIn eBP, base64, etc.) contain those substrings.
_PATH_SQL_HINT = re.compile(
    r"(\bunion\b\s+\bselect\b|\bdrop\b\s+\btable\b|\binto\b\s+outfile\b|\bexec\b\s*\()",
    re.I,
)
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
_REASON_VERIFY_DOMAIN = "This job page could not be reached right now. It may be behind a login or temporarily unavailable."
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


def _sql_injection_hint_in_path(path: str) -> bool:
    """Classic SQLi fragments belong in path segments; query strings use arbitrary encodings."""
    if not path or path == "/":
        return False
    return bool(_PATH_SQL_HINT.search(unquote(path)))


def is_known_job_platform(hostname: str) -> bool:
    host = hostname.lower().strip().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in _KNOWN_JOB_PLATFORMS)


def validate_url_format(url: str) -> Optional[str]:
    """Return plain-English failure reason or ``None`` if format is acceptable."""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return _REASON_SKIP_FORMAT

    parsed = urlparse(u)

    if _TRAVERSAL.search(u):
        return _REASON_SKIP_FORMAT

    if _sql_injection_hint_in_path(parsed.path):
        return _REASON_SKIP_FORMAT

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

    lower_path = (parsed.path or "").lower()
    if "google." in host and (lower_path == "/search" or lower_path.startswith("/url")):
        return _REASON_SKIP_GOOGLE

    for s in _SHORTENERS:
        if host == s.rstrip("/") or host.endswith("." + s.rstrip("/")):
            return _REASON_SKIP_SHORTENER

    if parsed.scheme == "mailto":
        return _REASON_SKIP_OTHER

    return None


def domain_resolves(url: str) -> bool:
    if under_pytest():
        return True
    host = urlparse(url.strip()).hostname or ""
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


async def head_domain_root(url: str) -> Literal["ok", "unknown"]:
    """Best-effort positive signal only; blocked HEAD/TLS/timeouts do not reject valid URLs."""
    if under_pytest():
        return "ok"
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    host = parsed.hostname or ""
    if not host:
        return "unknown"
    origin = f"{scheme}://{host}/"
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=3.0) as client:
            r = await client.head(origin)
            # Any HTTP response means transport worked
            _ = r.status_code
            return "ok"
    except httpx.RequestError:
        return "unknown"


def _url_matches_job_heuristic(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if is_known_job_platform(host):
        return True
    return bool(_JOB_PATH_RE.search(parsed.path or ""))


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

    if _url_matches_job_heuristic(url) or _description_matches_job_keywords(description_text):
        return UrlPreflightResult(outcome="proceed", plain_reason="")

    if not domain_resolves(url):
        return UrlPreflightResult(outcome="verify_weak", plain_reason=_REASON_VERIFY_DOMAIN)

    await head_domain_root(url)

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
