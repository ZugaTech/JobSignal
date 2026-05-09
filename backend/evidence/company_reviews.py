"""Company reputation and employee review signals layer."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass(frozen=True, slots=True)
class ReviewSource:
    platform: str
    rating: Optional[float]
    review_count: Optional[int]
    sentiment: str
    snippet: str
    reliability: str


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    review_confidence_score: Optional[int]
    overall_sentiment: str
    sources_checked: int
    sources_found: int
    highlights: List[Dict[str, Any]]
    red_flags: List[str]
    green_flags: List[str]
    plain_summary: str
    sources_unavailable: List[str]


def _get_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


async def get_company_reviews(company_name: str) -> Optional[ReviewSummary]:
    """Gather company reviews from Serper and summarize via LLM."""
    if not company_name or company_name.lower() in ("unknown", "n/a", "none"):
        return None

    api_key = _get_env("SERPER_API_KEY") or _get_env("SEARCH_API_KEY")
    if not api_key:
        return None

    queries = [
        f"{company_name} reviews Glassdoor",
        f"{company_name} employee reviews Indeed",
        f"{company_name} reviews Trustpilot",
        f"{company_name} LinkedIn company reviews",
        f"{company_name} reviews site:glassdoor.com OR site:indeed.com OR site:trustpilot.com",
    ]

    async with httpx.AsyncClient() as client:
        tasks = [
            _serper_search(client, query, api_key)
            for query in queries
        ]
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=8.0)
        except asyncio.TimeoutError:
            # Partial results or empty if timeout
            results = []

    all_highlights: List[ReviewSource] = []
    platforms_found = set()
    
    for query_res in results:
        for item in query_res:
            source = _parse_serper_item(item)
            if source and source.platform not in platforms_found:
                all_highlights.append(source)
                platforms_found.add(source.platform)

    if not all_highlights:
        return ReviewSummary(
            review_confidence_score=None,
            overall_sentiment="unknown",
            sources_checked=len(queries),
            sources_found=0,
            highlights=[],
            red_flags=[],
            green_flags=[],
            plain_summary="Company reputation data unavailable for this posting.",
            sources_unavailable=["Glassdoor", "Indeed", "Trustpilot", "LinkedIn"],
        )

    # Calculate Score
    score = 50.0
    for h in all_highlights:
        weight = 0.5
        if "glassdoor" in h.platform.lower(): weight = 0.95
        elif "indeed" in h.platform.lower(): weight = 0.90
        elif "linkedin" in h.platform.lower(): weight = 0.80
        elif "trustpilot" in h.platform.lower(): weight = 0.65
        
        if h.rating is not None:
            if h.rating >= 4.0: score += 15 * weight
            elif h.rating >= 3.0: score += 5 * weight
            elif h.rating >= 2.0: score -= 10 * weight
            else: score -= 20 * weight
    
    final_score = int(min(max(score, 0), 100))

    # Sentiment & Flags (Simple logic before LLM summary)
    red_flags = []
    green_flags = []
    positive_count = sum(1 for h in all_highlights if h.sentiment == "positive")
    negative_count = sum(1 for h in all_highlights if h.sentiment == "negative")
    
    if positive_count >= 2:
        green_flags.append("Consistent positive ratings across platforms")
    if negative_count >= 1:
        red_flags.append("Some negative employee feedback detected")

    overall_sentiment = "mixed"
    if positive_count > negative_count * 2: overall_sentiment = "mostly positive"
    elif negative_count > positive_count: overall_sentiment = "mostly negative"

    # LLM Summary
    plain_summary = await _generate_llm_summary(company_name, all_highlights)

    sources_unavailable = [p for p in ["Glassdoor", "Indeed", "Trustpilot", "LinkedIn"] if p not in platforms_found]

    return ReviewSummary(
        review_confidence_score=final_score,
        overall_sentiment=overall_sentiment,
        sources_checked=len(queries),
        sources_found=len(all_highlights),
        highlights=[{
            "platform": h.platform,
            "rating": h.rating,
            "review_count": h.review_count,
            "sentiment": h.sentiment,
            "snippet": h.snippet,
            "reliability": h.reliability
        } for h in all_highlights],
        red_flags=red_flags,
        green_flags=green_flags,
        plain_summary=plain_summary,
        sources_unavailable=sources_unavailable,
    )


async def _serper_search(client: httpx.AsyncClient, query: str, api_key: str) -> List[Dict[str, Any]]:
    try:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=5.0
        )
        if r.status_code == 200:
            return r.json().get("organic", [])
    except Exception:
        pass
    return []


def _parse_serper_item(item: Dict[str, Any]) -> Optional[ReviewSource]:
    snippet = item.get("snippet", "")
    link = item.get("link", "").lower()
    title = item.get("title", "").lower()
    
    platform = "Web"
    reliability = "low"
    
    if "glassdoor.com" in link:
        platform = "Glassdoor"
        reliability = "high"
    elif "indeed.com" in link:
        platform = "Indeed"
        reliability = "high"
    elif "linkedin.com" in link:
        platform = "LinkedIn"
        reliability = "medium"
    elif "trustpilot.com" in link:
        platform = "Trustpilot"
        reliability = "medium"
    else:
        return None # Only track key platforms for now to keep summary clean

    # Extract rating e.g. "Rating: 4.1 - 832 reviews" or "4.1 (832)"
    rating: Optional[float] = None
    review_count: Optional[int] = None
    
    rating_match = re.search(r"Rating:? (\d\.\d)", snippet) or re.search(r"(\d\.\d) out of 5", snippet)
    if rating_match:
        rating = float(rating_match.group(1))
    
    count_match = re.search(r"(\d+[\d,]*) reviews", snippet)
    if count_match:
        review_count = int(count_match.group(1).replace(",", ""))

    # Basic sentiment keyword check
    sentiment = "unknown"
    pos_words = ["great", "positive", "love", "good", "recommend", "growth", "culture", "stable"]
    neg_words = ["toxic", "poor", "bad", "underpaid", "layoffs", "management", "turnover", "scam"]
    
    text = (title + " " + snippet).lower()
    pos_score = sum(1 for w in pos_words if w in text)
    neg_score = sum(1 for w in neg_words if w in text)
    
    if pos_score > neg_score: sentiment = "positive"
    elif neg_score > pos_score: sentiment = "negative"
    elif pos_score > 0: sentiment = "mixed"

    return ReviewSource(
        platform=platform,
        rating=rating,
        review_count=review_count,
        sentiment=sentiment,
        snippet=snippet,
        reliability=reliability
    )


async def _generate_llm_summary(company: str, highlights: List[ReviewSource]) -> str:
    from backend.core.llm_fireworks import _client, _get
    
    api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    if not api_key:
        return "Employer reputation looks stable based on available web signals."

    context = "\n".join([f"- {h.platform} ({h.rating or 'N/A'} stars): {h.snippet}" for h in highlights])
    
    prompt = (
        f"You are a recruiter briefing a candidate on the employer reputation for '{company}'.\n"
        "Based on these employee review snippets, write a 2-3 sentence summary.\n"
        "Be honest, direct, and avoid corporate language.\n\n"
        "REVIEW DATA:\n"
        f"{context}\n\n"
        "Summary:"
    )
    
    try:
        c = _client()
        resp = c.chat.completions.create(
            model=_get("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2p5"),
            messages=[
                {"role": "system", "content": "Write like a recruiter briefing a candidate: honest, direct, no corporate language."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
            timeout=10
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        # Fallback
        return f"Reviews for {company} suggest a {highlights[0].sentiment if highlights else 'mixed'} sentiment overall. Sources checked include {', '.join([h.platform for h in highlights[:2]])}."
