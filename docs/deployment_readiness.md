# JobSignal — Deployment readiness (Sprint 4)

## 1. Pre-flight checklist

- [ ] **Runtime:** Python 3.10+ on API hosts; `python -m pytest` green in CI.
- [ ] **Dependencies:** `pip install -r requirements.txt` completes (FastAPI + uvicorn + httpx).
- [ ] **Secrets:** `.env` / secret manager holds `SEARCH_API_KEY`, `CACHE_URL`, etc.; never baked into images.
- [ ] **Config:** `EnvConfig.load(strict=True)` in production entrypoint (fail fast).
- [ ] **Cache:** Redis (or compatible) reachable; TTL matches policy (see `cache_design.md`).
- [ ] **Frontend:** static assets served with correct MIME; CSP baseline (nonce or hash later).
- [ ] **TLS:** terminate TLS at load balancer or reverse proxy.
- [ ] **Backups:** cache is disposable; document loss impact (recompute).

## 2. Health endpoints (contract)

| Route | Purpose | Expected |
|-------|---------|----------|
| `GET /health` | Liveness | `200` with `{ "status": "ok" }` always if process up |
| `GET /ready` | Readiness | `200` when critical deps satisfied; `503` if misconfigured (strict env) |

Payload shape: see `backend/core/health.py`.

## 2.1 Railway notes (current repo shape)

- Entry point: `Procfile` runs `uvicorn backend.api.main:app` with `PORT` (defaults to 8080 locally).
- Set Railway env vars at minimum: `NODE_ENV=production`, `CACHE_URL` (required by strict/staging/prod), `CACHE_DEFAULT_TTL_DAYS`, `SOURCE_PIPELINE_VERSION`, `SCORER_VERSION`.
- Optional (demo fixtures): `JOBSIGNAL_FIXTURES_PATH=data_sources/fixtures/verify_fixtures.json`
- Optional (screenshot demo): `ENABLE_IMAGE_VERIFY=1` + `FIREWORKS_API_KEY` + `FIREWORKS_VISION_MODEL`
- Optional (primary fetch demo): `ENABLE_JOB_FETCH=1` (honors `FETCH_MAX_BYTES` / `FETCH_MAX_REDIRECTS`)
- Optional (similar jobs): `RECOMMENDATIONS_ENABLED=1` plus `SERPER_API_KEY` or `JOBSIGNAL_SEARCH_FIXTURE_PATH` (and `SEARCH_PROVIDER_ORDER`)

## 3. Rollback plan

1. **Deploy:** tag image `release-<git-sha>`; keep previous tag `release-previous`.
2. **Switch:** load balancer targets previous task set / previous VM scale set instance.
3. **Cache:** if new `SCORER_VERSION`/`SOURCE_PIPELINE_VERSION` caused bad rows, **do not** roll back cache blindly—old keys remain valid TTL-wise; rollback **code** only unless incident doc says flush by fingerprint prefix.
4. **Feature flag (recommended):** `ALLOW_APPLY=false` env to force VERIFY-only mode during incidents (optional; document in runbook when implemented in route).

## 4. Monitoring (minimum)

- Error rate, latency p95, cache hit ratio.
- Alert on readiness `503` spike or 5xx ratio.

## 5. Operational runbook

Short operator steps: `deployment/RUNBOOK.md` (Sprint 4 stub) points here for deep checklist.

## 6. Related documents

- `security.md`, `reliability.md`, `final_scope.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 4 | Initial deployment readiness + rollback outline | Sprint 4 deliverable. |
