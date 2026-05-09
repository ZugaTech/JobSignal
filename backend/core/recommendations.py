"""Optional similar-job recommendations: search retrieval + verify (Sprint 6).

Not a job board: bounded candidates, honesty labels, no tenant data in shared cache.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Awaitable
from urllib.parse import urlparse

import httpx

from backend.core.image_ingest import ExtractedVisionFields
from backend.core.normalization import NormalizationResult, normalize_job_url

RECOMMENDATIONS_VERSION = "1.0.0"
_HARD_MAX_RECOMMENDATIONS = 3


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip()


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

    def search(self, query: str, *, limit: int) -> List[str]: ...


class FixtureSearchProvider:
    name = "fixture"

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        if self._data is None:
            with open(self._path, encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def search(self, query: str, *, limit: int) -> List[str]:
        data = self._load()
        qlow = query.lower()
        by_sub: Dict[str, Any] = data.get("by_query_substring") or {}
        for key, urls in by_sub.items():
            if key.lower() in qlow and isinstance(urls, list):
                return [str(u) for u in urls[:limit] if u]
        urls = data.get("urls") or []
        if isinstance(urls, list):
            return [str(u) for u in urls[:limit] if u]
        return []


class SerperSearchProvider:
    name = "serper"

    def search(self, query: str, *, limit: int) -> List[str]:
        key = _get("SERPER_API_KEY") or _get("SEARCH_API_KEY")
        if not key:
            return []
        try:
            r = httpx.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": key,
                    "Content-Type": "application/json",
                    "User-Agent": "JobSignal/1.0 (+https://github.com/jobverification)",
                },
                json={"q": query, "num": min(limit, 10)},
                timeout=12.0,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception:  # noqa: BLE001
            return []
        out: List[str] = []
        for row in payload.get("organic") or []:
            link = row.get("link")
            if isinstance(link, str) and link.startswith(("http://", "https://")):
                out.append(link)
            if len(out) >= limit:
                break
        return out


class SerpApiSearchProvider:
    name = "serpapi"

    def search(self, query: str, *, limit: int) -> List[str]:
        key = _get("SERPAPI_API_KEY")
        if not key:
            return []
        try:
            r = httpx.get(
                "https://serpapi.com/search.json",
                params={"api_key": key, "engine": "google", "q": query, "num": min(limit, 10)},
                headers={"User-Agent": "JobSignal/1.0 (+https://github.com/jobverification)"},
                timeout=12.0,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception:  # noqa: BLE001
            return []
        out: List[str] = []
        for row in payload.get("organic_results") or []:
            link = row.get("link")
            if isinstance(link, str) and link.startswith(("http://", "https://")):
                out.append(link)
            if len(out) >= limit:
                break
        return out


def _provider_order() -> List[str]:
    raw = _get("SEARCH_PROVIDER_ORDER", "serper,serpapi,fixture") or "serper,serpapi,fixture"
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def build_provider_chain() -> List[SearchProvider]:
    providers: Dict[str, SearchProvider] = {}
    fx_path = _get("JOBSIGNAL_SEARCH_FIXTURE_PATH")
    if fx_path and os.path.isfile(fx_path):
        providers["fixture"] = FixtureSearchProvider(fx_path)
    providers["serper"] = SerperSearchProvider()
    providers["serpapi"] = SerpApiSearchProvider()

    ordered: List[SearchProvider] = []
    for name in _provider_order():
        p = providers.get(name)
        if p is not None and p not in ordered:
            ordered.append(p)
    return ordered


def any_search_configured() -> bool:
    if _get("SERPAPI_API_KEY") or _get("SEARCH_API_KEY"):
        return True
    fx = _get("JOBSIGNAL_SEARCH_FIXTURE_PATH")
    return bool(fx and os.path.isfile(fx))


def collect_search_urls(queries: Sequence[str], *, limit: int) -> tuple[List[str], List[Dict[str, str]]]:
    """Run providers in order until we have ``limit`` unique URLs or exhaust providers."""

    warnings: List[Dict[str, str]] = []
    seen: set[str] = set()
    out: List[str] = []
    chain = build_provider_chain()
    if not chain:
        warnings.append(
            {
                "code": "REC_SEARCH_NO_PROVIDERS",
                "message": "No search providers configured (set SERPAPI_API_KEY or JOBSIGNAL_SEARCH_FIXTURE_PATH).",
            }
        )
        return [], warnings

    for q in queries:
        if len(out) >= limit:
            break
        q = (q or "").strip()
        if not q:
            continue
        remaining = limit - len(out)
        for prov in chain:
            try:
                found = prov.search(q, limit=remaining + 2)
            except Exception as e:  # noqa: BLE001
                warnings.append({"code": "REC_SEARCH_ERROR", "message": f"{prov.name}: {type(e).__name__}"})
                continue
            for u in found:
                canon, _ = normalize_job_url(u)
                if not canon:
                    continue
                if canon in seen:
                    continue
                seen.add(canon)
                out.append(canon)
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break

    if not out and not any(w["code"] == "REC_SEARCH_NO_PROVIDERS" for w in warnings):
        warnings.append(
            {"code": "REC_SEARCH_EMPTY", "message": "Search returned no usable URLs for the built queries."}
        )
    return out, warnings


def build_query_strings(norm: NormalizationResult, merged: Optional[ExtractedVisionFields]) -> List[str]:
    qs: List[str] = []
    if merged:
        if merged.company_name and str(merged.company_name).strip():
            qs.append(f"{merged.company_name.strip()} careers jobs")
        if merged.job_title and str(merged.job_title).strip():
            qs.append(f"{merged.job_title.strip()} job posting")
    if norm.registrable_domain:
        qs.append(f"site:{norm.registrable_domain} jobs")
    if norm.canonical_url:
        parsed = urlparse(norm.canonical_url)
        if parsed.path and parsed.path not in ("/", ""):
            seg = parsed.path.strip("/").split("/")[0]
            if seg and len(seg) > 2:
                qs.append(f"{seg} jobs hiring")
    if norm.description_text:
        words = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}", norm.description_text)
        chunk = " ".join(words[:10])
        if len(chunk) > 12:
            qs.append(chunk)
    # de-dupe preserve order
    seen: set[str] = set()
    out: List[str] = []
    for q in qs:
        k = q.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(q.strip())
    return out[:6]


def _similarity_reasons(seed: NormalizationResult, candidate_url: str) -> List[str]:
    reasons: List[str] = []
    cand_domain = None
    p = urlparse(candidate_url)
    host = (p.hostname or "").lower()
    if host:
        from backend.core.normalization import registrable_domain_naive

        cand_domain = registrable_domain_naive(host)
    if seed.registrable_domain and cand_domain and seed.registrable_domain == cand_domain:
        reasons.append("Same registrable domain as your posting URL.")
    elif seed.registrable_domain and cand_domain:
        reasons.append(f"Related web result (domain {cand_domain} vs your {seed.registrable_domain}).")
    else:
        reasons.append("Surfaced by search using your job text and URL hints.")
    return reasons[:4]


def _redact(url: str, max_len: int = 120) -> str:
    u = url.strip()
    if len(u) <= max_len:
        return u
    return u[: max_len - 1] + "…"


async def build_recommendations(
    seed_norm: NormalizationResult,
    merged_fields: Optional[ExtractedVisionFields],
    *,
    verify_candidate: Callable[..., Awaitable[Dict[str, Any]]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Verify up to ``candidate_pool_limit()`` URLs; return at most ``effective_recommendations_max()`` items."""

    warnings: List[Dict[str, str]] = []
    max_out = effective_recommendations_max()
    pool_n = candidate_pool_limit()
    queries = build_query_strings(seed_norm, merged_fields)
    if not queries:
        warnings.append(
            {
                "code": "REC_NO_QUERIES",
                "message": "Not enough context to build search queries; add a URL or richer description.",
            }
        )
        return [], warnings

    seed_url = seed_norm.canonical_url
    urls, sw = collect_search_urls(queries, limit=pool_n)
    warnings.extend(sw)
    if not urls:
        return [], warnings

    ranked: List[tuple[int, str, Dict[str, Any]]] = []
    for u in urls:
        if seed_url and u.rstrip("/") == seed_url.rstrip("/"):
            continue
        try:
            rep = await verify_candidate(u)
        except Exception as e:  # noqa: BLE001
            warnings.append({"code": "REC_VERIFY_ERROR", "message": f"Candidate verify failed: {type(e).__name__}"})
            continue
        conf = str(rep.get("confidence") or "").lower()
        if conf == "high":
            tier = 0
        elif conf == "medium":
            tier = 1
        else:
            continue
        ranked.append((tier, u, rep))

    ranked.sort(key=lambda x: (x[0], x[1]))

    recs: List[Dict[str, Any]] = []
    for tier, u, rep in ranked[:max_out]:
        band = "HIGH" if tier == 0 else "MEDIUM"
        recs.append(
            {
                "job_url": _redact(u, 256),
                "confidence_band": band,
                "verdict": rep.get("verdict"),
                "similarity_reasons": _similarity_reasons(seed_norm, u),
                "warnings": list(rep.get("warnings") or [])[:6],
                "source_urls": [_redact(u, 120)],
            }
        )

    return recs, warnings


