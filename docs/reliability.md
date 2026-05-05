# JobSignal — Reliability (Sprint 4)

## 1. Testing strategy

| Layer | What runs | Location |
|-------|-----------|----------|
| Unit | Normalization, cache keys/TTL, tenant strip, scoring gates, env parsing, input validation, prompt guard | `tests/test_*.py` |
| Contract | JSON-safe cache serialization | `tests/test_cache_store.py`, `tests/test_cache_privacy.py` |
| Static UI smoke | Required UI phases + uncertainty copy | `tests/test_frontend_smoke.py` |

**Command:** `python -m pytest` (see `pyproject.toml`).

## 2. Failure handling philosophy

- **External APIs:** bounded retries with jitter belong in the orchestrator (documented; not all adapters implemented in-repo yet).
- **Partial evidence:** never fabricate missing tiers; scorer defaults to **VERIFY** (Sprint 3).
- **Cache store down:** return fresh evaluation when possible; surface `warnings` if degraded.

## 3. Health checks

- `backend/core/health.py` exposes `build_health_payload` for **`/health`** (liveness) and **`/ready`** (readiness) contracts.
- Readiness may include optional dependency pings (cache URL present, search endpoint configured) — **boolean flags only**, no secrets in response body.

## 4. Observability (minimal production)

- Request id per call (header `x-request-id` when present).
- Count metrics: cache hit/miss, scorer outcomes (future exporter).

## 5. Cache TTL and invalidation (verification)

Documented in **`docs/cache_design.md`** §3 (TTL window 10–30 days, default 14) and §7 (invalidation via version bumps + operational delete). Sprint 4 **verified** no contradictions with `env.py` clamping of `CACHE_DEFAULT_TTL_DAYS`.

## 6. Related documents

- `security.md`, `deployment_readiness.md`, `data_flow.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 4 | Initial `reliability.md` + health helper tests | Sprint 4 deliverable. |
