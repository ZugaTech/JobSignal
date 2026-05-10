# JobSignal - Operator runbook

## Readiness semantics

- `status=ready`: all required runtime checks pass.
- `status=degraded`: core verification works, but optional sources are limited.
- `status=unavailable`: deployment should not receive traffic.
- Redis check is `skip` when `CACHE_URL` is unset.
- Recommendations Serper check is `skip` when `RECOMMENDATIONS_ENABLED=0`.

## Incident: elevated 5xx or readiness failures

1. Check `/health`, `/ready`, and `/metrics`.
2. If `/ready` is `unavailable`, inspect `CACHE_URL` and Redis connectivity.
3. If `/ready` is `degraded`, verify `FIREWORKS_API_KEY` or `LLM_API_KEY`, and `SERPER_API_KEY` when recommendations or live search-backed evidence are enabled.
4. Roll back to prior Railway deployment if incident persists.

## Incident: suspected cache leakage

1. Stop writes via maintenance mode or gateway block.
2. Inspect payload sanitizer in `backend/core/cache_payload.py`.
3. Rotate Redis credentials if exposure is suspected.

## Incident: false APPLY reports

1. Set temporary policy to force `VERIFY`.
2. Bump `SCORER_VERSION` to invalidate impacted cache entries.
3. Re-run smoke checks with known fixtures before reopening.
