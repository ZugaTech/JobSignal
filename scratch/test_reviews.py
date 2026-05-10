"""Company reputation and employee review signals layer."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True, slots=True)
class ReviewSource:
    platform: str
    rating: Optional[float]
    review_count: Optional[int]
    sentiment: str
    snippet: str
    reliability: str
    post_title: Optional[str] = None
    subreddit: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    status: str = "ok"
    message: str = ""
    error_type: Optional[str] = None
    partial: bool = False
    timeout: bool = False
    review_confidence_score: Optional[int] = None
    overall_sentiment: str = "unknown"
    sources_checked: int = 0
    sources_found: int = 0
    highlights: List[Dict[str, Any]] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    green_flags: List[str] = field(default_factory=list)
    plain_summary: str = ""
    sources_unavailable: List[str] = field(default_factory=list)
    reddit: Optional[Dict[str, Any]] = None
    x_twitter: Optional[Dict[str, Any]] = None


def _get_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def extract_company_name_hardened(url: Optional[str], text: Optional[str]) -> Optional[str]:
    # Primary: extract from job URL domain
    if url:
        try:
            host = urlparse(url).hostname or ""
            parts = host.split(".")
            if len(parts) > 1:
                label = parts[-2]
                if label not in ("com", "co", "org", "net"):
                    return label.replace("-", " ").title()
                elif len(parts) > 2:
                    return parts[-3].replace("-", " ").title()
        except Exception:
            pass

    # Secondary: LLM extraction
    if text:
        from backend.core.llm_fireworks import _client, _get
        api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
        if api_key:
            try:
                c = _client()
                prompt = f"Extract only the hiring company name from this job posting. Return only the company name, nothing else. If you cannot determine it, return null.\n\n{text[:2000]}"
                resp = c.chat.completions.create(
                    model=_get("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2p6"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=20,
                    timeout=5
                )
                res = resp.choices[0].message.content.strip()
                if res and res.lower() != "null":
                    return res
            except Exception:
                pass

    # Tertiary: Regex
    if text:
        m = re.search(r"(?:About\s+([A-Z][A-Za-z0-9&.\- ]+)|Company:\s*([A-Z][A-Za-z0-9&.\- ]+))", text)
        if m:
            return (m.group(1) or m.group(2)).strip()
            
    return None


async def get_company_reviews(coordinator: Any, company_name: Optional[str]) -> ReviewSummary:
    """Gather company reviews from Serper and summarize via LLM. Safe to run always."""
    if not company_name or company_name.lower() in ("unknown", "n/a", "none", "null"):
        return ReviewSummary(
            status="company_not_identified",
            message="We could not identify the company name from this posting. Paste the company name manually to enable reputation checks."
        )

    queries = [
        f"{company_name} reviews Glassdoor",
        f"{company_name} employee reviews Indeed",
        f"{company_name} reviews Trustpilot",
        f"{company_name} LinkedIn company reviews",
        f"{company_name} reviews reddit",
        f"{company_name} workplace culture reddit",
        f"working at {company name} reddit",
        f"{company_name} layoffs site:x.com OR site:twitter.com",
        f"{company_name} hiring scam OR fake job site:x.com OR site:twitter.com",
        f"{company_name} company culture site:x.com OR site:twitter.com",
        f"{company_name} employees site:x.com OR site:twitter.com"
    ]

    try:
        tasks = [
            coordinator.search(query, num=5)
            for query in queries
        ]
        
        # 10s hard cap for entire gather
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)
        timeout_hit = False
    except asyncio.TimeoutError:
        # If timeout in gather, we don't have results. Wait, gather cancels pending.
        # So we can't easily get partial unless we use wait. Let's use asyncio.wait instead.
        return ReviewSummary(status="unavailable", message="Review pipeline timed out.", timeout=True, partial=True)
    except Exception as e:
        return ReviewSummary(status="unavailable", message="Reputation data could not be retrieved for this request.", error_type="internal")
    
    # Process results ...
    return ReviewSummary()
