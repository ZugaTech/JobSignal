# JobSignal — Technical ledger

**Purpose:** Single view of implementation status, gaps, and risks—aligned with [`final_scope.md`](final_scope.md) and intended for reviewers (engineering hires, auditors, ops).

**Legend**

- 🟢 **Done** — implemented, covered by tests where practical, docs aligned  
- 🟡 **Partial** — works but incomplete, demo-only defaults, or needs manual verification  
- 🔴 **Not started** — no implementation  
- ⚪ **Blocked** — vendor choice, credentials, or policy decision required  

**Last reviewed:** 2026-05-12  

**Verify locally:** `pip install -r requirements.txt && npm ci && npm run build && set PYTHONPATH=. && pytest` (see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) for the CI matrix).

**Current scorer:** `SCORER_VERSION = 3.4.0` (`backend/core/scoring.py`).

---

## 1) Runtime and API

| Item | Status | Notes |
|------|--------|------|
| Python + pytest (`pyproject.toml`) | 🟢 | Core library and API tests. |
| FastAPI app | 🟢 | `backend/api/main.py` (`create_app`); `Procfile` for PaaS. |
| `/health` (liveness) | 🟢 | Always cheap: process up. |
| `/ready` (readiness) | 🟢 | Dependency booleans; **Redis ping** when `CACHE_URL` set; live provider probes only when `PROBE_PROVIDERS_ON_READY` is enabled. |
| `/v1/verify` | 🟢 | JSON + multipart; optional recommendations; env-driven rate limits. |
| CORS / request correlation | 🟡 | Configurable origins; structured request IDs not uniformly propagated end-to-end. |

---

## 2) Pipeline (normalize → evidence → score → report → cache)

| Item | Status | Notes |
|------|--------|------|
| Input validation | 🟢 | `backend/core/inputs.py`. |
| Normalization | 🟢 | `backend/core/normalization.py`. |
| Extraction / evidence ordering | 🟢 | `extraction.py`, `source_evidence.py`. |
| Search-backed evidence | 🟢 | Serper primary; SerpApi fallback path where configured (`backend/core/coordinator.py`, `evidence.py`). |
| SSRF-safe primary fetch | 🟢 | `backend/core/fetch_job_page.py` behind `ENABLE_JOB_FETCH`. |
| Scoring + verdict | 🟢 | `backend/core/scoring.py`, `report.py`, honesty guards documented in `docs/decision_logic.md`. |
| Optional LLM signals | 🟢 | Behind `ENABLE_LLM_SIGNALS`; mapping tested without live provider calls. |
| End-to-end orchestration | 🟢 | `backend/core/orchestrator.py` (image ingest, fetch, recommendations, cache). |

---

## 3) Frontend and clients

| Item | Status | Notes |
|------|--------|------|
| Primary UI | 🟢 | React + Vite under `src/`; production bundle `dist/` served by FastAPI. |
| Legacy static UI | 🟡 | Optional `frontend/` mount when `dist/` missing **and** folder exists; primary UI is React in `src/` → `dist/`. |
| Chrome extension | 🟢 | `extension/` — loads unpacked; configurable API base. |
| Automated browser E2E | 🔴 | Not in CI; manual + pytest API/contract coverage. |

---

## 4) Cache

| Item | Status | Notes |
|------|--------|------|
| In-memory TTL cache | 🟢 | Default local / single-instance. |
| Redis (`CACHE_URL`) | 🟢 | `RedisCache`; `/ready` reflects ping result. |
| Cross-tenant shared payload safety | 🟢 | `cache_payload.py`, `tests/test_cache_privacy.py`. |

---

## 5) Delivery and CI/CD

| Item | Status | Notes |
|------|--------|------|
| GitHub Actions | 🟢 | Frontend build + pytest on push/PR to `main`. |
| Deploy docs | 🟢 | `deploy/RAILWAY.md`, `deploy/CHECKLIST.md`, `docs/deployment_readiness.md`, `deployment/RUNBOOK.md`. |
| Demo walkthrough | 🟢 | `docs/demo_script.md`. |
| Fixture corpus | 🟡 | JSON fixtures exist; expanding curated real-world hashes remains useful for regression demos. |

---

## 6) Known risks (explicit)

- 🟡 **Heuristic prompt guard** — reduces trivial injection patterns; not a substitute for secure prompt design and trusted-model boundaries.
- 🟡 **Public suffix / registrable domain list** — hand-maintained multi-label suffixes; exotic TLDs may need updates (`backend/core/normalization.py`).
- 🟡 **Provider cost and quotas** — Serper/Fireworks usage scales with traffic; use env budgets and disable live probes on `/ready` in production (`PROBE_PROVIDERS_ON_READY`).
- 🟡 **Vision path costs** — screenshot flows require keys + `ENABLE_IMAGE_VERIFY`; CI uses stubs/monkeypatches.

---

## Next improvements (optional)

1. Expand **fixture-backed regression set** (stable hashes + documented recording procedure).
2. Add **Playwright** or equivalent smoke suite for the React UI (non-flaky, mocked API option).
3. Tighten **CORS defaults** for production templates (explicit origins vs wildcard).

---

## Change log

| Date | Change | Why |
|------|--------|-----|
| 2026-05-12 | Ledger rewritten for accuracy (CI, `/ready`, adapters, frontend stack); removed contradictory hackathon-only rows | Employer/public review readiness |
| 2026-05-06 | Prior ledger tracked Sprint 4→11 integration | Historical |
