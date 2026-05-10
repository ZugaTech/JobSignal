import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("jobsignal")


class EvidenceCoordinator:
    """Serper-backed search with an isolated per-phase call budget.

    Evidence vs reputation vs recommendations each use their own coordinator so
    parallel asyncio tasks do not starve one another under a shared global cap.
    """

    def __init__(
        self,
        api_key: str,
        *,
        search_timeout_s: float = 5.0,
        max_calls: int = 12,
        search_endpoint: str = "https://google.serper.dev/search",
    ):
        self.api_key = api_key
        self.search_timeout_s = float(search_timeout_s)
        ep = (search_endpoint or "").strip() or "https://google.serper.dev/search"
        self.search_endpoint = ep
        self.client = httpx.AsyncClient()
        self.calls_made = 0
        self.max_calls = max(1, int(max_calls))
        self.rate_limited = False
        self.lock = asyncio.Lock()

    def set_max_calls(self, count: int) -> None:
        self.max_calls = max(1, int(count))

    async def close(self) -> None:
        await self.client.aclose()

    async def search(self, query: str, num: int = 5) -> Optional[List[Dict[str, Any]]]:
        async with self.lock:
            if self.rate_limited or self.calls_made >= self.max_calls:
                return None
            self.calls_made += 1

        for _attempt in range(2):  # 1 retry max (2 attempts)
            try:
                r = await self.client.post(
                    self.search_endpoint,
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": num},
                    timeout=float(self.search_timeout_s),
                )
                if r.status_code == 200:
                    return r.json().get("organic", [])
                if r.status_code == 429:
                    async with self.lock:
                        self.rate_limited = True
                    return None
                logger.warning("Serper returned %s for query (truncated): %s", r.status_code, query[:120])
                return None
            except Exception:
                pass

        return []
