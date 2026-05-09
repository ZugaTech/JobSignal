from __future__ import annotations

import json
import os
import re
import asyncio
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Awaitable
from urllib.parse import urlparse

import httpx

from backend.core.image_ingest import ExtractedVisionFields
from backend.core.normalization import NormalizationResult, normalize_job_url
from backend.core.coordinator import EvidenceCoordinator

RECOMMENDATIONS_VERSION = "1.1.0"
_HARD_MAX_RECOMMENDATIONS = 3


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


def any_search_configured() -> bool:
    return bool(_get("SERPER_API_KEY") or _get("SEARCH_API_KEY"))


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


class SearchProvider(Protocol):
    name: str

    async def search(self, coordinator: EvidenceCoordinator, query: str, *, limit: int) -> List[Dict[str, Any]]: ...


class SerperDiscoveryProvider:
    name = "serper"

    async def search(self, coordinator: EvidenceCoordinator, query: str, *, limit: int) -> List[Dict[str, Any]]:
        # This will use the shared coordinator to respect call budget
        results = await coordinator.search(query)
        out = []
        for r in results:
            if not r.get("link"):
                continue
            title_raw = (r.get("title") or "").strip()
            company_raw = (r.get("company") or r.get("source") or "").strip()
            out.append({
                "title": title_raw or "Job title not provided by search.",
                "company": company_raw or "Employer name not provided by search.",
                "url": r.get("link"),
                "platform": r.get("source") or urlparse(r.get("link")).netloc,
                "snippet": r.get("snippet", "")
            })
        return out[:limit]


async def build_recommendations(
    coordinator: EvidenceCoordinator,
    normalized: NormalizationResult,
    *,
    extracted: Optional[ExtractedVisionFields] = None,
    max_results: int = 3
) -> List[Dict[str, Any]]:
    """Discover similar jobs using official sources and cross-platform signals."""
    
    if not any_search_configured():
        return []

    # Use titles/company from normalized or extracted vision
    job_title = normalized.title or (extracted.job_title if extracted else None)
    company_name = normalized.company or (extracted.company_name if extracted else None)
    
    if not job_title:
        return []

    # Filter out common generic noise
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', job_title).strip()
    
    # Core discovery query: title + optional company + trusted platforms
    # We want results from major job boards or official careers pages
    query = f'"{clean_title}" jobs'
    if company_name:
        query += f' "{company_name}"'
    
    query += " site:linkedin.com OR site:indeed.com OR site:greenhouse.io OR site:lever.co"

    provider = SerperDiscoveryProvider()
    try:
        # We cap candidate pool to avoid blowing budget on one provider
        candidates = await provider.search(coordinator, query, limit=candidate_pool_limit())
        
        # Deduplicate by normalized URL
        seen_urls = set()
        if normalized.url:
            seen_urls.add(normalize_job_url(normalized.url))
            
        final = []
        for c in candidates:
            norm_c = normalize_job_url(c["url"])
            if norm_c in seen_urls:
                continue
            seen_urls.add(norm_c)
            final.append(c)
            if len(final) >= max_results:
                break
        
        return final
    except Exception:
        # Graceful failure for discovery - don't crash verification
        return []


async def extend_report_with_recommendations(
    report: Dict[str, Any],
    normalized: NormalizationResult,
    extracted: Optional[ExtractedVisionFields],
    *,
    user_requested: Optional[bool],
    verify_candidate: Callable[[str], Awaitable[Dict[str, Any]]],
    coordinator: Optional[EvidenceCoordinator] = None
) -> None:
    """Orchestrates the discovery and optional verification of similar jobs."""
    if not user_requested or not coordinator:
        return

    # 1. Discover candidates
    candidates = await build_recommendations(
        coordinator,
        normalized,
        extracted=extracted,
        max_results=effective_recommendations_max()
    )
    
    if not candidates:
        report["recommendations"] = []
        return

    # 2. Parallel verification (Sprint 9 logic)
    tasks = [verify_candidate(c["url"]) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    verified_list = []
    for i, res in enumerate(results):
        cand = candidates[i]
        if isinstance(res, dict) and res.get("verdict"):
            cand["verdict"] = res["verdict"]
            cand["confidence"] = res.get("confidence_score") or res.get("confidence")
        verified_list.append(cand)
        
    report["recommendations"] = verified_list
