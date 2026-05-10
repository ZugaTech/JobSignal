"""Evidence bundle builder (Sprint 3: multi-source verification + honest uncertainty).

Search provider: Serper.dev (google.serper.dev/search) — POST, X-API-KEY header.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.core.extraction import ExtractionResult
from backend.core.fetch_job_page import JobPageFetchOutcome
from backend.core.normalization import NormalizationResult, registrable_domain_naive


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    official_page_found: bool
    official_url: Optional[str]
    duplicate_risk: bool
    recruiter_verified: bool
    signals: List[Dict[str, Any]]
    warnings: List[Dict[str, str]]
    evidence_sources: List[Dict[str, str]]


SUPPORTED_BOARDS = ("linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_official_domain(netloc: str, company_hint: Optional[str]) -> bool:
    """True when hostname / registrable domain plausibly belongs to ``company_hint``."""

    if not netloc or not company_hint:
        return False
    host = netloc.lower().strip()
    if "@" in host:
        host = host.split("@")[-1]
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    hint = re.sub(r"[^a-z0-9]", "", company_hint.lower())
    if len(hint) < 2:
        return False
    reg = registrable_domain_naive(host)
    if reg:
        base = reg.split(".")[0]
        base_clean = re.sub(r"[^a-z0-9]", "", base)
        if len(base_clean) >= 3 and (hint in base_clean or base_clean in hint):
            return True
    for label in host.split("."):
        lbl = re.sub(r"[^a-z0-9]", "", label)
        if len(lbl) >= 3 and (hint in lbl or lbl in hint):
            return True
    return False


def _posting_hostname(norm: NormalizationResult) -> str:
    if not norm.canonical_url:
        return ""
    return (urlparse(norm.canonical_url).hostname or "").lower()


def _registrable_domains_align(host_a: str, host_b: str) -> bool:
    ha = host_a.lower().split(":")[0]
    hb = host_b.lower().split(":")[0]
    if ha.startswith("www."):
        ha = ha[4:]
    if hb.startswith("www."):
        hb = hb[4:]
    ra = registrable_domain_naive(ha)
    rb = registrable_domain_naive(hb)
    return bool(ra and rb and ra == rb)


def _resolve_official_careers_url(
    norm: NormalizationResult,
    ext: ExtractionResult,
    serp_official_url: Optional[str],
    page_fetch: Optional[JobPageFetchOutcome],
) -> tuple[Optional[str], str]:
    """Prefer URLs extracted from the live job page, then Serp careers hits, then direct employer posting."""

    posting_host = _posting_hostname(norm)
    posting_reg = registrable_domain_naive(posting_host) if posting_host else None

    tier_same_reg: List[str] = []
    tier_company: List[str] = []

    if page_fetch and page_fetch.employer_page_urls:
        for link in page_fetch.employer_page_urls:
            h = (urlparse(link).hostname or "").lower()
            if not h:
                continue
            reg = registrable_domain_naive(h)
            if posting_reg and reg and posting_reg == reg:
                tier_same_reg.append(link)
            elif ext.company_hint and _is_official_domain(h, ext.company_hint):
                tier_company.append(link)

    def _first_dedup(rows: List[str]) -> Optional[str]:
        seen: set[str] = set()
        for u in rows:
            if u not in seen:
                seen.add(u)
                return u
        return None

    picked = _first_dedup(tier_same_reg)
    if picked:
        return picked, "job_page_same_registrable"
    picked = _first_dedup(tier_company)
    if picked:
        return picked, "job_page_company_match"
    if serp_official_url:
        return serp_official_url, "search_careers"
    if norm.canonical_url and posting_host and _is_official_domain(posting_host, ext.company_hint):
        return norm.canonical_url.strip(), "posting_on_company_domain"
    return None, ""


def _extract_days_from_snippet(snippet: str) -> Optional[int]:
    text = (snippet or "").lower()
    m = re.search(r"(\\d+)\\s+day", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\\d+)\\s+week", text)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r"(\\d+)\\s+month", text)
    if m:
        return int(m.group(1)) * 30
    return None


def _mk_signal(
    *,
    sid: str,
    label: str,
    tier: str,
    strength: str,
    detail: str,
    status: str,
    source: str,
) -> Dict[str, Any]:
    # Keep legacy fields (`id/label/tier/strength/details`) and add Sprint-3 signal contract fields.
    return {
        "id": sid,
        "label": label,
        "tier": tier,
        "strength": strength,
        "details": detail,
        "name": label,
        "status": status,
        "detail": detail,
        "source": source,
    }


async def _collect_serper_queries(coordinator: Any, base_query: str, company: str, title: str) -> Dict[str, Any]:
    tasks = {
        "careers": coordinator.search(f"{base_query} careers".strip(), num=8),
        "board": coordinator.search(f"\"{title}\" \"{company}\" job".strip(), num=10),
        "rep": coordinator.search(f"\"{company}\" layoffs scam \"fake recruiter\"".strip(), num=8),
        "linkedin": coordinator.search(f"site:linkedin.com/company \"{company}\"".strip(), num=5),
        "registry": coordinator.search(f"\"{company}\" (crunchbase OR \"companies house\")".strip(), num=8),
        "duplicates": coordinator.search(f"\"{title}\" \"{company}\"".strip(), num=10),
    }
    keys = list(tasks.keys())
    values = await asyncio.gather(*tasks.values())
    
    # Format results to match old tuple return: (rows, status, warning)
    res = {}
    for k, v in zip(keys, values):
        if v is None:
            # Dropped or rate limited or error
            res[k] = ([], "unverified", {"code": "SERPER_UNVERIFIED", "message": "Search API key missing or rate limited."})
        else:
            res[k] = (v, "verified", None)
    return res


def build_evidence_bundle(
    norm: NormalizationResult,
    ext: ExtractionResult,
    serp_results: Dict[str, Any],
    page_fetch: Optional[JobPageFetchOutcome] = None,
) -> EvidenceBundle:
    signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []
    evidence_sources: List[Dict[str, str]] = []

    duplicate_risk = False
    recruiter_verified = False

    company = ext.company_hint or ""
    title = ext.title_hint or ""
    base_query = f"{company} {title}".strip() or (norm.canonical_url or "")

    careers_rows, careers_status, careers_warning = serp_results.get("careers", ([], "unverified", None))
    if careers_warning:
        warnings.append(careers_warning)

    serp_official_url: Optional[str] = None
    for row in careers_rows:
        link = str(row.get("link") or "").strip()
        if not link.startswith(("http://", "https://")):
            continue
        evidence_sources.append({"url": link, "type": "careers_search", "found_at": _now_iso()})
        domain = urlparse(link).netloc
        if _is_official_domain(domain, ext.company_hint):
            serp_official_url = link
            break

    official_url, official_source = _resolve_official_careers_url(norm, ext, serp_official_url, page_fetch)
    official_found = bool(official_url)

    fetch_attempted = page_fetch is not None and page_fetch.attempted
    html_candidates = bool(page_fetch and page_fetch.employer_page_urls)
    careers_effectively_verified = careers_status == "verified" or (fetch_attempted and html_candidates)

    if official_found:
        careers_detail_map = {
            "job_page_same_registrable": "Employer URL from the fetched job page shares this posting's domain.",
            "job_page_company_match": "Employer URL extracted from the fetched job page.",
            "search_careers": official_url or "Official careers listing matched via search.",
            "posting_on_company_domain": "Job link is hosted on an employer-aligned domain.",
        }
        careers_detail = careers_detail_map.get(official_source, official_url or "Official employer URL resolved.")
    elif careers_status == "unverified" and not fetch_attempted:
        careers_detail = "unverified"
    else:
        careers_detail = "No clear official careers match."

    careers_strength = (
        "none"
        if careers_status == "unverified" and not careers_effectively_verified
        else ("high" if official_found else "low")
    )
    careers_sig_status = (
        "unknown"
        if careers_strength == "none"
        else ("pass" if official_found else "fail")
    )

    signals.append(
        _mk_signal(
            sid="careers_page_match",
            label="careers_page_match",
            tier="T1",
            strength=careers_strength,
            detail=careers_detail,
            status=careers_sig_status,
            source=official_url or "serp",
        )
    )
    if official_found:
        signals.append(
            _mk_signal(
                sid="official_careers_page",
                label="official_careers_page",
                tier="T1",
                strength="high",
                detail=official_url or "Official careers match found.",
                status="pass",
                source=official_url or "serp",
            )
        )

    posting_host = _posting_hostname(norm)
    official_host = (urlparse(official_url).hostname or "").lower() if official_url else ""
    domain_match = bool(posting_host and official_host and _registrable_domains_align(posting_host, official_host))
    signals.append(
        _mk_signal(
            sid="careers_domain_match",
            label="careers_domain_match",
            tier="T1",
            strength="high" if domain_match else ("none" if not posting_host or not official_host else "low"),
            detail="Careers and posting domains align." if domain_match else ("Insufficient domain data to compare." if not posting_host or not official_host else "Posting domain does not match the employer URL registrable domain."),
            status="pass" if domain_match else ("unknown" if not posting_host or not official_host else "fail"),
            source=official_url or norm.canonical_url or "pattern",
        )
    )

    board_rows, board_status, board_warning = serp_results.get("board", ([], "unverified", None))
    if board_warning:
        warnings.append(board_warning)
    board_domains: Dict[str, int] = {}
    max_days = 0
    for row in board_rows:
        link = str(row.get("link") or "").strip()
        snippet = str(row.get("snippet") or "")
        if link.startswith(("http://", "https://")):
            host = (urlparse(link).hostname or "").lower()
            for board in SUPPORTED_BOARDS:
                if board in host:
                    board_domains[board] = board_domains.get(board, 0) + 1
                    evidence_sources.append({"url": link, "type": f"board:{board}", "found_at": _now_iso()})
        days = _extract_days_from_snippet(snippet)
        if days and days > max_days:
            max_days = days
    cross_count = len(board_domains)
    signals.append(
        _mk_signal(
            sid="cross_platform_freshness",
            label="cross_platform_freshness",
            tier="T2",
            strength="none" if board_status == "unverified" else ("high" if cross_count >= 2 else "low"),
            detail="unverified" if board_status == "unverified" else f"Found on {cross_count} platforms ({', '.join(sorted(board_domains.keys())) or 'none'}).",
            status="unknown" if board_status == "unverified" else ("pass" if cross_count >= 2 else "fail"),
            source="serp",
        )
    )
    stale = max_days >= 30
    signals.append(
        _mk_signal(
            sid="staleness_flag",
            label="staleness_flag",
            tier="T2",
            strength="none" if board_status == "unverified" else ("low" if stale else "high"),
            detail="unverified" if board_status == "unverified" else f"Observed listing age up to {max_days} days.",
            status="unknown" if board_status == "unverified" else ("fail" if stale else "pass"),
            source="serp",
        )
    )
    first_seen_estimate: Optional[str] = None
    if max_days > 0:
        first_seen_estimate = (date.today() - timedelta(days=max_days)).isoformat()
    signals.append(
        _mk_signal(
            sid="first_seen_estimate",
            label="first_seen_estimate",
            tier="T2",
            strength="none" if board_status == "unverified" else ("low" if stale else "medium"),
            detail="unverified" if board_status == "unverified" else (first_seen_estimate or "No first-seen estimate found."),
            status="unknown" if board_status == "unverified" else ("fail" if stale else "pass"),
            source="serp",
        )
    )

    rep_rows, rep_status, rep_warning = serp_results.get("rep", ([], "unverified", None))
    if rep_warning:
        warnings.append(rep_warning)
    rep_hits = 0
    for row in rep_rows:
        snippet = str(row.get("snippet") or "").lower()
        title_text = str(row.get("title") or "").lower()
        blob = f"{snippet} {title_text}"
        if any(k in blob for k in ("layoff", "scam", "fake recruiter")):
            rep_hits += 1
        link = str(row.get("link") or "").strip()
        if link.startswith(("http://", "https://")):
            evidence_sources.append({"url": link, "type": "reputation", "found_at": _now_iso()})
    signals.append(
        _mk_signal(
            sid="company_reputation_signal",
            label="company_reputation_signal",
            tier="T3",
            strength="none" if rep_status == "unverified" else ("low" if rep_hits > 0 else "medium"),
            detail="unverified" if rep_status == "unverified" else f"Potential negative keyword hits: {rep_hits}.",
            status="unknown" if rep_status == "unverified" else ("fail" if rep_hits > 0 else "pass"),
            source="serp",
        )
    )

    linkedin_rows, linkedin_status, linkedin_warning = serp_results.get("linkedin", ([], "unverified", None))
    if linkedin_warning:
        warnings.append(linkedin_warning)
    linkedin_verified = any("linkedin.com/company/" in str(r.get("link") or "") for r in linkedin_rows)
    signals.append(
        _mk_signal(
            sid="company_linkedin_presence",
            label="company_linkedin_presence",
            tier="T1",
            strength="none" if linkedin_status == "unverified" else ("high" if linkedin_verified else "low"),
            detail="unverified" if linkedin_status == "unverified" else ("Verified LinkedIn company profile found." if linkedin_verified else "No clear LinkedIn company profile found."),
            status="unknown" if linkedin_status == "unverified" else ("pass" if linkedin_verified else "fail"),
            source="serp",
        )
    )

    registry_rows, registry_status, registry_warning = serp_results.get("registry", ([], "unverified", None))
    if registry_warning:
        warnings.append(registry_warning)
    registry_found = any(
        any(token in str(r.get("link") or "").lower() for token in ("crunchbase.com/organization", "find-and-update.company-information.service.gov.uk"))
        for r in registry_rows
    )
    signals.append(
        _mk_signal(
            sid="company_registry_presence",
            label="company_registry_presence",
            tier="T2",
            strength="none" if registry_status == "unverified" else ("high" if registry_found else "low"),
            detail="unverified" if registry_status == "unverified" else ("Company registry trail found." if registry_found else "No clear company registry trail found."),
            status="unknown" if registry_status == "unverified" else ("pass" if registry_found else "fail"),
            source="serp",
        )
    )

    dup_rows, dup_status, dup_warning = serp_results.get("duplicates", ([], "unverified", None))
    if dup_warning:
        warnings.append(dup_warning)
    dup_hosts = {(urlparse(str(r.get("link") or "")).hostname or "").lower() for r in dup_rows if str(r.get("link") or "").startswith(("http://", "https://"))}
    dup_hosts = {h for h in dup_hosts if h}
    dup_n = len(dup_hosts)
    duplicate_risk = dup_status == "verified" and dup_n >= 8

    if dup_status != "verified":
        dup_strength = "none"
        dup_detail = "unverified"
        dup_sig_status = "unknown"
    elif dup_n == 0:
        dup_strength = "low"
        dup_detail = "Search did not surface multiple posting domains; duplicate visibility is limited."
        dup_sig_status = "unknown"
    elif dup_n <= 2:
        dup_strength = "medium"
        dup_detail = f"Posting visibility spans about {dup_n} distinct domain(s) in search results."
        dup_sig_status = "pass"
    elif dup_n < 8:
        dup_strength = "low"
        dup_detail = f"Posting appears across {dup_n} domains; duplication signal is ambiguous without manual review."
        dup_sig_status = "unknown"
    else:
        dup_strength = "low"
        dup_detail = f"Posting appears across {dup_n} domains (possible recycled listing)."
        dup_sig_status = "fail"

    signals.append(
        _mk_signal(
            sid="posting_duplication_signal",
            label="posting_duplication_signal",
            tier="T2",
            strength=dup_strength,
            detail=dup_detail,
            status=dup_sig_status,
            source="serp",
        )
    )

    # Recruiter corroboration is best-effort; skip it when we can't safely run extra network calls.
    if ext.recruiter_name_hint and not recruiter_verified:
        signals.append(
            _mk_signal(
                sid="recruiter_unverified",
                label="recruiter_unverified",
                tier="T3",
                strength="low",
                detail=f"Recruiter '{ext.recruiter_name_hint}' could not be strongly corroborated.",
                status="unknown",
                source="serp",
            )
        )

    return EvidenceBundle(
        official_page_found=official_found,
        official_url=official_url,
        duplicate_risk=duplicate_risk,
        recruiter_verified=recruiter_verified,
        signals=signals,
        warnings=warnings[:20],
        evidence_sources=evidence_sources[:30],
    )
