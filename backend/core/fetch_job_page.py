"""SSRF-bounded GET of the primary job posting URL (Sprint 9).

Resolves hostnames and blocks disallowed destination IPs before connecting.
Redirects are followed manually so each hop is re-validated.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from backend.core.env import EnvConfig
from backend.core.job_url_shortcuts import is_job_board_brand_label
from backend.core.normalization import registrable_domain_naive

FETCH_ADAPTER_VERSION = "1.1.0"

_FETCH_HTML_SAMPLE_CAP = 400_000


def extract_employer_urls_from_html(html_bytes: bytes, base_url: str, *, max_urls: int = 48) -> Tuple[str, ...]:
    """Extract employer / careers URLs from fetched HTML (single GET; used for domain alignment).

    Conservative patterns only — canonical, ``og:url``, JSON-LD Organization URL, career-like anchors.
    """

    if not html_bytes or not base_url.startswith(("http://", "https://")):
        return ()
    text = html_bytes[:_FETCH_HTML_SAMPLE_CAP].decode("utf-8", errors="ignore")
    found: List[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        u = raw.strip().strip(",").rstrip(".,);)]}\"'")
        if not u.startswith(("http://", "https://")):
            return
        low = u.lower()
        if low.startswith(("javascript:", "mailto:", "tel:", "data:")):
            return
        if u not in seen:
            seen.add(u)
            found.append(u)

    for rx in (
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    ):
        for m in re.finditer(rx, text, re.I):
            add(urljoin(base_url, m.group(1)))

    for m in re.finditer(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        re.I,
    ):
        add(urljoin(base_url, m.group(1)))

    for m in re.finditer(
        r'\{[^{}]*"@type"\s*:\s*"Organization"[^{}]*"url"\s*:\s*"([^"]+)"[^{}]*\}',
        text,
        re.I | re.DOTALL,
    ):
        add(urljoin(base_url, m.group(1)))

    for m in re.finditer(r'"sameAs"\s*:\s*"([^"]+)"', text, re.I):
        add(urljoin(base_url, m.group(1)))

    career_kw = ("career", "job", "employment", "join-", "hiring", "work-at", "vacanc", "opening")
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', text, re.I):
        href = m.group(1).strip()
        low = href.lower()
        if any(k in low for k in career_kw):
            add(urljoin(base_url, href))

    return tuple(found[:max_urls])


def job_fetch_enabled() -> bool:
    v = (os.environ.get("ENABLE_JOB_FETCH", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class JobPageFetchOutcome:
    """Result of attempting a live fetch (for orchestrator wiring)."""

    attempted: bool
    signals: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    final_url: Optional[str] = None
    employer_page_urls: Tuple[str, ...] = ()
    page_title: Optional[str] = None
    page_description: Optional[str] = None
    site_name: Optional[str] = None
    extracted_job_text: Optional[str] = None


_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _parse_host_port(netloc: str) -> Tuple[str, Optional[int]]:
    host = netloc
    port: Optional[int] = None
    if host.startswith("["):
        end = host.find("]")
        if end != -1 and len(host) > end + 1 and host[end + 1] == ":":
            inner = host[1:end]
            port = int(host[end + 2 :])
            return inner, port
        if end != -1:
            return host[1:end], None
    if ":" in host and not host.startswith("["):
        h2, p2 = host.rsplit(":", 1)
        if p2.isdigit():
            return h2, int(p2)
    return host, port


def _ip_addresses_for_host(hostname: str) -> List[str]:
    """Resolve hostname to IP strings (IPv4 or IPv6). Literal IPs pass through."""

    host = hostname.strip()
    if not host:
        return []

    try:
        ip = ipaddress.ip_address(host)
        return [str(ip)]
    except ValueError:
        pass

    if host.startswith("[") and host.endswith("]"):
        inner = host[1:-1]
        try:
            return [str(ipaddress.ip_address(inner))]
        except ValueError:
            return []

    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips: List[str] = []
    for info in infos:
        sockaddr = info[4]
        if len(sockaddr) == 2:
            ips.append(sockaddr[0])
        elif len(sockaddr) == 4:
            ips.append(sockaddr[0])
    return list(dict.fromkeys(ips))


def _is_blocked_ip(ip_s: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_s.split("%")[0])
    except ValueError:
        return True
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_reserved or ip.is_unspecified:
        return True
    # IPv4 documentation / shared address space (carrier-grade NAT) — conservative block for SSRF
    if ip.version == 4:
        if ip in ipaddress.ip_network("100.64.0.0/10", strict=False):
            return True
    return False


def assert_safe_request_url(url: str) -> Tuple[str, str]:
    """Validate scheme/host and that resolved IPs are not SSRF targets.

    Returns ``(normalized_url_string, hostname_for_display)``.
    """

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("FETCH_SCHEME: Only http and https URLs are allowed.")
    if not parsed.netloc:
        raise ValueError("FETCH_NETLOC: URL must include a host.")

    host, _port = _parse_host_port(parsed.netloc.split("@")[-1])
    if not host:
        raise ValueError("FETCH_HOST: Missing host.")

    ips = _ip_addresses_for_host(host)
    if not ips:
        raise ValueError("FETCH_DNS: Could not resolve host.")

    for ip_s in ips:
        if _is_blocked_ip(ip_s):
            raise ValueError(f"FETCH_SSRF: Disallowed destination address for host {host!r}.")

    return url, host


def _fetch_ok_signal(strength: str, details: str) -> Dict[str, Any]:
    return {
        "id": "fetch_ok",
        "label": "Live page fetch",
        "tier": "T1",
        "strength": strength,
        "details": details[:512],
    }


def _domain_align_signal(strength: str, details: str) -> Dict[str, Any]:
    return {
        "id": "domain_align",
        "label": "Domain match after redirects",
        "tier": "T1",
        "strength": strength,
        "details": details[:512],
    }


def _clean_html_text(raw: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", text).strip()


def _first_meta_content(html: str, *names: str) -> Optional[str]:
    for name in names:
        rx = (
            r'<meta[^>]+(?:name|property)=["\']'
            + re.escape(name)
            + r'["\'][^>]+content=["\']([^"\']+)["\']'
        )
        m = re.search(rx, html, re.I)
        if m:
            cleaned = _clean_html_text(m.group(1))
            if cleaned:
                return cleaned[:500]
    return None


def extract_job_text_hints_from_html(html_bytes: bytes) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract conservative page hints for search/recommendation discovery.

    This is not treated as trusted evidence by itself; it only improves query
    construction when the user supplied a URL but no pasted job description.
    """

    if not html_bytes:
        return None, None, None, None
    html = html_bytes[:_FETCH_HTML_SAMPLE_CAP].decode("utf-8", errors="ignore")

    title: Optional[str] = None
    for rx in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ):
        m = re.search(rx, html, re.I | re.S)
        if m:
            title = _clean_html_text(m.group(1))[:160]
            if title:
                break

    site_name = _first_meta_content(html, "og:site_name", "application-name")
    description = _first_meta_content(html, "description", "og:description", "twitter:description")

    body_sample = _clean_html_text(html)[:1600]
    parts: List[str] = []
    if title:
        parts.append(f"Title: {title}")
    # og:site_name is often the job board (e.g. "LinkedIn") — do not label that as the employer.
    if site_name and not is_job_board_brand_label(site_name):
        parts.append(f"Company: {site_name}")
    if description:
        parts.append(f"Description: {description}")
    elif body_sample:
        parts.append(f"Description: {body_sample}")

    extracted = "\n".join(parts).strip() or None
    return title, description, site_name, extracted


