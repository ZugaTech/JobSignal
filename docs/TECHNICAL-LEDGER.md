# JobSignal — Technical ledger (post–Sprint 4)

**Purpose:** single pane of glass for what is truly ✅/⚠️/❌ and what’s needed to ship a hackathon demo without violating `docs/final_scope.md`.

**Legend**

- 🟢 **Done** — implemented, tested, docs aligned  
- 🟡 **Partial** — stubbed, works only locally, or missing wiring  
- 🔴 **Not started** — no implementation  
- ⚪ **Blocked** — needs human decision/secret/vendor choice  

**Last verified:** 2026-05-05  

**Baseline verification**

- `python -m pytest`: **48 passed** (local)
- Latest commit at time of ledger creation: `af0310d`

---

## 1) Runtime & API

| Item | Status | Notes |
|------|--------|------|
| Python runtime / test harness (`pyproject.toml`, pytest) | 🟢 | Core libs + tests run. |
| HTTP server app | 🔴 | No ASGI/WSGI app exists in `backend/` (only core modules). |
| Routes: `/health` + `/ready` | 🟡 | Payload helpers exist (`backend/core/health.py`), but no HTTP wiring. |
| Route: `/v1/verify` (or chosen) | 🔴 | No request handler yet; frontend still uses mock response. |
| CORS / request id | 🔴 | Needs HTTP framework choice. |

---

## 2) Orchestration (normalize → evidence → score → report → cache)

| Item | Status | Notes |
|------|--------|------|
| Raw input validation | 🟢 | `backend/core/inputs.py` + tests. |
| Normalization (URL/text + hashes) | 🟢 | `backend/core/normalization.py` + tests. |
| Entity extraction (heuristic) | 🟢 | `backend/core/extraction.py` + tests. |
| Evidence ordering | 🟢 | `backend/core/source_evidence.py` + tests. |
| Scoring + verdict + confidence | 🟢 | `backend/core/scoring.py` + tests. |
| Public report envelope | 🟢 | `backend/core/report.py` + tests. |
| Orchestrator function (end-to-end in code) | 🔴 | No single function that calls: validate → normalize → cache → collectors → score → report. |

---

## 3) External integrations (fetch / search)

| Item | Status | Notes |
|------|--------|------|
| Search adapter (real provider) | 🔴 | Docs only (`docs/source_validation.md`). |
| Fetch adapter (SSRF-safe) | 🔴 | Not implemented; only limits/env/docs exist. |
| Deterministic fixtures for CI | 🔴 | Not implemented (required for stable demo/CI). |

---

## 4) Frontend

| Item | Status | Notes |
|------|--------|------|
| Minimal UI + states | 🟢 | Static `frontend/*` with phases and uncertainty strip. |
| Client-side input validation | 🟢 | `frontend/app.js` validates lengths + URL shape. |
| Replace `mockVerify` with real `fetch` | 🟡 | Mock still present; needs API route + wiring. |
| Cache-hit display | 🟢 | Badge overlay wired to `cache.hit` (mocked). |
| Error handling | 🟢 | Client validation and network error path shown; needs real API integration test later. |

---

## 5) Cache backend

| Item | Status | Notes |
|------|--------|------|
| Key derivation + TTL behavior (in-memory) | 🟢 | `cache_key.py`, `cache_store.py` + tests. |
| Redis-backed cache | 🔴 | Not implemented. |
| Shared cache payload privacy guard | 🟢 | `cache_payload.py` + tests incl. forbidden keys. |
| Readiness cache ping | 🟡 | `health.py` supports `cache_ping_ok` flag, but no real ping. |

---

## 6) Config & env

| Item | Status | Notes |
|------|--------|------|
| `.env.example` completeness | 🟡 | Has main vars; will need framework-specific vars once API exists. |
| `EnvConfig.load(strict=…)` | 🟢 | Enforces TTL range and cache URL in staging/prod/strict. |

---

## 7) CI/CD

| Item | Status | Notes |
|------|--------|------|
| GitHub Actions pytest | 🔴 | No workflow in `.github/workflows/` yet. |

---

## 8) Deploy

| Item | Status | Notes |
|------|--------|------|
| Deployment checklist + rollback | 🟢 | `docs/deployment_readiness.md` + `deployment/RUNBOOK.md`. |
| Actual deploy target configured | ⚪ | Needs human choice (Render/Fly/Railway/etc.). |

---

## 9) Hackathon submission readiness

| Item | Status | Notes |
|------|--------|------|
| Demo script | 🔴 | Not written. |
| “One command” local run | 🔴 | Needs API wiring + optional `python -m http.server` for static UI. |

---

## 10) Known risks (carried)

- 🟡 **PSL-naive domain parsing** (`registrable_domain_naive`) may mis-handle some ccTLDs.
- 🟡 **Prompt guard is heuristic** and must not be treated as proof of safety.
- 🔴 **No real fetch/search adapters** (largest demo gap).
- 🟡 **Static UI uses mock**; needs `/v1/verify` before demo is end-to-end.

---

## Next actions (smallest vertical slice)

1. Implement **minimal HTTP API** (FastAPI or Flask) with `/health`, `/ready`, `/v1/verify` calling a new orchestrator function; keep scope tight (no background jobs).
2. Replace frontend `mockVerify()` with real `fetch()` for the happy path; keep mock as fallback only in dev if API absent (documented).
3. Add deterministic “fixtures mode” for fetch/search adapters (pure local JSON) so CI is stable.

