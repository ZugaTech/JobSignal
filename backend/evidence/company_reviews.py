"""Company reputation and employee review signals layer."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.job_url_shortcuts import is_job_board_brand_label, is_known_job_platform_url
from backend.core.structured_log import logger

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


GLOBAL_RED_TRIGGERS = [
    "mass layoffs", "pip culture", "toxic", "avoid", "run away", "ghost candidates", 
    "never got paid", "scam", "fake job", "fake recruiter", "never responded", 
    "ghosted candidates", "do not apply", "stay away", "micromanagement", "burnout",
    "no work life balance", "underpaid", "low salary", "high turnover", "management is clueless",
    "stagnant growth", "no room for advancement", "favouritism", "nepotism", "unprofessional",
    "disorganized", "fake interview", "bait and switch", "mlm", "pyramid scheme",
    "constant overtime", "work on weekends", "late paychecks", "legal issues",
    "hostile environment", "gaslighting", "no training", "thrown into the deep end",
    "sinking ship", "bankrupt", "hostile workplace", "workplace harassment", "unpaid overtime"
]

GLOBAL_GREEN_TRIGGERS = [
    "great culture", "pays well", "highly recommend", "work life balance", "promotes internally",
    "transparent leadership", "fast growth", "great benefits", "amazing team", "love working here",
    "best job", "incredible onboarding", "remote friendly", "flexible hours", "supportive management",
    "learning opportunities", "competitive salary", "work-life balance", "remote work",
    "work from home", "good perks", "supportive team", "clear goals", "transparent communication",
    "growth opportunities", "professional development", "tuition reimbursement", "generous pto",
    "health insurance", "dental insurance", "vision insurance", "stock options", "equity",
    "rsus", "signing bonus", "annual bonus", "mentorship", "inclusive", "diversity",
    "autonomy", "stable company", "profitable", "market leader", "positive environment",
    "great onboarding", "standardized interview"
]


def _get_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def extract_company_name_hardened(url: Optional[str], text: Optional[str], *, request_id: str = "company_name_extract") -> Optional[str]:
    # Never derive "company" from the job-board hostname (e.g. ng.indeed.com → "Indeed").
    if url and is_known_job_platform_url(url):
        url = None

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

    if text:
        from backend.core.llm_fireworks import _get, llm_enabled
        from backend.core.llm_safe import call_llm_safe_chat_sync

        api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
        llm_enabled_flag = llm_enabled()
        if api_key and llm_enabled_flag:
            try:
                prompt = (
                    "Extract only the hiring company name from this job posting. "
                    "Return only the company name, nothing else. If you cannot determine it, return null.\n\n"
                    f"{text[:2000]}"
                )
                res = call_llm_safe_chat_sync(
                    messages=[{"role": "user", "content": prompt}],
                    fallback="null.",
                    request_id=request_id,
                    model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
                    temperature=0.1,
                    max_tokens=24,
                    timeout=4.0,
                    prose_mode=True,
                    max_chars=120,
                    min_prose_len=1,
                    require_sentence_period=False,
                )
                res_clean = res.strip()
                if res_clean and res_clean.lower().rstrip(".") != "null":
                    if not is_job_board_brand_label(res_clean):
                        return res_clean
            except Exception:
                pass

    if text:
        for m in re.finditer(
            r"(?:About\s+([A-Za-z][A-Za-z0-9&.\- ]+)|Company:\s*([A-Za-z][A-Za-z0-9&.\- ]+))",
            text,
        ):
            for g in (m.group(1), m.group(2)):
                if g:
                    cand = g.strip()
                    if cand and not is_job_board_brand_label(cand):
                        return cand

    return None

def _dedup_flags(flags: List[str], max_flags: int = 4) -> List[str]:
    # Very simple dedup
    seen = set()
    res = []
    for f in flags:
        # naive theme grouping
        low = f.lower()
        key = low
        if "toxic" in low: key = "toxic"
        if "layoff" in low: key = "layoffs"
        if "scam" in low or "fake" in low: key = "scam"
        if key not in seen:
            seen.add(key)
            res.append(f)
            if len(res) >= max_flags:
                break
    return res

async def get_company_reviews(coordinator: Any, company_name: Optional[str], *, request_id: str = "unknown") -> ReviewSummary:
    if (
        not company_name
        or company_name.lower() in ("unknown", "n/a", "none", "null")
        or is_job_board_brand_label(company_name)
    ):
        return ReviewSummary(
            status="company_not_identified",
            message="We could not identify the company name from this posting. Paste the company name manually to enable reputation checks."
        )

    # Six parallel Serper calls (fits tight SEARCH_MAX_CALLS_REPUTATION budgets on Railway).
    # Plain queries only — site: operators often return empty/blocked rows from datacenter egress IPs.
    queries = {
        "reviews_aggregate": f"{company_name} employee reviews ratings Glassdoor Indeed",
        "linkedin_company": f"{company_name} LinkedIn company reviews employees",
        "reddit_culture": f"{company_name} company culture reddit employees",
        "x_layoffs": f"{company_name} layoffs hiring twitter employees",
        "x_watchouts": f"{company_name} workplace toxic scam fake recruiter twitter employees",
        "x_positive": f"{company_name} great place to work reviews twitter employees",
    }

    try:
        tasks = {k: coordinator.search(q, num=5) for k, q in queries.items()}
        # Wait up to 10s for the searches
        results_list = await asyncio.wait_for(asyncio.gather(*tasks.values()), timeout=8.0)
        results = dict(zip(tasks.keys(), results_list))
        timeout_hit = False
    except asyncio.TimeoutError:
        return ReviewSummary(status="unavailable", message="Review pipeline timed out.", timeout=True, partial=True)
    except Exception as e:
        import logging
        logging.error(f"Review pipeline error: {e}")
        return ReviewSummary(status="unavailable", message="Reputation data could not be retrieved for this request.", error_type="internal")

    all_highlights: List[ReviewSource] = []
    platforms_found = set()
    
    reddit_results = []
    x_results = []

    for k, query_res in results.items():
        if query_res is None: continue # dropped by coordinator
        for item in query_res:
            source = _parse_serper_item(item, k)
            if source:
                if source.platform == "Reddit":
                    reddit_results.append(source)
                elif source.platform == "X/Twitter":
                    x_results.append(source)
                else:
                    if source.platform not in platforms_found:
                        all_highlights.append(source)
                        platforms_found.add(source.platform)

    # Process Reddit
    reddit_data = _process_reddit(reddit_results)
    if reddit_data:
        platforms_found.add("Reddit")
    
    # Process X
    x_data = _process_x(x_results)
    if x_data:
        platforms_found.add("X/Twitter")

    if not all_highlights and not reddit_data and not x_data:
        return ReviewSummary(
            review_confidence_score=None,
            overall_sentiment="unknown",
            sources_checked=len(queries),
            sources_found=0,
            plain_summary=_template_summary(company_name, 0, "unknown", None, None),
            sources_unavailable=["Glassdoor", "Indeed", "Trustpilot", "LinkedIn", "Reddit", "X/Twitter"]
        )

    # Score calculation using Reliability table
    score = 50.0
    
    def score_source(sentiment, reliability_weight):
        nonlocal score
        if sentiment == "positive": score += 15 * reliability_weight
        elif sentiment == "mixed": score += 3 * reliability_weight
        elif sentiment == "negative": score -= 15 * reliability_weight

    all_red = []
    all_green = []

    for h in all_highlights:
        w = {"high": 0.9, "medium": 0.7}.get(h.reliability, 0.45)
        if h.platform == "Glassdoor": w = 0.95
        elif h.platform == "Indeed": w = 0.90
        elif h.platform == "LinkedIn": w = 0.80
        elif h.platform == "Trustpilot": w = 0.65
        score_source(h.sentiment, w)
        
        text = (h.snippet + " " + (h.post_title or "")).lower()
        has_green = False
        has_red = False
        
        for t in GLOBAL_RED_TRIGGERS:
            if t in text:
                all_red.append(f"{t} (via {h.platform})")
                has_red = True
                
        for t in GLOBAL_GREEN_TRIGGERS:
            if t in text:
                all_green.append(f"{t} (via {h.platform})")
                has_green = True
                
        if h.sentiment == "negative" and not has_red:
            all_red.append(f"Negative feedback on {h.platform} (via {h.platform})")
        if h.sentiment == "positive" and not has_green:
            all_green.append(f"Positive feedback on {h.platform} (via {h.platform})")

    if reddit_data:
        score_source(reddit_data["sentiment"].replace("mostly ", ""), 0.70)
        for r in reddit_data["red_flags_found"]: all_red.append(f"{r} (via Reddit)")
        for g in reddit_data["green_flags_found"]: all_green.append(f"{g} (via Reddit)")
        
    if x_data:
        score_source(x_data["sentiment"].replace("mostly ", ""), 0.55)
        for r in x_data["red_flags_found"]: all_red.append(f"{r} (via X)")
        for g in x_data["green_flags_found"]: all_green.append(f"{g} (via X)")

    red_dedup = _dedup_flags(all_red, 4)
    green_dedup = _dedup_flags(all_green, 4)
    
    score -= 10 * len(red_dedup)
    score += min(20, 5 * len(green_dedup))
    
    final_score = int(min(max(score, 0), 100))

    positive_count = sum(1 for h in all_highlights if h.sentiment == "positive") + (1 if reddit_data and "positive" in reddit_data["sentiment"] else 0)
    negative_count = sum(1 for h in all_highlights if h.sentiment == "negative") + (1 if reddit_data and "negative" in reddit_data["sentiment"] else 0)
    
    overall_sentiment = "mixed"
    if positive_count > negative_count * 2: overall_sentiment = "mostly positive"
    elif negative_count > positive_count: overall_sentiment = "mostly negative"

    plain_summary = await _generate_llm_summary(company_name, all_highlights + reddit_results + x_results, request_id=request_id)
    if not plain_summary:
        top_red = red_dedup[0] if red_dedup else None
        top_green = green_dedup[0] if green_dedup else None
        plain_summary = _template_summary(company_name, len(platforms_found), overall_sentiment, top_green, top_red)

    sources_unavailable = [p for p in ["Glassdoor", "Indeed", "Trustpilot", "LinkedIn", "Reddit", "X/Twitter"] if p not in platforms_found]

    return ReviewSummary(
        review_confidence_score=final_score,
        overall_sentiment=overall_sentiment,
        sources_checked=len(queries),
        sources_found=len(platforms_found),
        highlights=[{
            "platform": h.platform,
            "rating": h.rating,
            "review_count": h.review_count,
            "sentiment": h.sentiment,
            "snippet": h.snippet,
            "reliability": h.reliability
        } for h in all_highlights],
        red_flags=red_dedup,
        green_flags=green_dedup,
        plain_summary=plain_summary,
        sources_unavailable=sources_unavailable,
        reddit=reddit_data,
        x_twitter=x_data
    )

def _template_summary(company: str, count: int, sentiment: str, green: Optional[str], red: Optional[str]) -> str:
    """Template fallback when reputation LLM output is unavailable or invalid (never assign raw prompts here)."""
    green_text = green if green else "No standout positive themes appeared in the snippets we saw."
    if count == 0:
        base = (
            f"Public employer reputation data was sparse for {company}, so we could not summarize sentiment reliably. "
            "That usually means independent reviews were hard to find—not that the employer is problematic."
        )
        if red:
            return f"{base} Note: {red}."
        return base
    summary = f"Drawing on {count} public sources, {company} skews toward a {sentiment} employer reputation. {green_text}."
    if red:
        summary += f" {red}."
    return summary

def _process_reddit(results: List[ReviewSource]) -> Optional[Dict[str, Any]]:
    if not results: return None
    
    pos = 0
    neg = sum(1 for r in results if r.sentiment == "negative")
    neu = sum(1 for r in results if r.sentiment == "neutral" or r.sentiment == "mixed")
    
    phrases = []
    reds = []
    greens = []

    for r in results:
        text = (r.snippet + " " + (r.post_title or "")).lower()
        has_green = False
        for t in GLOBAL_RED_TRIGGERS:
            if t in text and t not in reds: reds.append(t)
        for t in GLOBAL_GREEN_TRIGGERS:
            if t in text:
                has_green = True
                if t not in greens: greens.append(t)
                
        if r.sentiment == "positive" or has_green:
            pos += 1
            
        m = re.search(r"\"([^\"]{10,60})\"", r.snippet)
        if m and len(phrases) < 3:
            p_text = m.group(1)
            p_lower = p_text.lower()
            p_sent = "neutral"
            if any(t in p_lower for t in GLOBAL_GREEN_TRIGGERS) or r.sentiment == "positive": p_sent = "positive"
            if any(t in p_lower for t in GLOBAL_RED_TRIGGERS) or r.sentiment == "negative": p_sent = "negative"
            phrases.append({"text": p_text, "sentiment": p_sent})
            
    sent = "mixed"
    if pos > neg * 2: sent = "mostly positive"
    elif neg > pos: sent = "mostly negative"

    if sent in ("positive", "mostly positive") and not greens:
        greens.append("Positive employer sentiment found on Reddit")
            
    if not phrases and results:
        p_text = results[0].snippet[:40] + "..."
        p_sent = results[0].sentiment
        phrases.append({"text": p_text, "sentiment": p_sent})
        
    phrases.sort(key=lambda x: {"positive": 0, "negative": 1, "neutral": 2, "mixed": 2}.get(x["sentiment"], 2))
        
    return {
        "found": True,
        "positive_mentions": pos,
        "negative_mentions": neg,
        "neutral_mentions": neu,
        "sentiment": sent,
        "notable_phrases": phrases[:3],
        "red_flags_found": reds,
        "green_flags_found": greens,
        "reliability": "medium-high"
    }

def _process_x(results: List[ReviewSource]) -> Optional[Dict[str, Any]]:
    if not results: return None

    pos = 0
    neg = sum(1 for r in results if r.sentiment == "negative")
    red_counts = {}
    green_counts = {}

    for r in results:
        text = r.snippet.lower()
        has_green = False
        for t in GLOBAL_RED_TRIGGERS:
            if t in text: red_counts[t] = red_counts.get(t, 0) + 1
        for t in GLOBAL_GREEN_TRIGGERS:
            if t in text:
                green_counts[t] = green_counts.get(t, 0) + 1
                has_green = True
                
        if r.sentiment == "positive" or has_green:
            pos += 1
                
    reds = [t for t, c in red_counts.items() if c >= 2]
    greens = [t for t, c in green_counts.items() if c >= 2]
    
    sent = "mixed"
    if pos > neg: sent = "mostly positive"
    elif neg > pos: sent = "mostly negative"

    if sent in ("positive", "mostly positive") and not greens:
        greens.append("Positive employer sentiment found on X (Twitter)")
            
    phrases = []
    if results:
        for r in results[:2]:
            p_text = r.snippet[:50] + "..."
            p_lower = p_text.lower()
            p_sent = "neutral"
            if any(t in p_lower for t in GLOBAL_GREEN_TRIGGERS) or r.sentiment == "positive": p_sent = "positive"
            if any(t in p_lower for t in GLOBAL_RED_TRIGGERS) or r.sentiment == "negative": p_sent = "negative"
            phrases.append({"text": p_text, "sentiment": p_sent})
            
    phrases.sort(key=lambda x: {"positive": 0, "negative": 1, "neutral": 2, "mixed": 2}.get(x["sentiment"], 2))
            
    return {
        "found": True,
        "sentiment": sent,
        "notable_phrases": phrases[:2],
        "red_flags_found": reds,
        "green_flags_found": greens,
        "reliability": "low-medium",
        "note": f"X signals are weighted lower due to noise. Corroborated by {max(0, len(results)-1)} other source(s)."
    }

def _parse_serper_item(item: Dict[str, Any], query_key: str) -> Optional[ReviewSource]:
    snippet = item.get("snippet", "")
    link = item.get("link", "").lower()
    title = item.get("title", "").lower()
    
    platform = "Web"
    reliability = "low"
    
    if "reddit" in query_key or "reddit.com" in link:
        platform = "Reddit"
        reliability = "medium"
    elif "x_" in query_key or "twitter.com" in link or "x.com" in link:
        platform = "X/Twitter"
        reliability = "low"
    elif "glassdoor.com" in link:
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
        return None

    rating: Optional[float] = None
    review_count: Optional[int] = None
    
    rating_match = re.search(r"Rating:? (\d\.\d)", snippet) or re.search(r"(\d\.\d) out of 5", snippet)
    if rating_match: rating = float(rating_match.group(1))
    
    count_match = re.search(r"(\d+[\d,]*) reviews", snippet)
    if count_match: review_count = int(count_match.group(1).replace(",", ""))

    sentiment = "unknown"
    pos_words = ["great", "positive", "love", "good", "recommend", "growth", "culture", "stable", "pays well"]
    neg_words = ["toxic", "poor", "bad", "underpaid", "layoffs", "management", "turnover", "scam", "avoid", "run"]
    
    text = (title + " " + snippet).lower()
    pos_score = sum(1 for w in pos_words if w in text)
    neg_score = sum(1 for w in neg_words if w in text)
    
    pos_score += sum(2 for w in GLOBAL_GREEN_TRIGGERS if w in text)
    neg_score += sum(2 for w in GLOBAL_RED_TRIGGERS if w in text)
    
    if pos_score > neg_score: sentiment = "positive"
    elif neg_score > pos_score: sentiment = "negative"
    elif pos_score > 0: sentiment = "mixed"
    else: sentiment = "neutral"

    return ReviewSource(
        platform=platform,
        rating=rating,
        review_count=review_count,
        sentiment=sentiment,
        snippet=snippet,
        reliability=reliability,
        post_title=title
    )


async def _generate_llm_summary(
    company: str, highlights: List[ReviewSource], *, request_id: str = "unknown"
) -> Optional[str]:
    from backend.core.llm_fireworks import _get, llm_enabled
    from backend.core.llm_safe import call_llm_safe

    api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    llm_enabled_flag = llm_enabled()
    if not api_key or not llm_enabled_flag:
        return None

    context = "\n".join([f"- {h.platform} ({h.sentiment}): {h.snippet}" for h in highlights[:10]])
    user_content = f"Company: {company}\nData:\n{context}"

    pos = sum(1 for h in highlights if h.sentiment == "positive")
    neg = sum(1 for h in highlights if h.sentiment == "negative")
    if pos > neg:
        overall_guess = "positive"
    elif neg > pos:
        overall_guess = "negative"
    else:
        overall_guess = "mixed"

    display_company = company.strip() if company.strip() else "The employer behind this posting"
    top_green_snip = next((h.snippet for h in highlights if h.sentiment == "positive"), None)
    top_red_snip = next((h.snippet for h in highlights if h.sentiment == "negative"), None)
    green_clause = (
        (top_green_snip[:160].rsplit(" ", 1)[0] + ".")
        if top_green_snip
        else "No strong positive signals were found."
    )
    red_clause = (
        (top_red_snip[:160].rsplit(" ", 1)[0] + ".")
        if top_red_snip
        else "No major concerns were detected."
    )
    fallback_txt = (
        f"Based on {len(highlights)} sources, {display_company} shows a {overall_guess} employer reputation. "
        f"{green_clause} {red_clause}"
    )

    summary_text = await call_llm_safe(
        messages=[
            {
                "role": "system",
                "content": "You are a recruiter briefing a candidate. Write a 2-3 sentence employer reputation briefing. No jargon. No instructions. Output ONLY the briefing text.",
            },
            {"role": "user", "content": user_content},
        ],
        fallback=fallback_txt,
        request_id=request_id,
        model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
        temperature=0.3,
        max_tokens=150,
        timeout=8.0,
    )
    if "Summary:" in summary_text:
        summary_text = summary_text.split("Summary:")[-1].strip()
    return summary_text or None
