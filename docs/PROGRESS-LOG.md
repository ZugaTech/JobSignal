# JobSignal — Progress log

Use this file as a **running journal** of what shipped, when, and why. Append new sections **newest first** under “Log entries” (or oldest-first—pick one convention and stick to it; this file uses **newest first**).

**Convention for new entries**

1. Date (ISO): `YYYY-MM-DD`
2. Short title
3. Bullets: done / deferred / risks / links to commits or PRs if helpful

---

## Log entries (newest first)

### 2026-05-04 — Sprint 2: ingestion, cache, tests, docs

- **Docs:** `docs/data_flow.md`, `docs/cache_design.md`, `docs/source_validation.md`, `docs/sprints/sprint-2.md`; README links updated.
- **Code:** `backend/core/normalization.py`, `extraction.py`, `cache_key.py`, `cache_payload.py` (tenant strip + JSON guard), `cache_store.py` (in-memory TTL), `source_evidence.py` (trust ordering).
- **Tests:** `tests/test_*.py` (normalization, cache key, TTL hit/miss, tenant strip, evidence ordering, extraction smoke); `pyproject.toml` with pytest config; `requires-python >=3.10`.
- **Tooling:** `.gitignore` extended for `__pycache__`, `.pytest_cache`, `*.pyc`.
- **Design decision logged:** composite public cache fingerprint `u:<sha>|t:<sha>` when both URL and pasted text exist (`docs/cache_design.md`, `docs/sprints/sprint-2.md`).
- **Deferred:** real HTTP fetch/search adapters, PSL-aware domain parsing, Sprint 3 verdict/UI, Sprint 4 hardening/deploy.
- **Verify:** `python -m pytest` — 12 tests passing (session verification on Python 3.12).

### 2026-05-04 — Core output contract (decision schema)

- **Code:** `backend/core/decision_schema.py` — `Verdict` enum; `DecisionResponse` with top-level `confidence: Literal["high","medium","low"]`; `VerifyResponse` extends with optional envelope fields; comment that `reasons` must contain **at least two** items (contract for scorer).
- **Commits (examples):** `feat: define decision schema and core output contract`; follow-up `refactor(core): add DecisionResponse with top-level confidence and reasoning floor`.

### 2026-05-04 — Sprint 1: architecture, trust, scaffold, git history

- **Docs:** `docs/architecture.md`, `trust_model.md`, `scope.md`, `environment.md`, `folder_structure.md`, `docs/sprints/sprint-1.md`; retained `docs/JOBSIGNAL-MASTER-PLAN.md`, `ADR-001-architecture.md`, `TRUST-MATRIX.md`; agent prompts under `prompts/`; sprint outlines under `sprints/`.
- **Repo:** reserved dirs (`backend/`, `frontend/`, `tests/`, `cache/`, `security/`, `deployment/`, `data_sources/`) with README stubs; root `README.md`, `.env.example`, `.cursor/rules/JOBSIGNAL-RULES.mdc`.
- **Process:** many **small commits** (docs and chores split) for hackathon-visible history; remote `origin` added over session (push enabled after initial “no remote” state).
- **Explicit non-goals for Sprint 1:** no product UI, no fetch/search/cache implementation.

### 2026-05-04 — Session start: rules alignment and planning baseline

- Adopted workspace rules in `.cursor/rules/JOBSIGNAL-RULES.mdc` (accuracy-first, docs-before-code, global cache + tenant privacy, VERIFY when weak).
- Initial planning scaffold and folder tree created where the repo was previously empty aside from `.cursor`.

---

## Cumulative sprint status (snapshot)

| Sprint | Status | Primary artifacts |
|--------|--------|---------------------|
| **1** | Done (docs + scaffold) | `architecture.md`, `trust_model.md`, `scope.md`, `environment.md`, `folder_structure.md`, `docs/sprints/sprint-1.md` |
| **2** | Done (docs + core modules + tests) | `data_flow.md`, `cache_design.md`, `source_validation.md`, `backend/core/*`, `tests/*`, `docs/sprints/sprint-2.md` |
| **3** | Not started | Scoring, API polish, frontend flow (per roadmap) |
| **4** | Not started | Hardening, CI, deployment readiness (per roadmap) |

---

## Follow-ups (backlog from sprints)

- [ ] Wire `SearchAdapter` + fetch with **recorded** fixtures for CI.
- [ ] Replace naive registrable-domain parsing with PSL-aware library; bump `NORMALIZATION_VERSION`.
- [ ] Align `docs/architecture.md` API narrative with `DecisionResponse` / `confidence` band-only if product locks that contract everywhere.
- [ ] Sprint 3: rule engine + minimal UI per `prompts/sprint-03-agent.md`.

---

## How to append

Add a new `### YYYY-MM-DD — Title` block **above** the previous dated block under “Log entries”, or continue a same-day block if the work is one continuous thread.
