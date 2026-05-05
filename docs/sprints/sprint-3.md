# Sprint 3 — Notes and completion record

**Status:** scoring, decision output contract usage, public report envelope, minimal static frontend, and tests shipped. **No** Sprint 4 deployment hardening; **no** rebuild of Sprint 2 ingestion collectors.

**Date:** 2026-05-04.

## Deliverables

| Item | Location |
|------|----------|
| Trust score definition | `docs/scoring.md` |
| APPLY / VERIFY / SKIP + confidence | `docs/decision_logic.md` |
| Frontend states + uncertainty + cache hit UX | `docs/frontend_flow.md` |
| Scorer implementation | `backend/core/scoring.py` (`SCORER_VERSION`) |
| Public report JSON helper | `backend/core/report.py` |
| Unit tests (verdict + honesty guard + report) | `tests/test_scoring.py` |
| Frontend smoke tests | `tests/test_frontend_smoke.py` |
| Minimal UI | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` |

## Decision logic improvement (documented)

**Borderline APPLY downgrade:** APPLY candidates with **T1 best = medium** and **≤ two** `medium+` evidence rows are assigned confidence **`low`**, triggering the **honesty guard** (`HONESTY_GUARD`) that forces **`VERIFY`**. Rationale: avoid an overly optimistic APPLY when employer-controlled evidence is thin.

## Out of scope (honored)

- Real `/v1/verify` HTTP server and fetch/search wiring (frontend uses **mock** data).
- Playwright/Cypress E2E (smoke tests assert static assets and copy instead).
- Job board features, blacklist UX, or legal accusation language.

## Done criteria (Sprint 3 prompt)

- [x] Trust score / gates documented and implemented  
- [x] Verdict + confidence + warnings surfaced  
- [x] Report schema versioned (`report_schema_version`)  
- [x] Frontend states: idle, loading, success, warning, cache hit overlay, error  
- [x] Tests for scoring + verdict + static frontend smoke  
- [x] User flow documented (`frontend_flow.md`)  

## Commands

```bash
python -m pytest
```

Open `frontend/index.html` in a browser (static) for the demo UI.
