# JobSignal

Applicant-side job posting verification: reduce wasted applications to ghost, duplicate, stale, or low-trust listings.

## Current status

**Sprint 1 (complete):** architecture, trust model, scope, environment contract, and folder policy are documented under `docs/`. No feature application code yet—see `docs/sprints/sprint-1.md` for the completion checklist.

## Where to read first

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | End-to-end flow, normalized inputs, response schema, cache keys, multi-tenant |
| [`docs/trust_model.md`](docs/trust_model.md) | T1/T2/T3 ranking, VERIFY gates, signal ids |
| [`docs/scope.md`](docs/scope.md) | MVP in-scope / out-of-scope |
| [`docs/environment.md`](docs/environment.md) | Environment variables and validation |
| [`docs/folder_structure.md`](docs/folder_structure.md) | Repo layout and minimal future dependencies |
| [`docs/sprints/sprint-1.md`](docs/sprints/sprint-1.md) | Sprint 1 notes, validation, improvement log |
| [`docs/data_flow.md`](docs/data_flow.md) | Sprint 2 — ingestion → cache → evidence pipeline |
| [`docs/cache_design.md`](docs/cache_design.md) | Sprint 2 — TTL, keys, cross-tenant, invalidation |
| [`docs/source_validation.md`](docs/source_validation.md) | Sprint 2 — sources, search packs, extraction |
| [`docs/sprints/sprint-2.md`](docs/sprints/sprint-2.md) | Sprint 2 notes and completion record |
| [`docs/PROGRESS-LOG.md`](docs/PROGRESS-LOG.md) | Running log of shipped work and sprint status |
| [`docs/scoring.md`](docs/scoring.md) | Sprint 3 — trust score composition |
| [`docs/decision_logic.md`](docs/decision_logic.md) | Sprint 3 — APPLY / VERIFY / SKIP gates |
| [`docs/frontend_flow.md`](docs/frontend_flow.md) | Sprint 3 — UI states and uncertainty |
| [`docs/sprints/sprint-3.md`](docs/sprints/sprint-3.md) | Sprint 3 completion notes |
| [`docs/security.md`](docs/security.md) | Sprint 4 — threats, cache privacy, injection, env hygiene |
| [`docs/reliability.md`](docs/reliability.md) | Sprint 4 — tests, health checks, failure philosophy |
| [`docs/deployment_readiness.md`](docs/deployment_readiness.md) | Sprint 4 — go-live checklist + rollback |
| [`docs/final_scope.md`](docs/final_scope.md) | Sprint 4 — frozen in/out scope |
| [`docs/sprints/sprint-4.md`](docs/sprints/sprint-4.md) | Sprint 4 completion notes + remaining risks |
| [`deployment/RUNBOOK.md`](deployment/RUNBOOK.md) | Operator incidents (stub) |

**Integrated baseline (earlier planning):** [`docs/JOBSIGNAL-MASTER-PLAN.md`](docs/JOBSIGNAL-MASTER-PLAN.md)

**Agent prompts (by sprint):** [`prompts/`](prompts/)

**High-level sprint tracks:** [`sprints/`](sprints/)

## Repository rules

Editor and agent guidance: [`.cursor/rules/JOBSIGNAL-RULES.mdc`](.cursor/rules/JOBSIGNAL-RULES.mdc) (accuracy-first, documentation-led).

## Local configuration

Copy `.env.example` to `.env` for local development when implementation begins. Never commit secrets.
