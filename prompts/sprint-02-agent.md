# IDE agent prompt — Sprint 2 only (JobSignal)

You are implementing **Sprint 2**: data ingestion, search validation, and **cache system** for JobSignal.

## Preconditions

Read `docs/JOBSIGNAL-MASTER-PLAN.md` and Sprint 1 outputs (`docs/ADR-*`, `docs/TRUST-MATRIX.md`, response schema). If Sprint 1 artifacts are missing, **stop** and produce minimal stubs for those docs first, then continue—still **no** Sprint 3 UI/scoring integration beyond what Sprint 2 needs.

## Hard boundaries

- **Do not** build the full scoring verdict UX of Sprint 3; backend may return provisional internal DTOs only.
- **Do not** add features from the extension list unless required for Sprint 2.
- **Do not** store tenant-private notes or secrets in shared cache rows.

## Accuracy-first

- Ingestion failures must map to **safe** states (VERIFY/SKIP semantics in logs—not necessarily user-facing until Sprint 3).
- Search results are **evidence**, not truth: document how snippets are capped and redacted for cache.

## Caching rules

- TTL 10–30 days (config); default 14 unless repo already standardized.
- Keys include `pipeline_version` / scorer placeholder version as per master plan.
- Add an **automated test** that fails if tenant-only fields appear in serialized cache payload.

## Required outputs

1. Normalization + key derivation modules with unit tests.
2. Fetch and search adapters behind interfaces; use mocks in CI.
3. Cache get/set with explicit schema for cached record.
4. Update `docs/` with any deviation from master plan (short ADR note).

## Tests

- Unit: normalization, keys, TTL calculation.
- Integration: miss → write → hit (mocked HTTP/search).

## Safe fallback

- If provider credentials missing in dev, code must **fail closed** (no fabricated APPLY data).

## Stop condition

Sprint 2 **Done criteria** in `sprints/sprint-02-ingestion-cache.md` satisfied. Do not implement final public REST response polish unless needed for cache tests.