def run_job_page_fetch(
    canonical_url: str,
    cfg: EnvConfig,
    *,
    client: Optional[httpx.Client] = None,
) -> JobPageFetchOutcome:
    """Perform one bounded GET chain; return signals + warnings."""

    if not job_fetch_enabled():
        return JobPageFetchOutcome(attempted=False)

    warnings: List[Dict[str, str]] = []
    initial_domain: Optional[str] = None
    try:
        _, host0 = assert_safe_request_url(canonical_url)
        initial_domain = registrable_domain_naive(host0)
    except ValueError as e:
        warnings.append({"code": "FETCH_BLOCKED", "message": str(e)})
        return JobPageFetchOutcome(
            attempted=True,
            signals=[_fetch_ok_signal("low", f"Fetch not started: {e}")],
            warnings=warnings,
        )

    timeout = httpx.Timeout(6.0, connect=2.0)
    headers = {"User-Agent": "JobSignal/1.0 (+https://github.com/jobverification)", "Accept": "text/html,*/*;q=0.8"}

    own_client = client is None
    hc = client or httpx.Client(timeout=timeout, verify=True)

    current = canonical_url
    redirect_hops = 0
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    total_read = 0
    final_url = canonical_url

    try:
        while True:
            try:
                assert_safe_request_url(current)
            except ValueError as e:
                warnings.append({"code": "FETCH_REDIRECT_SSRF", "message": str(e)})
                return JobPageFetchOutcome(
                    attempted=True,
                    signals=[_fetch_ok_signal("low", f"Redirect target blocked: {e}")],
                    warnings=warnings,
                )

            try:
                with hc.stream("GET", current, headers=headers, follow_redirects=False) as resp:
                    status_code = resp.status_code
                    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower() or None
                    final_url = str(resp.url)

                    if status_code in (301, 302, 303, 307, 308):
                        if redirect_hops >= cfg.fetch_max_redirects:
                            warnings.append({"code": "FETCH_REDIRECT_LIMIT", "message": "Too many redirects."})
                            return JobPageFetchOutcome(
                                attempted=True,
                                signals=[_fetch_ok_signal("low", "Too many redirects.")],
                                warnings=warnings,
                            )
                        loc = resp.headers.get("location")
                        if not loc:
                            warnings.append({"code": "FETCH_REDIRECT", "message": "Redirect without Location header."})
                            return JobPageFetchOutcome(
                                attempted=True,
                                signals=[_fetch_ok_signal("low", "Redirect response missing Location header.")],
                                warnings=warnings,
                            )
                        current = urljoin(current, loc.strip())
                        redirect_hops += 1
                        resp.read()
                        continue

                    chunk_size = 64_000
                    buf = bytearray()
                    for chunk in resp.iter_bytes(chunk_size):
                        buf.extend(chunk)
                        total_read = len(buf)
                        if total_read >= cfg.fetch_max_bytes:
                            break
            except httpx.TimeoutException:
                warnings.append({"code": "FETCH_TIMEOUT", "message": "HTTP timeout while fetching job page."})
                return JobPageFetchOutcome(
                    attempted=True,
                    signals=[_fetch_ok_signal("low", "Fetch timed out.")],
                    warnings=warnings,
                )
            except httpx.RequestError as e:
                warnings.append({"code": "FETCH_ERROR", "message": f"HTTP error: {type(e).__name__}"})
                return JobPageFetchOutcome(
                    attempted=True,
                    signals=[_fetch_ok_signal("low", f"Request failed: {type(e).__name__}")],
                    warnings=warnings,
                )

            break

        assert status_code is not None

        if status_code >= 400:
            warnings.append({"code": "FETCH_HTTP", "message": f"HTTP status {status_code}."})
            return JobPageFetchOutcome(
                attempted=True,
                signals=[_fetch_ok_signal("low", f"HTTP {status_code}; received {total_read} bytes.")],
                warnings=warnings,
            )

        html_like = content_type is None or "html" in content_type or content_type in ("text/plain", "application/xhtml+xml")
        if not html_like:
            warnings.append(
                {
                    "code": "FETCH_CONTENT_TYPE",
                    "message": f"Unexpected content-type {content_type!r}; treating fetch as weak evidence.",
                }
            )
            strength = "medium"
            details = f"HTTP {status_code}; {total_read} bytes; type={content_type or 'unknown'}"
        else:
            strength = "high" if status_code == 200 and total_read > 200 else "medium"
            details = f"HTTP {status_code}; {total_read} bytes; final URL fingerprinted"

        signals: List[Dict[str, Any]] = [_fetch_ok_signal(strength, details)]

        final_parsed = urlparse(final_url)
        final_host = _parse_host_port(final_parsed.netloc.split("@")[-1])[0]
        final_domain = registrable_domain_naive(final_host) if final_host else None

        if initial_domain and final_domain:
            if initial_domain == final_domain:
                signals.append(
                    _domain_align_signal(
                        "medium",
                        f"Same registrable domain after redirects ({initial_domain}).",
                    )
                )
            else:
                signals.append(
                    _domain_align_signal(
                        "low",
                        f"Redirect changed registrable domain: {initial_domain} → {final_domain}.",
                    )
                )
                warnings.append(
                    {
                        "code": "FETCH_DOMAIN_SHIFT",
                        "message": "Final page is on a different registrable domain than the original URL.",
                    }
                )
        else:
            signals.append(_domain_align_signal("none", "Could not compare registrable domains."))

        employer_urls: Tuple[str, ...] = ()
        page_title: Optional[str] = None
        page_description: Optional[str] = None
        site_name: Optional[str] = None
        extracted_job_text: Optional[str] = None
        if html_like and total_read > 0:
            html_bytes = bytes(buf)
            employer_urls = extract_employer_urls_from_html(html_bytes, final_url)
            page_title, page_description, site_name, extracted_job_text = extract_job_text_hints_from_html(html_bytes)

        return JobPageFetchOutcome(
            attempted=True,
            signals=signals,
            warnings=warnings,
            final_url=final_url,
            employer_page_urls=employer_urls,
            page_title=page_title,
            page_description=page_description,
            site_name=site_name,
            extracted_job_text=extracted_job_text,
        )
    finally:
        if own_client:
            hc.close()
