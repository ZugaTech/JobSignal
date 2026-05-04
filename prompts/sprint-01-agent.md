# IDE agent prompt — Sprint 1 only (JobSignal)

You are working on the **JobSignal** repository. Obey `docs/JOBSIGNAL-MASTER-PLAN.md` and `.cursor/rules/JOBSIGNAL-RULES.mdc`.

## Hard boundaries

- Work **only** on Sprint 1: architecture, workspace hygiene, and **trust model documentation**.
- **Do not** implement Sprint 2+ behavior (no real fetch/search/cache code, no full API server, no production frontend).
- **Do not** jump ahead to scoring code or deployment automation unless it is a **stub** explicitly labeled non-functional and required for types only—prefer zero runtime code.

## Accuracy-first philosophy

- Rule-first trust: document when `APPLY`, `VERIFY`, and `SKIP` are allowed.
- Never document a path where `APPLY` is allowed without T1/T2-class support.

## Caching and multi-tenant (design only this sprint)

- Document cache key inputs and tenant-private field prohibition for shared cache.
- No shared-cache implementation required in Sprint 1 unless already trivially present; if you add stubs, add tests only if they add clarity.

## Required outputs

1. `docs/ADR-001-architecture.md` (or equivalent name): end-to-end request flow and components.
2. `docs/TRUST-MATRIX.md`: tiers, signals, gates, examples.
3. Update `sprints/sprint-01-architecture-trust.md` if your plan changes done criteria (brief delta note at bottom).
4. Response schema examples in `docs/` (OpenAPI fragment or JSON Schema).

## Tests

- If you add **any** executable code, add the minimum tests that prove it. If you add **no** code, instead add **checklists or contract examples** in `docs/` that Sprint 2 will turn into tests.

## Safe fallback

- If a design choice is uncertain, document **VERIFY-heavy** default and list open questions—do not invent certainty.

## Improvement path

If you find a better structure, you may adopt it **only** if you document the change and update affected sprint notes.

## Stop condition

Stop when Sprint 1 **Done criteria** in `sprints/sprint-01-architecture-trust.md` are met. Do not open Sprint 2 tasks.
