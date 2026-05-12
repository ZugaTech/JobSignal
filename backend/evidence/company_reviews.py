"""Company reputation and employee review signals layer."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.core.employer_hints import merge_curated_baseline
from backend.core.employer_llm_noise import employer_label_is_llm_noise
from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.job_url_shortcuts import is_job_board_brand_label, is_known_job_platform_url
from backend.core.prompt_guard import is_prompt_leak

logger = logging.getLogger("jobsignal")

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
    # How the reputation panel was produced (hybrid pipeline). List, not tuple, so
    # JSON serializers always emit a real array on the wire — frontends read ds[0] directly.
    data_sources: List[str] = field(default_factory=list)
    reliability_report: str = ""


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

def is_company_relevant(result: Dict[str, Any], company_name: str) -> bool:
    """Snippets often omit the legal entity string; allow token overlap for known employer names."""

    text = f"{result.get('snippet', '')} {result.get('title', '')}".lower()
    company_lower = (company_name or "").strip().lower()
    if not company_lower:
        return False
    if company_lower in text:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9]+", company_lower) if len(t) >= 3]
    if not tokens:
        return False
    matches = sum(1 for t in tokens if t in text)
    need = max(1, (len(tokens) + 1) // 2)
    return matches >= need


def count_relevant_negative_hits(
    results: List[Dict[str, Any]],
    keywords: List[str],
    company_name: str,
) -> int:
    count = 0
    company_lower = (company_name or "").strip().lower()
    if not company_lower:
        return 0
    for result in results:
        text = f"{result.get('snippet', '')} {result.get('title', '')}".lower()
        if company_lower not in text:
            continue
        for kw in keywords:
            if kw.lower() in text:
                count += 1
                break
    return count


SNIPPET_MARKERS = [
    "out of 5 stars",
    "company reviews on",
    "based on",
    "indicating that most",
    "...",
    "would recommend",
]


def contains_raw_snippet(text: str) -> bool:
    text_lower = (text or "").lower()
    hits = sum(1 for m in SNIPPET_MARKERS if m in text_lower)
    return hits >= 2


# Backward-compatible name used by older tests and _generate_llm_summary.
is_raw_snippet = contains_raw_snippet


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
        for m in re.finditer(
            r"(?:About\s+([A-Za-z][A-Za-z0-9&.\- ]+)|Company:\s*([A-Za-z][A-Za-z0-9&.\- ]+))",
            text,
        ):
            for g in (m.group(1), m.group(2)):
                if g:
                    cand = g.strip()
                    if cand and not is_job_board_brand_label(cand):
                        return cand

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


BAD_REPUTATION_PLACEHOLDER_NAMES = frozenset(
    {
        "unknown",
        "the company",
        "this company",
        "",
        "employer",
        "client",
        "confidential",
        "a company",
        "n/a",
        "none",
        "null",
    }
)

# Backward-compatible name for tests / internal callers.
_employer_label_is_llm_noise = employer_label_is_llm_noise


def _safe_reputation_company_label(company: str, job_url: Optional[str]) -> str:
    """User-visible employer name for templates; never inject instruction-like strings."""

    if company and not employer_label_is_llm_noise(company):
        return company
    if job_url:
        dom = extract_company_from_domain(job_url)
        if dom and not is_job_board_brand_label(dom):
            return dom
    return "this employer"


_SKIP_DOMAIN_LABELS = frozenset(
    {
        "www",
        "careers",
        "jobs",
        "job",
        "apply",
        "work",
        "talent",
        "recruiting",
        "hr",
        "people",
        "board",
        "vacancies",
    }
)


# Short suffixes that, when fused into the bare domain label (e.g. "wemabank", "halobank"),
# should be re-split so the LLM baseline and Serper queries see a recognizable employer name.
_DOMAIN_SUFFIX_SPLITS = (
    "bank",
    "group",
    "corp",
    "holdings",
    "industries",
    "international",
    "systems",
    "labs",
    "media",
    "tech",
    "global",
)


def _humanize_domain_label(label: str) -> str:
    base = label.replace("-", " ").strip()
    if " " in base or len(base) < 6:
        return base.title()
    low = base.lower()
    for suf in _DOMAIN_SUFFIX_SPLITS:
        if low.endswith(suf) and len(low) > len(suf) + 1:
            head = base[: len(base) - len(suf)]
            tail = base[len(base) - len(suf):]
            return f"{head.title()} {tail.title()}".strip()
    return base.title()


def extract_company_from_domain(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower().strip()
        if not host:
            return None
        if host.startswith("www."):
            host = host[4:]
        parts = [p for p in host.split(".") if p]
        i = 0
        while i < len(parts) and parts[i] in _SKIP_DOMAIN_LABELS:
            i += 1
        if i >= len(parts) - 1:
            return None
        name = parts[i]
        if name in _SKIP_DOMAIN_LABELS or len(name) < 2:
            return None
        return _humanize_domain_label(name)
    except Exception:  # noqa: BLE001
        return None


def _maybe_humanize_compound_token(name: str) -> str:
    """Re-split fused single-word employer slugs (``Wemabank`` → ``Wema Bank``).

    LLMs and SERP queries hit better with a spaced employer name. Only applies when the input
    is a single token whose tail matches a known suffix in ``_DOMAIN_SUFFIX_SPLITS``.
    """

    if not name or " " in name:
        return name
    return _humanize_domain_label(name)


def resolve_reputation_query_name(
    company_name: Optional[str],
    job_url: Optional[str],
) -> Optional[str]:
    raw_in = (company_name or "").strip()
    if employer_label_is_llm_noise(raw_in):
        raw_in = ""
    raw = raw_in
    low = raw.lower()
    usable = bool(raw) and low not in BAD_REPUTATION_PLACEHOLDER_NAMES and not is_job_board_brand_label(raw)
    if usable:
        return _maybe_humanize_compound_token(raw)
    if job_url:
        dom = extract_company_from_domain(job_url)
        if dom and not is_job_board_brand_label(dom):
            return _maybe_humanize_compound_token(dom)
    if raw and low not in BAD_REPUTATION_PLACEHOLDER_NAMES and not is_job_board_brand_label(raw):
        return _maybe_humanize_compound_token(raw)
    return None


def build_template_fallback(
    company_name: str,
    overall_sentiment: str,
    green_flags: List[str],
    red_flags: List[str],
    sources_found: int,
) -> str:
    def _clean(line: str) -> str:
        return (line or "").strip().rstrip(".") + "."

    g0 = _clean(green_flags[0] if green_flags else "No strong positives identified")
    r0 = _clean(red_flags[0] if red_flags else "No major concerns detected")
    return (
        f"Based on {sources_found} source(s), {company_name} has a {overall_sentiment} employer reputation. "
        f"{g0} {r0}"
    )


def _strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.removeprefix("```json").removeprefix("```").strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    return t


def _parse_llm_json_object(text: str) -> Optional[Dict[str, Any]]:
    t = _strip_json_fence(text)
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        start = t.find("{")
        end = t.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(t[start : end + 1])
        except Exception:  # noqa: BLE001
            return None


# In-process baseline cache: the LLM "what do you know about <employer>" answer changes
# rarely (employer reputation in Kimi's knowledge cutoff is effectively static for our
# purposes). Caching it shaves 20-35s off every repeat lookup for the same employer.
_BASELINE_CACHE_TTL_S = 24 * 60 * 60  # 24 hours
_BASELINE_CACHE_MAX = 512
# Sentinel marks an explicit negative cache hit (LLM said unknown / confidence none).
_BASELINE_NEGATIVE_SENTINEL = object()
_baseline_cache: Dict[str, tuple[float, Any]] = {}
_BASELINE_REDIS_PREFIX = "jobsignal:rep_baseline:v1:"
_redis_baseline_store: Any = None  # None | False | RedisCache instance


def _baseline_cache_key(company_name: str) -> str:
    return re.sub(r"\s+", " ", (company_name or "")).strip().lower()


def _ensure_redis_baseline_client():
    global _redis_baseline_store  # noqa: PLW0603
    if _redis_baseline_store is False:
        return None
    if _redis_baseline_store is not None:
        return _redis_baseline_store
    try:
        from backend.core.cache_store import RedisCache
        from backend.core.env import EnvConfig

        cfg = EnvConfig.load(strict=False)
        url = (cfg.cache_url or "").strip()
        if not url:
            _redis_baseline_store = False
            return None
        _redis_baseline_store = RedisCache(url)
        return _redis_baseline_store
    except Exception:  # noqa: BLE001
        _redis_baseline_store = False
        return None


def _baseline_redis_key(norm_key: str) -> str:
    digest = hashlib.sha256(norm_key.encode("utf-8")).hexdigest()
    return _BASELINE_REDIS_PREFIX + digest


def _baseline_redis_read(norm_key: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Return (hit, payload). hit=False means miss; hit=True with payload=None means negative cache."""
    client = _ensure_redis_baseline_client()
    if not client:
        return False, None
    raw = client.get(_baseline_redis_key(norm_key))
    if raw is None:
        return False, None
    try:
        obj = json.loads(raw)
        if obj.get("neg"):
            return True, None
        data = obj.get("data")
        return True, dict(data) if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return False, None


