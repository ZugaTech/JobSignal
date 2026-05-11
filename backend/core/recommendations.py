from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urlparse

from backend.core.coordinator import EvidenceCoordinator
from backend.core.job_discovery_urls import is_job_posting_discovery_candidate
from backend.core.extraction import ExtractionResult, extract_entities
from backend.core.image_ingest import ExtractedVisionFields
from backend.core.normalization import NormalizationResult, normalize_job_url

RECOMMENDATIONS_VERSION = "1.3.0"
_HARD_MAX_RECOMMENDATIONS = 3

_LINKEDIN_VIEW_ID = re.compile(r"linkedin\.com/jobs/view/(\d+)", re.I)


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def any_search_configured() -> bool:
    return bool(_get("SERPER_API_KEY") or _get("SEARCH_API_KEY") or _get("SERPAPI_API_KEY"))


def env_recommendations_default_on() -> bool:
    return (_get("RECOMMENDATIONS_ENABLED", "0") or "0").lower() in ("1", "true", "yes", "on")


def effective_recommendations_max() -> int:
    try:
        n = int(_get("RECOMMENDATIONS_MAX", str(_HARD_MAX_RECOMMENDATIONS)) or _HARD_MAX_RECOMMENDATIONS)
    except ValueError:
        n = _HARD_MAX_RECOMMENDATIONS
    return max(1, min(n, _HARD_MAX_RECOMMENDATIONS))


def candidate_pool_limit() -> int:
    try:
        n = int(_get("RECOMMENDATIONS_CANDIDATE_POOL", "8") or "8")
    except ValueError:
        n = 8
    return max(3, min(n, 20))


def recommendations_min_verify_score() -> int:
    """Minimum nested verify confidence_score (0–100) for a similar job to be shown."""
    try:
        n = int(_get("RECOMMENDATIONS_MIN_VERIFY_SCORE", "55") or "55")
    except ValueError:
        n = 70
    return max(0, min(100, n))


