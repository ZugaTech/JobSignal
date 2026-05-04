# Sprint 1 — Architecture, workspace, and trust model

## Sprint goal

Establish a reviewable architecture and **trust model** (signals, tiers, gates) so later sprints can implement without re-deciding fundamentals.

## Scope

- Repo layout aligned with `docs/JOBSIGNAL-MASTER-PLAN.md` (already scaffolded).
- ADR or short architecture note: request flow, components, data stores (logical).
- Trust matrix document: T1/T2/T3 definitions, forbidden paths to `APPLY`.
- OpenAPI or JSON Schema **sketch** for verify response (no full server required).
- Definition of `pipeline_version` and `scorer_version` bump policy.

## Tasks

1. Confirm folder READMEs match intended ownership.
2. Write `docs/ADR-001-architecture.md` (or equivalent): diagram + sequence for verify request.
3. Write `docs/TRUST-MATRIX.md`: signal list, tiers, score caps, VERIFY gates.
4. Freeze response field names with examples (happy / weak / error).
5. Agree on search provider interface (methods + timeout + error types) **without** vendor lock-in text as fact—use “implementation choice” language.

## Done criteria

- A new engineer can read docs and explain why `APPLY` cannot fire without T1/T2 support.
- Response schema reviewed and checked into `docs/`.
- No production application code required for this sprint’s completion (spec-only is OK).

## Risk

Ambiguity in “official careers” detection → **Mitigation:** document heuristics + false-positive/false-negative acceptance.

## Fallback

If architecture slides: still deliver trust matrix + response schema as **blocking** artifacts for Sprint 2.

## Manual checklist

- [ ] Walkthrough: user submits URL → listed steps through verdict
- [ ] Trust matrix peer-reviewed (second pair of eyes)
- [ ] Glossary: tenant, fingerprint, signal, verdict
