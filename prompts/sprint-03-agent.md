# IDE agent prompt — Sprint 3 only (JobSignal)

You are implementing **Sprint 3**: **scoring / verdict engine**, API surface, and **frontend** that makes trust and uncertainty visible.

## Preconditions

Sprint 2 normalization, ingestion contracts, and cache behavior exist or are stubbed with the same interfaces you will call.

## Hard boundaries

- **Do not** perform Sprint 4 CI hardening, production infra, or full security audit—note gaps as TODO with severity.
- **Do not** weaken VERIFY gates to make demos “more impressive.”

## Accuracy-first

- Rule engine owns `APPLY` / `VERIFY` / `SKIP`. LLM (if any) may **not** override rule engine to APPLY.
- UI must show warnings, cache hit, and low-confidence copy.

## Caching and multi-tenant

- Respect shared cache schema; when adding response fields for tenant features, keep them **out** of shared cache document.

## Required outputs

1. Versioned scorer + table-driven tests from trust matrix.
2. Public API returning the frozen schema (or updated schema with ADR).
3. Frontend per master plan §9.
4. At least one E2E test for VERIFY or error path.

## Tests

- Scoring: conflicting signals, missing T1, duplicates.
- API: schema validation rejects incomplete payloads.

## Safe fallback

- On scorer internal error, return user-safe error with **no** verdict or VERIFY per API policy—document which.

## Stop condition

Sprint 3 **Done criteria** in `sprints/sprint-03-scoring-frontend.md` met.
