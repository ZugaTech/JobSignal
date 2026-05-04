# ADR-001 — Verification pipeline architecture (planning)

**Canonical detail (Sprint 1):** see [`architecture.md`](architecture.md). This ADR remains a short decision record; avoid duplicating long sections here.

## Status

Accepted (planning phase). Implementation must follow `JOBSIGNAL-MASTER-PLAN.md` and `architecture.md`; revise via new ADR if behavior changes.

## Context

JobSignal verifies a **public job fingerprint** (URL and/or pasted text) using multiple signals, returns a verdict with explicit uncertainty, and uses a **shared cache** for identical normalized inputs.

## Decision

1. **Synchronous request path** — Client calls API; orchestrator runs: validate input → normalize → cache get → (on miss) parallel source collection with budgets → rule-based scorer → cache set (stripped) → response.
2. **Rule engine is authoritative** for `APPLY` / `VERIFY` / `SKIP`. Optional LLM may annotate or extract entities **only** if outputs are tied to signal ids and cannot force `APPLY`.
3. **Logical components** — API layer; normalization; fetcher; search adapter; dedupe/stale helpers; scorer; cache store; observability.
4. **Multi-tenant** — `tenant_id` for quotas and audit; **shared** verification payload keyed by public fingerprint versions.

## Consequences

- Must maintain `pipeline_version` / `scorer_version` for cache key evolution.
- CI must enforce cache serialization tests for tenant leakage.

## Non-decisions (implementation picks)

Specific web framework, search vendor, and cache product are **not** fixed by this ADR—only interfaces and safety properties from the master plan.
