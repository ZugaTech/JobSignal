import asyncio
import httpx
from typing import Dict, Any, List, Optional

class EvidenceCoordinator:
    def __init__(self, api_key: str, *, search_timeout_s: float = 5.0):
        self.api_key = api_key
        self.search_timeout_s = float(search_timeout_s)
        self.client = httpx.AsyncClient()
        self.calls_made = 0
        self.max_calls = 8
        self.rate_limited = False
        self.lock = asyncio.Lock()

    def set_max_calls(self, count: int):
        self.max_calls = count

    async def close(self):
        await self.client.aclose()

    async def search(self, query: str, num: int = 5) -> Optional[List[Dict[str, Any]]]:
        async with self.lock:
            if self.rate_limited or self.calls_made >= self.max_calls:
                return None
            self.calls_made += 1
            
        for attempt in range(2): # 1 retry max (2 attempts)
            try:
                r = await self.client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": num},
                    timeout=float(self.search_timeout_s),
                )
                if r.status_code == 200:
                    return r.json().get("organic", [])
                elif r.status_code == 429:
                    async with self.lock:
                        self.rate_limited = True
                    return None
                else:
                    import logging
                    logging.warning(f"Serper returned {r.status_code} for query: {query}")
                    return None # Non-200 -> unavailable
            except Exception:
                pass
                
        return [] # Timeout or error after 2 attempts -> source not found
