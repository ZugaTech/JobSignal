# Sprint 4 — Testing, hardening, deployment readiness, and final freeze

## Sprint goal

Make the system **safe to demo** and **ready for controlled deploy**: tests, security pass, ops checklist, **frozen scope** sign-off.

## Scope

- Full regression suite wired in CI.
- Security review items from master plan §12 (SSRF, logs, rate limits, cache leak test).
- Deployment doc: env matrix, health checks, rollback.
- **Scope freeze** document with explicit out-of-scope list.

## Tasks

1. CI: lint, unit, integration, cache leak test required.
2. Rate limit and abuse scenarios documented + tested where feasible.
3. `deployment/RUNBOOK.md`: incident steps, key rotation, disable APPLY flag if needed.
4. Final README links and version tag policy.

## Done criteria

- CI green on main; no known P0 security gaps open.
- Runbook + deployment checklist completed.
- Stakeholders sign frozen scope (even if “team of one” — dated note in `docs/`).

## Risk

Last-minute feature creep → **Mitigation:** defer to extension list only with ADR.

## Fallback

If deploy target unknown: deliver “release candidate” bundle + docker-compose for local prod-like demo.

## Manual checklist

- [ ] Secret scan on repo
- [ ] Dependency audit (package manager)
- [ ] Backup/restore note for cache store
- [ ] Dry-run deploy to staging
