# JobSignal — Technical ledger (post–Sprint 4)

**Purpose:** single pane of glass for what is truly ✅/⚠️/❌ and what’s needed to ship a hackathon demo without violating `docs/final_scope.md`.

**Legend**

- 🟢 **Done** — implemented, tested, docs aligned  
- 🟡 **Partial** — stubbed, works only locally, or missing wiring  
- 🔴 **Not started** — no implementation  
- ⚪ **Blocked** — needs human decision/secret/vendor choice  

**Last verified:** 2026-05-06  

**Baseline verification**

- `python -m pytest`: **94 passed** (local; Sprint 6 recommendations + Sprint 9 fetch)
- Scope addendum: `docs/scope_addendum_2026-05-06.md`
- Scorer: `SCORER_VERSION = 3.1.0` (description-only intelligence; cache-invalidating)

---

## 1) Runtime & API

| Item | Status | Notes |
|------|--------|------|
| Python runtime / test harness (`pyproject.toml`, pytest) | 🟢 | Core libs + tests run. |
| HTTP server app (FastAPI) | 🟢 | `backend/api/main.py` (`create_app`) + `Procfile`. |
| Routes: `/health` + `/ready` | 🟡 | HTTP wiring exists; `/ready` does not ping real cache yet. |
| Route: `/v1/verify` | 🟡 | JSON + **multipart**; optional **`recommendations_enabled`**; fixtures + optional **similar jobs** (SerpAPI/fixture) max 3. |
| CORS / request id | 🟡 | CORS allows `*` for demo; request-id propagation not yet implemented. |

---

## 2) Orchestration (normalize → evidence → score → report → cache)

| Item | Status | Notes |
|------|--------|------|
| Raw input validation | 🟢 | `backend/core/inputs.py` + tests. |
| Normalization (URL/text + hashes) | 🟢 | `backend/core/normalization.py` + tests. |
| Entity extraction (heuristic) | 🟢 | `backend/core/extraction.py` + tests. |
| Evidence ordering | 🟢 | `backend/core/source_evidence.py` + tests. |
| Scoring + verdict + confidence | 🟢 | `backend/core/scoring.py` + tests. **3.1.0** adds `TEXT_PATTERN_MATCH` SKIP + Path C (text-only APPLY exception, capped `medium`). |
| Description-only LLM signals (T3) | 🟢 | `backend/core/llm_fireworks.map_llm_payload_to_signals` produces `jd_specificity`, `jd_red_flags`, `jd_missing_fields`, `jd_scam_indicators`, `jd_content_farm_score`, `jd_ai_generated_score`, `jd_recruiter_intent_score`, `jd_employer_identifiability` at tier `T3` with user-facing labels. |
| Public report envelope | 🟢 | `backend/core/report.py` + tests. |
| Orchestrator function (end-to-end in code) | 🟡 | Orchestrator: image ingest → normalize → live fetch → verify → **`recommendations` attach** (`report_schema_version` **1.2.0** + `ingestion`). |

---

## 3) External integrations (fetch / search)

| Item | Status | Notes |
|------|--------|------|
| Search adapter (real provider) | 🟡 | **SerpAPI** wired for recommendations + **JSON fixture** provider; Zenserp/Bing/Google CSE still optional/future. |
| Fetch adapter (SSRF-safe) | 🟡 | **Primary** URL GET + signals: `backend/core/fetch_job_page.py` behind `ENABLE_JOB_FETCH` (default off); candidate/search fetches still pending (Sprint 6+). |
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

---

## Change log

| Date | Change | Why |
|------|--------|-----|
| 2026-05-06 | Description-only intelligence: `SCORER_VERSION` 3.1.0, `TEXT_PATTERN_MATCH` SKIP, Path C (text-only APPLY capped `medium`), expanded T3 LLM signals. Tests 64 → **79**. | Description-only inputs now produce a real, useful answer instead of a generic "VERIFY low". |

