#!/usr/bin/env python3
"""Capture deck PNGs for ``jobsignal_deck_v2.py`` (Playwright + local API).

Requires: ``pip install playwright`` and ``playwright install chromium``.

Prereq: build the UI (``npm run run build``) and run the API on port 8080, e.g.:

  set PORT=8080
  set NODE_ENV=development
  python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deck_assets"
BASE = "http://127.0.0.1:8080"

HERO_URL = "https://example.com/careers/software-engineer"

JD_VERIFY = (
    "Senior Software Engineer at Acme Corp. Responsibilities include leading backend development, "
    "mentoring junior engineers, and collaborating with product teams. Requirements: 5+ years "
    "Python experience, distributed systems knowledge, strong communication skills. We offer "
    "competitive salary, health benefits, and remote flexibility. This role is based in Austin, "
    "TX and reports to the VP of Engineering. Must have experience with cloud infrastructure and "
    "CI/CD pipelines. Apply with resume and cover letter. Acme is an equal opportunity employer."
)

SKIP_URL = "https://boards.greenhouse.io/example/jobs/123456"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install Playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="domcontentloaded", timeout=60_000)

        # --- 1) Hero: URL tab, prefilled, no submit
        page.get_by_text("Paste URL", exact=True).click()
        page.locator('input[type="url"]').fill(HERO_URL)
        card = page.locator("div.glass.rounded-2xl").first
        card.screenshot(path=str(OUT / "slide01_hero.png"))

        # --- 2) VERIFY: description tab
        page.get_by_text("Description", exact=True).click()
        page.locator("textarea").fill(JD_VERIFY)
        page.get_by_role("button", name="Check Posting").click()
        page.get_by_text("Verify First", exact=True).wait_for(timeout=120_000)
        dlg = page.locator("[role=dialog].fixed.inset-0").first
        dlg.locator("div.max-w-7xl").screenshot(path=str(OUT / "slide09_panel1_verify.png"))
        page.get_by_role("button", name="Close results").click()
        page.locator("[role=dialog]").wait_for(state="hidden", timeout=30_000)

        # --- 3) SKIP: URL tab
        page.get_by_text("Paste URL", exact=True).click()
        page.locator('input[type="url"]').fill(SKIP_URL)
        page.get_by_role("button", name="Check Posting").click()
        page.get_by_text("Skip", exact=True).wait_for(timeout=120_000)
        dlg = page.locator("[role=dialog].fixed.inset-0").first
        dlg.locator("div.max-w-7xl").screenshot(path=str(OUT / "slide09_panel2_skip.png"))
        page.get_by_role("button", name="Close results").click()
        page.locator("[role=dialog]").wait_for(state="hidden", timeout=30_000)

        # --- 4) Two-panel: reuse VERIFY modal (same verdict; wide viewport shows both columns)
        page.get_by_text("Description", exact=True).click()
        page.locator("textarea").fill(JD_VERIFY)
        page.get_by_role("button", name="Check Posting").click()
        page.get_by_text("Verify First", exact=True).wait_for(timeout=120_000)
        dlg = page.locator("[role=dialog].fixed.inset-0").first
        dlg.locator("div.max-w-7xl").screenshot(path=str(OUT / "slide09_panel3_twopanel.png"))

        browser.close()

    print(f"Wrote PNGs under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
