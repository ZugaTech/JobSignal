"""Lightweight HTTP probe for removed listings (HEAD / redirect chain, SSRF-guarded)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

import httpx

from backend.core.fetch_job_page import assert_safe_request_url


async def probe_http_status_head(url: str, *, max_redirects: int = 4) -> Optional[int]:
    """Return final HTTP status after bounded redirects, or None if unavailable."""

    current = url
    hops = 0
    timeout = httpx.Timeout(6.0, connect=2.0)
    headers = {"User-Agent": "JobSignal/1.0 (+https://github.com/jobverification)"}

    async with httpx.AsyncClient(timeout=timeout, verify=True, follow_redirects=False) as client:
        while hops <= max_redirects:
            try:
                assert_safe_request_url(current)
            except ValueError:
                return None
            try:
                resp = await client.head(current, headers=headers)
            except httpx.HTTPError:
                return None
            code = int(resp.status_code)
            if code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc or hops >= max_redirects:
                    return code
                current = urljoin(current, loc.strip())
                hops += 1
                continue
            return code
    return None
