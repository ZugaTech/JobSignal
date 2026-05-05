# JobSignal — Operator runbook (Sprint 4 stub)

## Incident: elevated 5xx or readiness failures

1. Check `/ready` returns `200` and `checks.cache_ping` is `ok` (when ping wired).
2. If deploy-related: roll back to previous image tag per `docs/deployment_readiness.md` §3.
3. If cache poisoned (hypothetical): flush keys matching fingerprint prefix only after security review.

## Incident: suspected cache leakage

1. Stop writes: set maintenance mode (load balancer) if available.
2. Inspect recent shared payloads for forbidden keys (`tenant_id`, `password`, …) using audit tooling.
3. Patch serializer (`cache_payload.py`) if new forbidden key class found; bump `SOURCE_PIPELINE_VERSION`.

## Incident: false APPLY reports

1. Set emergency **VERIFY-only** mode at gateway (recommended flag from `deployment_readiness.md` when implemented).
2. Bump `SCORER_VERSION` to invalidate cached verdicts if verdicts were cached (future storage decision).

## Contacts / links

- Deep checklist: `docs/deployment_readiness.md`
- Security assumptions: `docs/security.md`
