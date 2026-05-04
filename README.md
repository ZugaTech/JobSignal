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

**Integrated baseline (earlier planning):** [`docs/JOBSIGNAL-MASTER-PLAN.md`](docs/JOBSIGNAL-MASTER-PLAN.md)

**Agent prompts (by sprint):** [`prompts/`](prompts/)

**High-level sprint tracks:** [`sprints/`](sprints/)

## Repository rules

Editor and agent guidance: [`.cursor/rules/JOBSIGNAL-RULES.mdc`](.cursor/rules/JOBSIGNAL-RULES.mdc) (accuracy-first, documentation-led).

## Local configuration

Copy `.env.example` to `.env` for local development when implementation begins. Never commit secrets.
