# IDE agent prompt — Sprint 4 only (JobSignal)

You are executing **Sprint 4**: testing expansion, **security hardening**, deployment readiness, and **final scope freeze**.

## Preconditions

Sprints 1–3 delivered features exist in repo; you extend rather than rewrite unless fixing P0 bugs (document fixes).

## Hard boundaries

- **No new product features** unless they close a security gap or are required for CI/deploy.
- **Do not** expand scope into job board, mass crawler, or blacklist product.

## Accuracy-first

- Add regression tests that prevent false confidence (e.g., APPLY without required signals).
- Fuzz or property tests optional; prefer targeted cases from trust matrix.

## Caching and multi-tenant

- Re-run and extend cache leak tests; verify rate limits per tenant/IP.

## Required outputs

1. CI pipeline running lint + tests.
2. `deployment/RUNBOOK.md` and deployment checklist updates.
3. `docs/SCOPE-FREEZE.md` with date and in/out scope bullets mirroring master plan §15.
4. Security pass notes in `security/` (even if short: SSRF, logs, secrets).

## Tests

- Mandatory: cache tenant leak test, SSRF tests for fetcher, failure path tests.
- Frontend smoke in CI if feasible.

## Safe fallback

- If deploy target is unknown, deliver docker-compose + documented local prod-like path; do not fake cloud deploy.

## Stop condition

Sprint 4 **Done criteria** in `sprints/sprint-04-hardening-deploy.md` met.
