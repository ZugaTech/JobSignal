"""Evidence bundle builder (Sprint 10: Evidence-First Architecture).

Collects concrete proof from external sources before LLM synthesis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.core.extraction import ExtractionResult
from backend.core.normalization import NormalizationResult
from backend.core.recommendations import build_provider_chain


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    official_page_found: bool
    official_url: Optional[str]
    duplicate_risk: bool
    recruiter_verified: bool
    signals: List[Dict[str, Any]]
    warnings: List[Dict[str, str]]


def _is_official_domain(domain: str, company_hint: Optional[str]) -> bool:
    if not company_hint or not domain:
        return False
    c_clean = re.sub(r'[^a-z0-9]', '', company_hint.lower())
    d_clean = domain.lower().split('.')[0]
    return c_clean in d_clean or d_clean in c_clean


def build_evidence_bundle(norm: NormalizationResult, ext: ExtractionResult) -> EvidenceBundle:
    signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []
    
    official_found = False
    official_url = None
    duplicate_risk = False
    recruiter_verified = False

    chain = build_provider_chain()
    provider = chain[0] if chain else None

    # Source 1 & 2: Official Careers Page & Domain Search
    if ext.company_hint and ext.title_hint and provider:
        query = f"{ext.company_hint} {ext.title_hint} careers"
        results = provider.search(query, limit=5)
        
        for url in results:
            parsed = urlparse(url)
            domain = parsed.netloc
            if _is_official_domain(domain, ext.company_hint):
                official_found = True
                official_url = url
                signals.append({
                    "id": "official_careers_page",
                    "label": "Official Source Found",
                    "tier": "T1",
                    "strength": "high",
                    "details": f"Found matching role on likely official domain: {domain}"
                })
                break
                
        if not official_found:
            warnings.append({
                "code": "NO_OFFICIAL_SOURCE",
                "message": f"Could not find {ext.title_hint} on {ext.company_hint} official pages."
            })

    # Source 3: Open Web Duplicate Search
    if ext.title_hint and provider:
        query = f'"{ext.title_hint}" job'
        if ext.company_hint:
            query += f' "{ext.company_hint}"'
            
        dup_results = provider.search(query, limit=10)
        # If we see the exact same job on 4+ different job boards, flag as repost risk
        unique_domains = {urlparse(u).netloc for u in dup_results}
        if len(unique_domains) >= 4 and not official_found:
            duplicate_risk = True
            signals.append({
                "id": "duplicate_repost_risk",
                "label": "High Repost Volume",
                "tier": "T3",
                "strength": "low",
                "details": f"Found role listed across {len(unique_domains)} different domains without an official source."
            })

    # Source 4: Recruiter Identity
    if ext.recruiter_name_hint:
        if provider and ext.company_hint:
            query = f'"{ext.recruiter_name_hint}" "{ext.company_hint}" recruiter linkedin'
            rec_results = provider.search(query, limit=2)
            if any("linkedin.com/in/" in u for u in rec_results):
                recruiter_verified = True
                signals.append({
                    "id": "recruiter_verified",
                    "label": "Recruiter Identity",
                    "tier": "T2",
                    "strength": "medium",
                    "details": f"Found professional profile for {ext.recruiter_name_hint} at {ext.company_hint}."
                })
        
        if not recruiter_verified:
            signals.append({
                "id": "recruiter_unverified",
                "label": "Unverified Recruiter",
                "tier": "T3",
                "strength": "low",
                "details": f"Recruiter '{ext.recruiter_name_hint}' mentioned, but identity could not be strongly corroborated."
            })

    # Fallback: if we have a provided URL but it's not verified as official
    if norm.canonical_url and not official_found:
        parsed = urlparse(norm.canonical_url)
        if _is_official_domain(parsed.netloc, ext.company_hint):
            official_found = True
            official_url = norm.canonical_url
            signals.append({
                "id": "official_careers_page",
                "label": "Official Source Provided",
                "tier": "T1",
                "strength": "medium",
                "details": f"Provided URL matches company domain pattern: {parsed.netloc}"
            })

    return EvidenceBundle(
        official_page_found=official_found,
        official_url=official_url,
        duplicate_risk=duplicate_risk,
        recruiter_verified=recruiter_verified,
        signals=signals,
        warnings=warnings
    )
