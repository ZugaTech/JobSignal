#!/usr/bin/env python3
"""Clear JobSignal Redis cache entries used by the verify pipeline.

Loads ``.env`` from the repo root when present.

- Deletes keys matching the URL-result prefix ``js:urlres:v1:*``.
- If ``CACHE_URL`` is unset, the app uses in-memory cache — restart ``uvicorn``
  instead (no Redis keys to delete).

For a **dedicated local Redis** where only JobSignal stores data, you may run
``redis-cli -u "$CACHE_URL" FLUSHDB`` to wipe everything.

Usage (from repo root)::

    python scripts/clear_app_cache.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except Exception:
        pass

    url = (os.environ.get("CACHE_URL") or "").strip()
    if not url:
        print(
            "CACHE_URL not set — verify cache is in-process memory. "
            "Restarting the API server already cleared it."
        )
        return 0

    try:
        import redis
    except ImportError:
        print("Install redis: pip install redis", file=sys.stderr)
        return 1

    client = redis.Redis.from_url(url, decode_responses=True)
    deleted = 0
    for key in client.scan_iter(match="js:urlres:v1:*", count=500):
        client.delete(key)
        deleted += 1
    print(f"Cleared {deleted} Redis key(s) matching js:urlres:v1:*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
