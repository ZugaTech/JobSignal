#!/usr/bin/env python3
"""Warm the URL-only result cache before a demo (sequential POST /v1/verify).

Usage:
  python scripts/warm_cache.py

Optional:
  set JOBSIGNAL_API_BASE=http://127.0.0.1:8080
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


DEMO_URLS = (
    "https://www.linkedin.com/jobs/view/",
    "https://www.indeed.com/viewjob?jk=demo",
    "https://boards.greenhouse.io/demo/jobs/123",
    "https://jobs.lever.co/demo/role",
    "https://example.com/careers/demo-role",
)


def main() -> int:
    base = (os.environ.get("JOBSIGNAL_API_BASE") or "http://127.0.0.1:8080").rstrip("/")
    print(f"Warming cache via {base}/v1/verify …")
    for url in DEMO_URLS:
        body = json.dumps({"job_url": url}).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/v1/verify",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
        except urllib.error.HTTPError as e:
            print(f"FAIL {url} HTTP {e.code}")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {url} {type(e).__name__}: {e}")
            continue
        verdict = data.get("verdict")
        score = data.get("confidence_score")
        cached = data.get("cached")
        print(f"OK  {verdict} ({score}%) cached={cached} — {url}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
