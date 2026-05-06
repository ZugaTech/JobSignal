# JobSignal — Technical ledger (post–Sprint 4)

**Purpose:** single pane of glass for what is truly ✅/⚠️/❌ and what’s needed to ship a hackathon demo without violating `docs/final_scope.md`.

**Legend**

- 🟢 **Done** — implemented, tested, docs aligned  
- 🟡 **Partial** — stubbed, works only locally, or missing wiring  
- 🔴 **Not started** — no implementation  
- ⚪ **Blocked** — needs human decision/secret/vendor choice  

**Last verified:** 2026-05-06  

**Baseline verification**

- `python -m pytest`: **62 passed** (local; image ingest + multipart verify)
- Scope addendum: `docs/scope_addendum_2026-05-06.md`

---

## 1) Runtime & API

| Item | Status | Notes |
|------|--------|------|
| Python runtime / test harness (`pyproject.toml`, pytest) | 🟢 | Core libs + tests run. |
| HTTP server app (FastAPI) | 🟢 | `backend/api/main.py` (`create_app`) + `Procfile`. |
| Routes: `/health` + `/ready` | 🟡 | HTTP wiring exists; `/ready` does not ping real cache yet. |
| Route: `/v1/verify` | 🟡 | JSON + **multipart** (`job_image`); fixtures evidence; optional **Fireworks vision** behind `ENABLE_IMAGE_VERIFY`. |
| CORS / request id | 🟡 | CORS allows `*` for demo; request-id propagation not yet implemented. |

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
| Orchestrator function (end-to-end in code) | 🟡 | `backend/core/orchestrator.py` wires validate→**optional image ingest**→normalize→cache→fixtures→score→report (`report_schema_version` 1.1.0 + `ingestion`). Live collectors pending. |

---

## 3) External integrations (fetch / search)

| Item | Status | Notes |
|------|--------|------|
| Search adapter (real provider) | ⚪ | Candidate providers (planned multi-provider fallback): **SerpAPI**, **Zenserp**, **Bing Web Search**, **Google Programmable Search**. |
| Fetch adapter (SSRF-safe) | 🔴 | Not implemented; fixtures-only evidence currently. |
| Deterministic fixtures for CI | 🟡 | `data_sources/fixtures/verify_fixtures.json` added; needs real hashes and more cases. |

---

## 4) Frontend

| Item | Status | Notes |
|------|--------|------|
| Minimal UI + states | 🟢 | Static `frontend/*` with phases and uncertainty strip. |
| Client-side input validation | 🟢 | `frontend/app.js` validates lengths + URL shape. |
| Replace `mockVerify` with real `fetch` | 🟢 | Frontend calls `http://localhost:8080/v1/verify` by default; **multipart** when a screenshot is selected. |
| Cache-hit display | 🟢 | Badge overlay wired to `cache.hit` (mocked). |
| Error handling | 🟡 | Client validation and network error path shown; needs real “API down” manual check in demo script. |

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
| `.env.example` completeness | 🟡 | Includes `ENABLE_IMAGE_VERIFY`, `FIREWORKS_VISION_MODEL`, `IMAGE_MAX_BYTES`. |
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
| Actual deploy target configured | 🟡 | **Railway chosen**; repo needs Railway-specific run instructions and env list verified. |

---

## 9) Hackathon submission readiness

| Item | Status | Notes |
|------|--------|------|
| Demo script | 🔴 | Not written. |
| “One command” local run | 🟡 | API + static UI exist; document `uvicorn` + static server for judges. |

---

## 10) Known risks (carried)

- 🟡 **PSL-naive domain parsing** (`registrable_domain_naive`) may mis-handle some ccTLDs.
- 🟡 **Prompt guard is heuristic** and must not be treated as proof of safety.
- 🔴 **No real fetch/search adapters** (largest demo gap).
- 🟡 **Vision path** needs real `FIREWORKS_API_KEY` + `ENABLE_IMAGE_VERIFY=1` for live screenshot demos; CI uses stubs.

---

## Next actions (smallest vertical slice)

1. Expand fixtures: add 3–5 real job URLs and populate `verify_fixtures.json` with their real sha256 keys (documented method).
2. Add **live** search adapter behind interface with **fixtures-first** and **multiple-provider fallback** (per your preference), preserving CI determinism.
3. Add Railway “how to run” section + ensure `/ready` semantics match deploy reality (cache ping when Redis configured).

