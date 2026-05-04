"""Job URL and pasted-text normalization (Sprint 2).

Naive registrable-domain extraction is intentional (no publicsuffix dependency).
Known limitation: multi-part public suffixes (e.g. ``co.uk``) are not handled;
bump ``NORMALIZATION_VERSION`` if replaced with a proper PSL library.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

NORMALIZATION_VERSION = "2.0.0"

# Strip common marketing/analytics params; extend via version bump.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_eid",
        "_ga",
    }
)

_MAX_TEXT_BYTES_HINT = 32768


def _is_tracking_query_key(key: str) -> bool:
    lk = key.lower()
    if lk in _TRACKING_PARAMS:
        return True
    return lk.startswith("utm_")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def registrable_domain_naive(host: str) -> Optional[str]:
    host = host.lower().rstrip(".")
    if not host:
        return None
    parts = host.split(".")
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])


def normalize_job_url(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return ``(canonical_url, url_sha256)`` or ``(None, None)`` if absent/invalid."""
    if raw is None:
        return None, None
    s = raw.strip()
    if not s:
        return None, None
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, None
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # Drop default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_key(k)
    ]
    query = urlencode(query_pairs)
    cleaned = urlunparse((scheme, netloc, path, "", query, ""))
    return cleaned, _sha256_hex(cleaned.encode("utf-8"))


def normalize_job_text(raw: Optional[str], max_chars: int = _MAX_TEXT_BYTES_HINT) -> tuple[Optional[str], Optional[str]]:
    """Return ``(normalized_text, sha256_of_full_nfkc_bytes)``.

    Truncation uses character count for simplicity; full hash is always of the
    **full** NFKC-normalized string before truncation.
    """
    if raw is None:
        return None, None
    nfkc = unicodedata.normalize("NFKC", raw)
    full_bytes = nfkc.encode("utf-8")
    full_hash = _sha256_hex(full_bytes)
    collapsed = _collapse_ws(nfkc)
    if not collapsed:
        return None, full_hash
    truncated = collapsed[:max_chars]
    return truncated, full_hash


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    normalization_version: str
    canonical_url: Optional[str]
    canonical_url_sha256: Optional[str]
    description_text: Optional[str]
    description_full_sha256: Optional[str]
    registrable_domain: Optional[str]


def normalize_job_input(
    job_url: Optional[str],
    job_description: Optional[str],
) -> NormalizationResult:
    canonical_url, url_hash = normalize_job_url(job_url)
    desc_text, desc_full_hash = normalize_job_text(job_description)

    domain: Optional[str] = None
    if canonical_url:
        host = urlparse(canonical_url).hostname or ""
        domain = registrable_domain_naive(host)

    return NormalizationResult(
        normalization_version=NORMALIZATION_VERSION,
        canonical_url=canonical_url,
        canonical_url_sha256=url_hash,
        description_text=desc_text,
        description_full_sha256=desc_full_hash,
        registrable_domain=domain,
    )
