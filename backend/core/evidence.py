"""Evidence bundle builder (Sprint 3: multi-source verification + honest uncertainty).

Search provider: Serper.dev (google.serper.dev/search) — POST, X-API-KEY header.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from backend.core.extraction import ExtractionResult
from backend.core.normalization import NormalizationResult


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


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_official_domain(domain: str, company_hint: Optional[str]) -> bool:
    if not company_hint or not domain:
        return False
    c_clean = re.sub(r"[^a-z0-9]", "", company_hint.lower())
    d_clean = domain.lower().split(".")[0]
    return c_clean in d_clean or d_clean in c_clean


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


async def _serper_search_async(
    client: httpx.AsyncClient,
    query: str,
    *,
    num: int,
    key: Optional[str],
    endpoint: str,
    timeout_s: int,
    retries: int,
) -> tuple[List[Dict[str, Any]], str, Optional[Dict[str, str]]]:
    if not key:
        return [], "unverified", {"code": "SERPER_UNVERIFIED", "message": "Search API key missing; search signals unverified."}
    
    is_serper = "serper.dev" in endpoint.lower()
    last_error: Optional[str] = None
    
    for _ in range(retries + 1):
        try:
            if is_serper:
                # Serper.dev uses POST + X-API-KEY header
                r = await client.post(
                    endpoint,
                    headers={"X-API-KEY": key, "Content-Type": "application/json", "User-Agent": "JobSignal/1.0"},
                    json={"q": query, "num": min(max(num, 1), 10)},
                    timeout=float(timeout_s),
                )
            else:
                # SerpApi uses GET + api_key param
                r = await client.get(
                    endpoint,
                    params={"api_key": key, "engine": "google", "q": query, "num": min(max(num, 1), 10)},
                    headers={"User-Agent": "JobSignal/1.0"},
                    timeout=float(timeout_s),
                )
            
            if r.status_code in (401, 403, 429):
                return [], "unverified", {
                    "code": "SERPER_UNVERIFIED",
                    "message": "Serper auth/quota/rate-limited; search signals unverified.",
                }
            r.raise_for_status()
            data = r.json()
            # Serper organic results are in 'organic', SerpApi in 'organic_results'
            rows = data.get("organic") if is_serper else data.get("organic_results")
            if not isinstance(rows, list):
                rows = []
            return rows, "verified", None
        except (httpx.HTTPError, ValueError, TypeError) as e:
            last_error = type(e).__name__
    
    return [], "unverified", {"code": "SERPER_UNVERIFIED", "message": f"Serper call failed ({last_error}); search signals unverified."}


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


def build_evidence_bundle(norm: NormalizationResult, ext: ExtractionResult, serp_results: Dict[str, Any]) -> EvidenceBundle:
    signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []
    evidence_sources: List[Dict[str, str]] = []

    official_found = False
    official_url = None
    duplicate_risk = False
    recruiter_verified = False

    company = ext.company_hint or ""
    title = ext.title_hint or ""
    base_query = f"{company} {title}".strip() or (norm.canonical_url or "")

    # This function expects serp_results to be passed in.
    # serp_results is obtained by awaiting _collect_serper_queries in orchestrator.py
    pass

    careers_rows, careers_status, careers_warning = serp_results.get("careers", ([], "unverified", None))
    if careers_warning:
        warnings.append(careers_warning)
    for row in careers_rows:
        link = str(row.get("link") or "").strip()
        if not link.startswith(("http://", "https://")):
            continue
        evidence_sources.append({"url": link, "type": "careers_search", "found_at": _now_iso()})
        domain = urlparse(link).netloc
        if _is_official_domain(domain, ext.company_hint):
            official_found = True
            official_url = link
            break
    careers_strength = "none" if careers_status == "unverified" else ("high" if official_found else "low")
    signals.append(
        _mk_signal(
            sid="careers_page_match",
            label="careers_page_match",
            tier="T1",
            strength=careers_strength,
            detail="unverified" if careers_status == "unverified" else (official_url or "No clear official careers match."),
            status="unknown" if careers_status == "unverified" else ("pass" if official_found else "fail"),
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

    posting_domain = (urlparse(norm.canonical_url).hostname or "").lower() if norm.canonical_url else ""
    careers_domain = (urlparse(official_url).hostname or "").lower() if official_url else ""
    domain_match = bool(posting_domain and careers_domain and posting_domain.split(":")[0].endswith(".".join(careers_domain.split(".")[-2:])))
    signals.append(
        _mk_signal(
            sid="careers_domain_match",
            label="careers_domain_match",
            tier="T1",
            strength="high" if domain_match else ("none" if not posting_domain or not careers_domain else "low"),
            detail="Careers and posting domains align." if domain_match else ("Insufficient domain data to compare." if not posting_domain or not careers_domain else "Careers domain differs from posting domain."),
            status="pass" if domain_match else ("unknown" if not posting_domain or not careers_domain else "fail"),
            source=official_url or norm.canonical_url or "pattern",
        )
    )

    dup_rows, dup_status, dup_warning = serp_results.get("duplicates", ([], "unverified", None))
    if dup_warning:
        warnings.append(dup_warning)
    dup_hosts = {(urlparse(str(r.get("link") or "")).hostname or "").lower() for r in dup_rows if str(r.get("link") or "").startswith(("http://", "https://"))}
    dup_hosts = {h for h in dup_hosts if h}
    duplicate_risk = dup_status == "verified" and len(dup_hosts) >= 3
    signals.append(
        _mk_signal(
            sid="posting_duplication_signal",
            label="posting_duplication_signal",
            tier="T2",
            strength="none" if dup_status == "unverified" else ("low" if duplicate_risk else "high"),
            detail="unverified" if dup_status == "unverified" else f"Posting appears across {len(dup_hosts)} domains.",
            status="unknown" if dup_status == "unverified" else ("fail" if duplicate_risk else "pass"),
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

    if norm.canonical_url and not official_found:
        parsed = urlparse(norm.canonical_url)
        if _is_official_domain(parsed.netloc, ext.company_hint):
            official_found = True
            official_url = norm.canonical_url

    return EvidenceBundle(
        official_page_found=official_found,
        official_url=official_url,
        duplicate_risk=duplicate_risk,
        recruiter_verified=recruiter_verified,
        signals=signals,
        warnings=warnings[:20],
        evidence_sources=evidence_sources[:30],
    )