def _canonical_url_string(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    u, _h = normalize_job_url(raw)
    return u


def _linkedin_job_view_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = _LINKEDIN_VIEW_ID.search(url)
    return m.group(1) if m else None


def _resolve_title_company(
    extracted: Optional[ExtractedVisionFields],
    ext: ExtractionResult,
) -> tuple[Optional[str], Optional[str]]:
    jt: Optional[str] = None
    cn: Optional[str] = None
    if extracted:
        jt = (extracted.job_title or "").strip() or None
        cn = (extracted.company_name or "").strip() or None
    if not jt:
        jt = ext.title_hint
    if not cn:
        cn = ext.company_hint
    return jt, cn


def _build_discovery_query(
    normalized: NormalizationResult,
    extracted: Optional[ExtractedVisionFields],
    ext: ExtractionResult,
) -> Optional[str]:
    job_title, company_name = _resolve_title_company(extracted, ext)

    if job_title:
        clean_title = re.sub(r"\(.*?\)|\[.*?\]", "", job_title).strip()
        if clean_title:
            q = f'"{clean_title}" (jobs OR careers OR hiring)'
            if company_name:
                q += f' "{company_name}"'
            q += " (site:linkedin.com/jobs OR site:indeed.com OR site:greenhouse.io OR site:lever.co OR site:workdayjobs.com)"
            return q

    domain = (normalized.registrable_domain or "").strip()
    if company_name:
        q = f'"{company_name}" (jobs OR careers OR hiring)'
        q += " (site:linkedin.com/jobs OR site:indeed.com OR site:greenhouse.io OR site:lever.co OR site:workdayjobs.com)"
        return q

    if domain:
        q = f"site:{domain} (jobs OR careers OR hiring)"
        return q

    canonical = normalized.canonical_url or ""
    li_id = _linkedin_job_view_id(canonical)
    if li_id:
        return (
            f'"{li_id}" jobs site:linkedin.com OR site:indeed.com '
            "OR site:greenhouse.io OR site:lever.co OR site:workdayjobs.com"
        )

    host = (urlparse(canonical).hostname or "").lower()
    if host:
        return (
            f'"{host}" jobs hiring '
            "site:linkedin.com/jobs OR site:indeed.com OR site:greenhouse.io OR site:lever.co OR site:workdayjobs.com"
        )

    return None


class SerperDiscoveryProvider:
    name = "serper"

    async def search(self, coordinator: EvidenceCoordinator, query: str, *, limit: int) -> List[Dict[str, Any]]:
        results = await coordinator.search(query)
        out = []
        for r in results or []:
            if not r.get("link"):
                continue
            title_raw = (r.get("title") or "").strip()
            company_raw = (r.get("company") or r.get("source") or "").strip()
            out.append({
                "title": title_raw or "Job title not provided by search.",
                "company": company_raw or "Employer name not provided by search.",
                "url": r.get("link"),
                "platform": r.get("source") or urlparse(r.get("link")).netloc,
                "snippet": r.get("snippet", ""),
            })
        return out[:limit]


async def build_recommendations(
    coordinator: EvidenceCoordinator,
    normalized: NormalizationResult,
    *,
    extracted: Optional[ExtractedVisionFields] = None,
    max_collect: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Discover candidate similar-job URLs before nested verification."""
    if not any_search_configured():
        return []

    ext = extract_entities(normalized)
    query = _build_discovery_query(normalized, extracted, ext)
    if not query:
        return []

    pool = max_collect if max_collect is not None else candidate_pool_limit()
    provider = SerperDiscoveryProvider()
    try:
        candidates = await provider.search(coordinator, query, limit=pool)
        seen_urls: set[str] = set()
        seed = _canonical_url_string(normalized.canonical_url)
        if seed:
            seen_urls.add(seed)

        final: List[Dict[str, Any]] = []
        for c in candidates:
            raw_link = c.get("url")
            if not raw_link:
                continue
            if not is_job_posting_discovery_candidate(str(raw_link)):
                continue
            nu = _canonical_url_string(str(raw_link))
            if not nu or nu in seen_urls:
                continue
            seen_urls.add(nu)
            final.append(c)
            if len(final) >= pool:
                break
        return final
    except Exception:
        return []


def _nested_confidence_score(report: Dict[str, Any]) -> Optional[int]:
    raw = report.get("confidence_score")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def extend_report_with_recommendations(
    report: Dict[str, Any],
    normalized: NormalizationResult,
    extracted: Optional[ExtractedVisionFields],
    *,
    user_requested: Optional[bool],
    verify_candidate: Callable[[str], Awaitable[Dict[str, Any]]],
    coordinator: Optional[EvidenceCoordinator] = None,
) -> None:
    """Discover candidates, nested-verify each, keep only high-confidence non-SKIP rows."""
    if not user_requested or not coordinator:
        return

    min_score = recommendations_min_verify_score()
    candidates = await build_recommendations(coordinator, normalized, extracted=extracted)

    if not candidates:
        report["recommendations"] = []
        report["meta"] = dict(report.get("meta") or {})
        report["meta"]["recommendations_status"] = "empty"
        report["meta"]["recommendations_version"] = RECOMMENDATIONS_VERSION
        return

    tasks = [verify_candidate(str(c["url"])) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored: List[Dict[str, Any]] = []
    for i, res in enumerate(results):
        cand = dict(candidates[i])
        if isinstance(res, BaseException) or not isinstance(res, dict):
            continue
        verdict = str(res.get("verdict") or "").upper()
        cs = _nested_confidence_score(res)
        if verdict == "SKIP":
            continue
        if cs is None or cs < min_score:
            continue
        cand["verdict"] = verdict
        cand["confidence_score"] = cs
        cand["recommendation_note"] = "Verified similar posting at high confidence."
        scored.append(cand)

    scored.sort(key=lambda x: int(x.get("confidence_score") or 0), reverse=True)
    cap = effective_recommendations_max()
    report["recommendations"] = scored[:cap]
    report["meta"] = dict(report.get("meta") or {})
    report["meta"]["recommendations_status"] = "ok" if report["recommendations"] else "empty"
    report["meta"]["recommendations_version"] = RECOMMENDATIONS_VERSION
    report["meta"]["recommendations_min_verify_score"] = min_score