def _baseline_redis_write(norm_key: str, payload: Optional[Dict[str, Any]]) -> None:
    client = _ensure_redis_baseline_client()
    if not client:
        return
    if payload is None:
        body = json.dumps({"v": 1, "neg": True})
    else:
        body = json.dumps({"v": 1, "neg": False, "data": payload}, ensure_ascii=False)
    try:
        client.set(_baseline_redis_key(norm_key), body, ttl_seconds=_BASELINE_CACHE_TTL_S)
    except Exception:  # noqa: BLE001
        pass


def _peek_baseline_cache(company_name: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Return (hit, payload). miss -> (False, None). hit with unknown employer -> (True, None)."""
    import time as _time

    key = _baseline_cache_key(company_name)
    if not key:
        return False, None

    # 1) Same-process memory (fastest)
    hit = _baseline_cache.get(key)
    if hit:
        ts, payload = hit
        if _time.time() - ts > _BASELINE_CACHE_TTL_S:
            _baseline_cache.pop(key, None)
        else:
            if payload is _BASELINE_NEGATIVE_SENTINEL:
                return True, None
            return True, dict(payload) if isinstance(payload, dict) else None

    # 2) Shared Redis (other replicas / cold restart warm-through)
    rhit, rpayload = _baseline_redis_read(key)
    if rhit:
        _baseline_cache[key] = (_time.time(), _BASELINE_NEGATIVE_SENTINEL if rpayload is None else rpayload)
        return True, rpayload

    return False, None


def clear_baseline_cache() -> None:
    """Test helper: reset the in-process baseline cache between scenarios."""
    _baseline_cache.clear()


def _baseline_cache_set(company_name: str, payload: Optional[Dict[str, Any]]) -> None:
    import time as _time

    key = _baseline_cache_key(company_name)
    if not key:
        return
    store_val: Any = _BASELINE_NEGATIVE_SENTINEL if payload is None else dict(payload)
    if len(_baseline_cache) >= _BASELINE_CACHE_MAX:
        try:
            oldest = min(_baseline_cache.items(), key=lambda kv: kv[1][0])[0]
            _baseline_cache.pop(oldest, None)
        except ValueError:
            pass
    _baseline_cache[key] = (_time.time(), store_val)
    _baseline_redis_write(key, payload)


async def get_llm_company_baseline(
    company_name: str,
    job_title: Optional[str] = None,
    job_location: Optional[str] = None,
    *,
    request_id: str = "company_baseline",
) -> Optional[Dict[str, Any]]:
    from backend.core.llm_fireworks import _get, llm_enabled
    from backend.core.llm_safe import call_llm_safe, under_pytest

    # Avoid hitting real Fireworks during pytest runs unless a test explicitly mocks
    # ``call_llm_safe`` — sync openai retries can otherwise blow the outer 45s pipeline budget.
    if under_pytest() and getattr(call_llm_safe, "__module__", "") == "backend.core.llm_safe":
        return None

    # Warm-cache fast path: a known employer's baseline answer is good for 24h (memory +
    # optional Redis when CACHE_URL is set for multi-replica consistency). Negative results
    # are cached too so niche employers do not re-trigger the same LLM timeout on every refresh.
    hit, cached_payload = _peek_baseline_cache(company_name)
    if hit:
        return cached_payload

    fallback = (
        '{"known":false,"company_type":"unknown","industry":null,"headquarters":null,'
        '"size_estimate":null,"reputation_summary":"","known_positives":[],"known_concerns":[],'
        '"confidence":"none","knowledge_cutoff_note":""}'
    )
    try:
        if not llm_enabled():
            return None
        if not (_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")):
            return None
        extras: List[str] = []
        if job_title:
            extras.append(f"Job title context: {job_title}")
        if job_location:
            extras.append(f"Location context: {job_location}")
        extra_blk = ("\n" + "\n".join(extras)) if extras else ""
        system = (
            "You are a company research assistant. Respond only with valid JSON. "
            "No preamble. No explanation. No markdown."
        )
        # Compact schema: dropping low-value fields keeps Kimi K2.6 generation under our 25s
        # request budget. Industry/headquarters/size were never user-visible.
        user = (
            f"What do you know about {company_name} as an employer?{extra_blk}\n"
            "Return exactly this JSON structure and nothing else:\n"
            "{\n"
            '  "known": true|false,\n'
            '  "reputation_summary": "<=2 sentence honest assessment",\n'
            '  "known_positives": ["up to 3 short bullets"],\n'
            '  "known_concerns": ["up to 3 short bullets"],\n'
            '  "confidence": "high|medium|low|none"\n'
            "}\n"
            "If you have no knowledge of this company, set known=false and confidence=none. "
            "Never invent information."
        )
        raw = await call_llm_safe(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            fallback=fallback,
            request_id=request_id,
            model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            temperature=0.2,
            max_tokens=700,
            timeout=35.0,
            prose_mode=False,
            max_chars=8000,
            min_prose_len=2,
            require_sentence_period=False,
        )
        data = _parse_llm_json_object(raw)
        data = merge_curated_baseline(company_name, data)
        if not data or not data.get("known"):
            # Negative result is also cached so we don't keep retrying unknown employers
            # within the 24h window — saves repeat 25-35s timeouts on niche names.
            _baseline_cache_set(company_name, None)
            return None
        conf = str(data.get("confidence") or "").lower()
        if conf in ("none", ""):
            _baseline_cache_set(company_name, None)
            return None
        _baseline_cache_set(company_name, data)
        return data
    except Exception:  # noqa: BLE001
        logger.warning("llm_company_baseline_failed request_id=%s", request_id, exc_info=False)
        return None


def _serper_summary_for_llm(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    # Keep the synthesis prompt small enough that Kimi K2.6 can generate the full JSON
    # within our 25s inner timeout — 6 rows × ~200 chars stays well under 4KB of context.
    out: List[Dict[str, str]] = []
    for row in rows[:6]:
        out.append(
            {
                "title": str(row.get("title") or "")[:120],
                "snippet": str(row.get("snippet") or "")[:240],
            }
        )
    return out


async def synthesize_reputation(
    company_name: str,
    llm_baseline: Optional[Dict[str, Any]],
    serper_summary: Optional[List[Dict[str, str]]],
    *,
    legacy_score: int,
    legacy_sentiment: str,
    legacy_green: List[str],
    legacy_red: List[str],
    sources_found: int,
    request_id: str = "reputation_synthesize",
) -> Optional[Dict[str, Any]]:
    from backend.core.llm_fireworks import _get, llm_enabled
    from backend.core.llm_safe import call_llm_safe, under_pytest

    has_base = bool(llm_baseline)
    has_serper = bool(serper_summary)
    if not has_base and not has_serper:
        return None

    if under_pytest() and getattr(call_llm_safe, "__module__", "") == "backend.core.llm_safe":
        return _synthesize_fallback_payload(
            company_name,
            llm_baseline,
            serper_summary,
            legacy_score=legacy_score,
            legacy_sentiment=legacy_sentiment,
            legacy_green=legacy_green,
            legacy_red=legacy_red,
            sources_found=sources_found,
        ) or None

    rel_n = len(serper_summary or [])
    if not llm_enabled() or not (_get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")):
        return _synthesize_fallback_payload(
            company_name,
            llm_baseline,
            serper_summary,
            legacy_score=legacy_score,
            legacy_sentiment=legacy_sentiment,
            legacy_green=legacy_green,
            legacy_red=legacy_red,
            sources_found=sources_found,
        )

    serper_blob = json.dumps(serper_summary or [], ensure_ascii=False)
    base_blob = json.dumps(llm_baseline or {}, ensure_ascii=False)

    if has_base and has_serper:
        branch_user = (
            f"Synthesize a company reputation assessment for {company_name}.\n\n"
            f"LLM knowledge:\n{base_blob}\n\n"
            f"Live search findings:\n{serper_blob}\n\n"
            "Return exactly this JSON:\n"
            "{\n"
            '  "overall_sentiment": "positive/mixed/negative/unknown",\n'
            '  "review_confidence_score": <integer 0-100>,\n'
            '  "plain_summary": "2-3 sentences, recruiter tone, honest",\n'
            '  "green_flags": ["up to 3 specific positives"],\n'
            '  "red_flags": ["up to 3 specific concerns"],\n'
            '  "data_sources": ["LLM knowledge", "Live search"],\n'
            '  "reliability": "high/medium/low"\n'
            "}\n"
            "plain_summary must be original prose, not copied snippets. "
            "green_flags and red_flags must be specific to this company. "
            "review_confidence_score: if both sources agree, 65-85; if conflicting, 45-65."
        )
        expected_sources = ["LLM knowledge", "Live search"]
    elif has_base:
        branch_user = (
            f"Synthesize a company reputation assessment for {company_name}.\n\n"
            f"LLM knowledge:\n{base_blob}\n\n"
            "Live search returned no usable rows for this run.\n\n"
            "Return exactly this JSON:\n"
            "{\n"
            '  "overall_sentiment": "positive/mixed/negative/unknown",\n'
            '  "review_confidence_score": <integer 0-100>,\n'
            '  "plain_summary": "2-3 sentences; end by noting live review data was unavailable.",\n'
            '  "green_flags": ["up to 3 specific positives"],\n'
            '  "red_flags": ["up to 3 specific concerns"],\n'
            '  "data_sources": ["LLM knowledge only"],\n'
            '  "reliability": "high/medium/low"\n'
            "}\n"
            "Add to plain_summary: Note: live review data was unavailable at this time.\n"
            "If LLM confidence in the baseline was high, score 50-65; medium 30-50; else lower."
        )
        expected_sources = ["LLM knowledge only"]
    else:
        branch_user = (
            f"Synthesize a company reputation assessment for {company_name}.\n\n"
            "LLM had no reliable prior knowledge of this employer.\n\n"
            f"Live search findings:\n{serper_blob}\n\n"
            "Return exactly this JSON:\n"
            "{\n"
            '  "overall_sentiment": "positive/mixed/negative/unknown",\n'
            '  "review_confidence_score": <integer 0-100>,\n'
            '  "plain_summary": "2-3 sentences, recruiter tone, honest",\n'
            '  "green_flags": ["up to 3 specific positives"],\n'
            '  "red_flags": ["up to 3 specific concerns"],\n'
            '  "data_sources": ["Live search only"],\n'
            '  "reliability": "high/medium/low"\n'
            "}\n"
            f"If there are 3+ relevant results use 55-70; if 1-2 use 35-55. "
            f"(This run has {rel_n} summarized rows.)"
        )
        expected_sources = ["Live search only"]

    fallback = json.dumps(
        {
            "overall_sentiment": legacy_sentiment,
            "review_confidence_score": legacy_score,
            "plain_summary": _template_summary(
                company_name, sources_found, legacy_sentiment, legacy_red, legacy_green
            ),
            "green_flags": legacy_green[:3],
            "red_flags": legacy_red[:3],
            "data_sources": expected_sources,
            "reliability": "low",
        },
        ensure_ascii=False,
    )

    try:
        raw = await call_llm_safe(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are JobSignal's reputation analyst. "
                        "Respond only with valid JSON. No preamble. No markdown."
                    ),
                },
                {"role": "user", "content": branch_user},
            ],
            fallback=fallback,
            request_id=request_id,
            model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            temperature=0.25,
            max_tokens=700,
            timeout=25.0,
            prose_mode=False,
            max_chars=12_000,
            min_prose_len=2,
            require_sentence_period=False,
        )
        data = _parse_llm_json_object(raw)
        if not data:
            return _synthesize_fallback_payload(
                company_name,
                llm_baseline,
                serper_summary,
                legacy_score=legacy_score,
                legacy_sentiment=legacy_sentiment,
                legacy_green=legacy_green,
                legacy_red=legacy_red,
                sources_found=sources_found,
            )
        if isinstance(data.get("data_sources"), list):
            ds = [str(x) for x in data["data_sources"]]
        else:
            ds = list(expected_sources)
        data["data_sources"] = ds
        return data
    except Exception:  # noqa: BLE001
        logger.warning("synthesize_reputation_failed request_id=%s", request_id, exc_info=False)
        return _synthesize_fallback_payload(
            company_name,
            llm_baseline,
            serper_summary,
            legacy_score=legacy_score,
            legacy_sentiment=legacy_sentiment,
            legacy_green=legacy_green,
            legacy_red=legacy_red,
            sources_found=sources_found,
        )


def _sentiment_to_simple(legacy: str) -> str:
    s = (legacy or "unknown").lower().strip()
    if "positive" in s and "negative" not in s:
        return "positive"
    if "negative" in s:
        return "negative"
    if "mixed" in s:
        return "mixed"
    return "unknown"


def _synthesize_fallback_payload(
    company_name: str,
    llm_baseline: Optional[Dict[str, Any]],
    serper_summary: Optional[List[Dict[str, str]]],
    *,
    legacy_score: int,
    legacy_sentiment: str,
    legacy_green: List[str],
    legacy_red: List[str],
    sources_found: int,
) -> Dict[str, Any]:
    has_base = bool(llm_baseline)
    has_serper = bool(serper_summary)
    if has_base and has_serper:
        return {
            "overall_sentiment": legacy_sentiment,
            "review_confidence_score": legacy_score,
            "plain_summary": _template_summary(
                company_name, sources_found, legacy_sentiment, legacy_red, legacy_green
            ),
            "green_flags": legacy_green[:3] or ["No strong positives identified."],
            "red_flags": legacy_red[:3],
            "data_sources": ["LLM knowledge", "Live search"],
            "reliability": "medium",
        }
    if has_base:
        ds = ["LLM knowledge only"]
        note = " Note: live review data was unavailable at this time."
        summary = (llm_baseline or {}).get("reputation_summary") or ""
        summary = f"{summary}{note}" if summary else note.strip()
        greens = [str(x) for x in (llm_baseline or {}).get("known_positives") or []][:3]
        reds = [str(x) for x in (llm_baseline or {}).get("known_concerns") or []][:3]
        if not greens and legacy_green:
            greens = legacy_green[:3]
        if not reds and legacy_red:
            reds = legacy_red[:3]
        return {
            "overall_sentiment": _sentiment_from_baseline(llm_baseline)
            or legacy_sentiment
            or _sentiment_to_simple(legacy_sentiment),
            "review_confidence_score": max(30, min(65, legacy_score)) if legacy_score else 45,
            "plain_summary": summary
            or build_template_fallback(
                company_name,
                _sentiment_from_baseline(llm_baseline) or "unknown",
                greens,
                reds,
                sources_found,
            ),
            "green_flags": greens or ["No strong positives identified."],
            "red_flags": reds or [],
            "data_sources": ds,
            "reliability": "medium",
        }
    if has_serper:
        return {
            "overall_sentiment": legacy_sentiment,
            "review_confidence_score": legacy_score,
            "plain_summary": _template_summary(
                company_name, sources_found, legacy_sentiment, legacy_red, legacy_green
            ),
            "green_flags": legacy_green[:3] or ["No strong positives identified."],
            "red_flags": legacy_red[:3],
            "data_sources": ["Live search only"],
            "reliability": "medium",
        }
    return {}


def _sentiment_from_baseline(baseline: Optional[Dict[str, Any]]) -> str:
    if not baseline:
        return "unknown"
    concerns = baseline.get("known_concerns") or []
    pos = baseline.get("known_positives") or []
    if pos and not concerns:
        return "positive"
    if concerns and not pos:
        return "negative"
    if pos and concerns:
        return "mixed"
    return "unknown"


def _cap_review_confidence_score(score: int, *, platforms_found: int, quick: bool) -> int:
    """Tie reputation numeric confidence to how many distinct platforms returned usable rows.

    Public web search leftovers are not grounds for a perfect score; caps keep the UI honest.
    """

    v = max(0, min(100, int(score)))
    n = max(0, int(platforms_found))
    if quick:
        ceiling = min(74, 38 + n * 12)
    else:
        ceiling = min(84, 48 + n * 12)
    return min(v, ceiling)


async def _one_serper_query(
    coordinator: Any, q: str, *, timeout_s: float = 6.0
) -> Optional[List[Dict[str, Any]]]:
    try:
        rows = await asyncio.wait_for(coordinator.search(q, num=5), timeout=timeout_s)
        return rows
    except Exception:  # noqa: BLE001
        return None


async def get_company_reviews(
    coordinator: Any,
    company_name: Optional[str],
    *,
    request_id: str = "unknown",
    quick: bool = False,
    employer_confirmed: bool = True,
    job_url: Optional[str] = None,
    job_title: Optional[str] = None,
    job_location: Optional[str] = None,
) -> ReviewSummary:
    if not employer_confirmed:
        return ReviewSummary(
            status="employer_unconfirmed",
            message="Employer identity not confirmed.",
            review_confidence_score=None,
            overall_sentiment="unknown",
            sources_checked=0,
            sources_found=0,
            plain_summary="",
        )

    resolved = resolve_reputation_query_name(company_name, job_url)
    if not resolved:
        return ReviewSummary(
            status="company_not_identified",
            message="We could not identify the company name from this posting. Paste the company name manually to enable reputation checks.",
        )

    company_name_eff = resolved
    summary_company = _safe_reputation_company_label(company_name_eff, job_url)

    query_templates_full = [
        f"{company_name_eff} employee reviews rating",
        f"{company_name_eff} Glassdoor Indeed workplace",
        f"{company_name_eff} company culture employees",
        f"{company_name_eff} employer reputation",
    ]
    # Quick: two highest-yield queries only; full: four parallel signals.
    query_templates = query_templates_full[:2] if quick else query_templates_full
    query_keys = [f"enrich_{i}" for i in range(len(query_templates))]
    serper_timeout_s = 4.0 if quick else 6.0

    async def _bounded_baseline() -> Optional[Dict[str, Any]]:
        # Hard ceiling on the baseline call. Production probes showed Kimi K2.6 on Fireworks
        # sometimes runs 20-25s for the compact schema, so 40s gives consistent headroom
        # while still fitting inside the 75s outer budget alongside synthesis.
        try:
            return await asyncio.wait_for(
                get_llm_company_baseline(
                    company_name_eff,
                    job_title,
                    job_location,
                    request_id=f"{request_id}_baseline",
                ),
                timeout=40.0,
            )
        except Exception:  # noqa: BLE001
            return None

    async def _run_pipeline() -> ReviewSummary:
        serper_tasks = [
            _one_serper_query(coordinator, q, timeout_s=serper_timeout_s) for q in query_templates
        ]
        if quick:
            raw_lists = await asyncio.gather(*serper_tasks)
            llm_baseline = None
        else:
            baseline_task = asyncio.create_task(_bounded_baseline())
            serper_gathered = asyncio.gather(*serper_tasks)
            llm_baseline, raw_lists = await asyncio.gather(baseline_task, serper_gathered)

        results: Dict[str, List[Dict[str, Any]]] = {}
        flat_for_summary: List[Dict[str, Any]] = []
        for key, q, rows in zip(query_keys, query_templates, raw_lists):
            if rows is None:
                results[key] = []
                continue
            filtered = [row for row in rows if is_company_relevant(row, company_name_eff)]
            results[key] = filtered
            for row in filtered:
                flat_for_summary.append(row)

        serper_for_llm = _serper_summary_for_llm(flat_for_summary) if flat_for_summary else None

        all_highlights: List[ReviewSource] = []
        platforms_found: set[str] = set()
        reddit_results: List[ReviewSource] = []
        x_results: List[ReviewSource] = []

        for k, query_res in results.items():
            for item in query_res:
                source = _parse_serper_item(item, k, company_name_eff)
                if source:
                    if source.platform == "Reddit":
                        reddit_results.append(source)
                    elif source.platform == "X/Twitter":
                        x_results.append(source)
                    else:
                        if source.platform not in platforms_found:
                            all_highlights.append(source)
                            platforms_found.add(source.platform)

        reddit_data = _process_reddit(reddit_results)
        if reddit_data:
            platforms_found.add("Reddit")

        x_data = _process_x(x_results)
        if x_data:
            platforms_found.add("X/Twitter")

        score = 50.0

        def score_source(sentiment: str, reliability_weight: float) -> None:
            nonlocal score
            if sentiment == "positive":
                score += 15 * reliability_weight
            elif sentiment == "mixed":
                score += 3 * reliability_weight
            elif sentiment == "negative":
                score -= 15 * reliability_weight

        all_red: List[str] = []
        all_green: List[str] = []

        for h in all_highlights:
            w = {"high": 0.9, "medium": 0.7}.get(h.reliability, 0.45)
            if h.platform == "Glassdoor":
                w = 0.95
            elif h.platform == "Indeed":
                w = 0.90
            elif h.platform == "LinkedIn":
                w = 0.80
            elif h.platform == "Trustpilot":
                w = 0.65
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
            score_source(str(reddit_data["sentiment"]).replace("mostly ", ""), 0.70)
            for r in reddit_data["red_flags_found"]:
                all_red.append(f"{r} (via Reddit)")
            for g in reddit_data["green_flags_found"]:
                all_green.append(f"{g} (via Reddit)")

        if x_data:
            score_source(str(x_data["sentiment"]).replace("mostly ", ""), 0.55)
            for r in x_data["red_flags_found"]:
                all_red.append(f"{r} (via X)")
            for g in x_data["green_flags_found"]:
                all_green.append(f"{g} (via X)")

        red_dedup = _dedup_flags(all_red, 4)
        green_dedup = _dedup_flags(all_green, 4)

        score -= 10 * len(red_dedup)
        score += min(20, 5 * len(green_dedup))

        final_score = int(min(max(score, 0), 100))
        final_score = _cap_review_confidence_score(
            final_score, platforms_found=len(platforms_found), quick=quick
        )

        positive_count = sum(1 for h in all_highlights if h.sentiment == "positive") + (
            1 if reddit_data and "positive" in str(reddit_data["sentiment"]) else 0
        )
        negative_count = sum(1 for h in all_highlights if h.sentiment == "negative") + (
            1 if reddit_data and "negative" in str(reddit_data["sentiment"]) else 0
        )

        overall_sentiment = "mixed"
        if positive_count > negative_count * 2:
            overall_sentiment = "mostly positive"
        elif negative_count > positive_count:
            overall_sentiment = "mostly negative"

        sources_unavailable = [
            p for p in ["Glassdoor", "Indeed", "Trustpilot", "LinkedIn", "Reddit", "X/Twitter"] if p not in platforms_found
        ]

        highlights_payload = [
            {
                "platform": h.platform,
                "rating": h.rating,
                "review_count": h.review_count,
                "sentiment": h.sentiment,
                "snippet": h.snippet,
                "reliability": h.reliability,
            }
            for h in all_highlights
        ]

        # Quick reputation: Serper + heuristic scoring only (no Kimi baseline or synthesis).
        if quick:
            if not serper_for_llm:
                return ReviewSummary(
                    review_confidence_score=None,
                    overall_sentiment="unknown",
                    sources_checked=len(query_templates),
                    sources_found=0,
                    plain_summary=_template_summary(summary_company, 0, "unknown", [], []),
                    sources_unavailable=["Glassdoor", "Indeed", "Trustpilot", "LinkedIn", "Reddit", "X/Twitter"],
                    data_sources=[],
                    reliability_report="",
                )
            tpl_plain = _template_summary(
                summary_company,
                len(platforms_found),
                overall_sentiment,
                red_dedup,
                green_dedup,
            )
            rcs_quick = _cap_review_confidence_score(
                final_score, platforms_found=len(platforms_found), quick=True
            )
            return ReviewSummary(
                review_confidence_score=rcs_quick,
                overall_sentiment=overall_sentiment,
                sources_checked=len(query_templates),
                sources_found=len(platforms_found),
                highlights=highlights_payload,
                red_flags=red_dedup[:4],
                green_flags=green_dedup[:4],
                plain_summary=tpl_plain,
                sources_unavailable=sources_unavailable,
                reddit=reddit_data,
                x_twitter=x_data,
                data_sources=["Live search only"],
                reliability_report="",
            )

        if not llm_baseline and not serper_for_llm:
            return ReviewSummary(
                review_confidence_score=None,
                overall_sentiment="unknown",
                sources_checked=len(query_templates),
                sources_found=0,
                plain_summary=_template_summary(summary_company, 0, "unknown", [], []),
                sources_unavailable=["Glassdoor", "Indeed", "Trustpilot", "LinkedIn", "Reddit", "X/Twitter"],
                data_sources=[],
                reliability_report="",
            )

        try:
            synth = await asyncio.wait_for(
                synthesize_reputation(
                    company_name_eff,
                    llm_baseline,
                    serper_for_llm,
                    legacy_score=final_score,
                    legacy_sentiment=overall_sentiment,
                    legacy_green=green_dedup,
                    legacy_red=red_dedup,
                    sources_found=len(platforms_found),
                    request_id=f"{request_id}_synthesize",
                ),
                timeout=30.0,
            )
        except Exception:  # noqa: BLE001
            synth = _synthesize_fallback_payload(
                company_name_eff,
                llm_baseline,
                serper_for_llm,
                legacy_score=final_score,
                legacy_sentiment=overall_sentiment,
                legacy_green=green_dedup,
                legacy_red=red_dedup,
                sources_found=len(platforms_found),
            ) or None
        if not synth:
            return ReviewSummary(
                review_confidence_score=None,
                overall_sentiment="unknown",
                sources_checked=len(query_templates),
                sources_found=len(platforms_found),
                highlights=highlights_payload,
                plain_summary=_template_summary(summary_company, 0, "unknown", [], []),
                sources_unavailable=sources_unavailable,
                reddit=reddit_data,
                x_twitter=x_data,
                data_sources=[],
                reliability_report="",
            )

        plain = str(synth.get("plain_summary") or "").strip()
        osent = str(synth.get("overall_sentiment") or "unknown")
        gfs = [str(x) for x in (synth.get("green_flags") or [])][:4]
        rfs = [str(x) for x in (synth.get("red_flags") or [])][:4]
        rcs = synth.get("review_confidence_score")
        try:
            rcs_int = int(rcs) if rcs is not None else final_score
            rcs_int = max(0, min(100, rcs_int))
        except Exception:  # noqa: BLE001
            rcs_int = final_score
        rcs_int = _cap_review_confidence_score(
            rcs_int, platforms_found=len(platforms_found), quick=False
        )

        if is_prompt_leak(plain) or contains_raw_snippet(plain):
            plain = build_template_fallback(
                summary_company,
                osent,
                gfs or green_dedup,
                rfs or red_dedup,
                len(platforms_found),
            )

        ds_raw = synth.get("data_sources") or []
        ds_list: List[str] = [str(x) for x in ds_raw] if isinstance(ds_raw, list) else []
        # Defensive: synthesis fallback always sets data_sources; never let the wire payload
        # drop the field silently when we actually have evidence on hand.
        if not ds_list:
            if llm_baseline and serper_for_llm:
                ds_list = ["LLM knowledge", "Live search"]
            elif llm_baseline:
                ds_list = ["LLM knowledge only"]
            elif serper_for_llm:
                ds_list = ["Live search only"]
        rel_rep = str(synth.get("reliability") or "")

        display_sentiment = osent
        if osent == "positive" and overall_sentiment == "mostly positive":
            display_sentiment = overall_sentiment
        elif osent == "negative" and overall_sentiment == "mostly negative":
            display_sentiment = overall_sentiment

        return ReviewSummary(
            review_confidence_score=rcs_int,
            overall_sentiment=display_sentiment,
            sources_checked=len(query_templates),
            sources_found=len(platforms_found),
            highlights=highlights_payload,
            red_flags=rfs or red_dedup,
            green_flags=gfs or green_dedup,
            plain_summary=plain,
            sources_unavailable=sources_unavailable,
            reddit=reddit_data,
            x_twitter=x_data,
            data_sources=ds_list,
            reliability_report=rel_rep,
        )

    try:
        outer_budget = 22.0 if quick else 75.0
        return await asyncio.wait_for(_run_pipeline(), timeout=outer_budget)
    except asyncio.TimeoutError:
        return ReviewSummary(status="unavailable", message="Review pipeline timed out.", timeout=True, partial=True)
    except Exception as e:  # noqa: BLE001
        logger.error("Review pipeline error: %s", e)
        return ReviewSummary(
            status="unavailable",
            message="Reputation data could not be retrieved for this request.",
            error_type="internal",
        )

def _average_rating(highlights: List[ReviewSource]) -> Optional[float]:
    vals = [float(h.rating) for h in highlights if h.rating is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def build_reputation_summary_messages(
    *,
    company: str,
    overall_sentiment: str,
    avg_rating: Optional[float],
    green_flags: List[str],
    red_flags: List[str],
    sources_found: int,
) -> List[Dict[str, str]]:
    green_text = "; ".join(green_flags[:3]) if green_flags else "No strong positive signals were found."
    red_text = "; ".join(red_flags[:3]) if red_flags else "No major concerns were detected."
    rating_text = f"{avg_rating}/5" if avg_rating is not None else "unknown"
    return [
        {
            "role": "system",
            "content": (
                "You are JobSignal. Write a concise 2-3 sentence employer reputation summary for a job seeker using "
                "only the structured data provided. Respond with the summary only. Start directly with the advice. "
                "No preamble. Use natural prose, not field labels, bullets, or planning notes. Do not quote or "
                "paste source snippets."
            ),
        },
        {
            "role": "user",
            "content": (
                f"company={company}\n"
                f"overall_sentiment={overall_sentiment}\n"
                f"average_rating={rating_text}\n"
                f"sources_found={sources_found}\n"
                f"green_flags={green_text}\n"
                f"red_flags={red_text}"
            ),
        },
    ]


def _template_summary(
    company: str,
    count: int,
    sentiment: str,
    red_flags: List[str],
    green_flags: List[str],
) -> str:
    """Template fallback when reputation LLM output is unavailable or invalid."""
    def _clean(line: str) -> str:
        return (line or "").strip().rstrip(".") + "."

    top_green = _clean(green_flags[0] if green_flags else "No strong positive signals were found")
    top_red = _clean(red_flags[0] if red_flags else "No major concerns detected")
    if count == 0:
        base = (
            f"Public employer reputation data was sparse for {company}, so we could not summarize sentiment reliably. "
            "That usually means independent reviews were hard to find—not that the employer is problematic."
        )
        if red_flags:
            return f"{base} Note: {top_red}"
        return base
    return (
        f"Based on {count} sources, {company} has a {sentiment} employer reputation. "
        f"{top_green} {top_red}"
    )

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

def _parse_serper_item(item: Dict[str, Any], query_key: str, company_name: str) -> Optional[ReviewSource]:
    snippet_raw = item.get("snippet", "") or ""
    title_raw = item.get("title", "") or ""
    snippet = snippet_raw
    link = (item.get("link", "") or "").lower()
    title_lower = title_raw.lower()

    if not is_company_relevant(item, company_name):
        return None

    platform = "Web"
    reliability = "low"

    if "reddit" in query_key or "reddit.com" in link:
        platform = "Reddit"
        reliability = "medium"
    elif "twitter.com" in link or "x.com" in link:
        platform = "X/Twitter"
        reliability = "low"
    elif "glassdoor.com" in link:
        platform = "Glassdoor"
        reliability = "high"
    elif "indeed.com" in link:
        platform = "Indeed"
        reliability = "high"
    elif "linkedin.com/company/" in link:
        platform = "LinkedIn"
        reliability = "medium"
    elif "linkedin.com" in link:
        return None
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

    text = title_lower + " " + snippet.lower()
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
        post_title=title_lower,
    )


async def _generate_llm_summary(
    company: str,
    *,
    overall_sentiment: str,
    avg_rating: Optional[float],
    green_flags: List[str],
    red_flags: List[str],
    sources_found: int,
    request_id: str = "unknown",
) -> Optional[str]:
    from backend.core.llm_fireworks import _get, llm_enabled
    from backend.core.llm_safe import call_llm_safe

    api_key = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    llm_enabled_flag = llm_enabled()
    if not api_key or not llm_enabled_flag:
        return None

    fallback_txt = _template_summary(
        company.strip() if company.strip() else "The employer behind this posting",
        sources_found,
        overall_sentiment,
        red_flags,
        green_flags,
    )

    def _looks_like_meta_text(s: str) -> bool:
        low = (s or "").strip().lower()
        if not low:
            return False
        meta_markers = (
            "i need to",
            "i should",
            "ignore any line",
            "looking at the data",
            "based on the data provided",
            "here are",
            "1.",
            "2.",
        )
        if any(m in low for m in meta_markers):
            return True
        return False

    summary_text = await call_llm_safe(
        messages=build_reputation_summary_messages(
            company=company,
            overall_sentiment=overall_sentiment,
            avg_rating=avg_rating,
            green_flags=green_flags,
            red_flags=red_flags,
            sources_found=sources_found,
        ),
        fallback=fallback_txt,
        request_id=request_id,
        model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
        temperature=0.3,
        max_tokens=150,
        timeout=8.0,
    )
    if "Summary:" in summary_text:
        summary_text = summary_text.split("Summary:")[-1].strip()
    summary_text = (summary_text or "").strip()
    if not summary_text:
        return None
    if is_prompt_leak(summary_text) or _looks_like_meta_text(summary_text) or is_raw_snippet(summary_text):
        return fallback_txt
    return summary_text