async def extend_report_with_recommendations(
    report: Dict[str, Any],
    seed_norm: NormalizationResult,
    merged_fields: Optional[ExtractedVisionFields],
    *,
    user_requested: Optional[bool],
    verify_candidate: Callable[..., Awaitable[Dict[str, Any]]],
) -> None:
    """Mutate ``report`` with ``recommendations`` + meta when policy allows."""

    if user_requested is False:
        return
    if user_requested is None and not env_recommendations_default_on():
        return

    base_meta = dict(report.get("meta") or {})
    if not any_search_configured():
        report["meta"] = {
            **base_meta,
            "recommendations_version": RECOMMENDATIONS_VERSION,
            "recommendations_status": "unavailable",
            "recommendations_message": (
                "Similar jobs need SERPAPI_API_KEY (or SEARCH_API_KEY) or JOBSIGNAL_SEARCH_FIXTURE_PATH; see .env.example."
            ),
        }
        report["recommendations"] = []
        return

    recs, rw = await build_recommendations(
        seed_norm,
        merged_fields,
        verify_candidate=verify_candidate,
    )
    report["recommendations"] = recs
    top_warnings: List[Any] = list(report.get("warnings") or [])
    for w in rw:
        if isinstance(w, dict) and w.get("code"):
            top_warnings.append(w)
    report["warnings"] = top_warnings[:20]
    report["meta"] = {
        **base_meta,
        "recommendations_version": RECOMMENDATIONS_VERSION,
        "recommendations_status": "ok" if recs else "empty",
    }
