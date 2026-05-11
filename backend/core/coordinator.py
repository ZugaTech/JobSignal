import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("jobsignal")


def _normalize_serpapi_organic(raw: Any) -> List[Dict[str, Any]]:
    """Map SerpApi ``organic_results`` rows into Serper-shaped dicts (title, link, snippet)."""

    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        link = row.get("link")
        if not link:
            continue
        out.append(
            {
                "title": row.get("title") or "",
                "link": link,
                "snippet": row.get("snippet") or "",
            }
        )
    return out


class EvidenceCoordinator:
    """Search-backed evidence with Serper primary and optional SerpApi fallback.

    SerpApi is used when Serper returns a non-200 response, raises, or when no Serper key is set.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        serpapi_api_key: str = "",
        serpapi_endpoint: str = "https://serpapi.com/search.json",
        search_timeout_s: float = 5.0,
        max_calls: int = 12,
        search_endpoint: str = "https://google.serper.dev/search",
    ):
        self.serper_api_key = (api_key or "").strip()
        self.serpapi_api_key = (serpapi_api_key or "").strip()
        self.search_timeout_s = float(search_timeout_s)
        ep = (search_endpoint or "").strip() or "https://google.serper.dev/search"
        self.search_endpoint = ep
        sep = (serpapi_endpoint or "").strip() or "https://serpapi.com/search.json"
        self.serpapi_endpoint = sep
        self.client = httpx.AsyncClient()
        self.calls_made = 0
        self.max_calls = max(1, int(max_calls))
        self.rate_limited = False
        self.lock = asyncio.Lock()

    def set_max_calls(self, count: int) -> None:
        self.max_calls = max(1, int(count))

    async def close(self) -> None:
        await self.client.aclose()

    async def _search_serpapi(self, query: str, num: int) -> Optional[List[Dict[str, Any]]]:
        if not self.serpapi_api_key:
            return None
        try:
            r = await self.client.get(
                self.serpapi_endpoint,
                params={
                    "engine": "google",
                    "q": query,
                    "num": num,
                    "api_key": self.serpapi_api_key,
                },
                timeout=float(self.search_timeout_s),
            )
            if r.status_code == 200:
                return _normalize_serpapi_organic((r.json() or {}).get("organic_results"))
            if r.status_code == 429:
                async with self.lock:
                    self.rate_limited = True
                logger.warning("SerpAPI returned 429 for query (truncated): %s", query[:120])
                return None
            logger.warning("SerpAPI returned %s for query (truncated): %s", r.status_code, query[:120])
            return None
        except Exception:
            logger.warning("SerpAPI request failed for query (truncated): %s", query[:120], exc_info=False)
            return None

    async def search(self, query: str, num: int = 5) -> Optional[List[Dict[str, Any]]]:
        async with self.lock:
            if self.rate_limited or self.calls_made >= self.max_calls:
                return None
            self.calls_made += 1

        if self.serper_api_key:
            saw_serper_429 = False
            for _attempt in range(2):  # retry once on transport errors
                try:
                    r = await self.client.post(
                        self.search_endpoint,
                        headers={"X-API-KEY": self.serper_api_key, "Content-Type": "application/json"},
                        json={"q": query, "num": num},
                        timeout=float(self.search_timeout_s),
                    )
                    if r.status_code == 200:
                        return r.json().get("organic", [])
                    if r.status_code == 429:
                        saw_serper_429 = True
                        logger.warning("Serper returned 429 for query (truncated): %s", query[:120])
                        break
                    logger.warning("Serper returned %s for query (truncated): %s", r.status_code, query[:120])
                    break
                except Exception:
                    pass

            fb = await self._search_serpapi(query, num)
            if fb is not None:
                return fb
            if saw_serper_429:
                async with self.lock:
                    self.rate_limited = True
            return None

        fb_only = await self._search_serpapi(query, num)
        if fb_only is not None:
            return fb_only

        return None
