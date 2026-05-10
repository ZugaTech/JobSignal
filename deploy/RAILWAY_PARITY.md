# Railway vs localhost parity

Use this when deployed behavior differs from local dev: verify **environment**, **cache**, and **outbound fetch** before chasing application bugs.

## 1. Readiness comparison (`/ready`)

Same JSON shape from [`backend/core/health.py`](../backend/core/health.py). Compare:

| Field | Meaning |
|-------|--------|
| `status` | `ready` (ok) / `degraded` (missing provider key or failed live probe) / implied 503 = `unavailable` (e.g. Redis down when `CACHE_URL` set) |
| `checks.redis` | `skip` if no `CACHE_URL`; `pass`/`fail` if Redis configured |
| `checks.llm_key` | Fireworks/LLM key present (`pass` without live probe; live result if `PROBE_PROVIDERS_ON_READY=1`) |
| `checks.serp_key` | Serper (or accepted fallback search key) configured — **`fail`** means verify/evidence will degrade |
| `checks.serp_key_for_recommendations` | Only strict when recommendations default on |
| `features.*` | Feature flags from env (`job_fetch_enabled`, `llm_signals_enabled`, etc.) |
| `live_probe` | Matches `PROBE_PROVIDERS_ON_READY` |

**Examples (run from your machine):**

```bash
curl -sS "http://127.0.0.1:8080/ready" | python -m json.tool
curl -sS "https://jobsignal.up.railway.app/ready" | python -m json.tool
```

## 2. Sanitized variable checklist (names only; no secrets in git)

Align **names** and **non-secret values** with [`.env.example`](../.env.example) and [`backend/core/config.py`](../backend/core/config.py) `ENV_SPECS`. Pay special attention to:

- `NODE_ENV` — `production` requires `CACHE_URL` (see [config validate](../backend/core/config.py)).
- `CACHE_URL` — often set only on Railway; **empty local `.env` + `push_env_to_railway.py` without `--no-delete` can delete it** on the service.
- `SOURCE_PIPELINE_VERSION`, `SCORER_VERSION` — affect cache keys ([`cache_key`](../backend/core/cache_key.py)).
- `ENABLE_JOB_FETCH`, `ENABLE_LLM_SIGNALS`, `ENABLE_IMAGE_VERIFY`, `RECOMMENDATIONS_ENABLED`
- `SERPER_API_KEY`, `FIREWORKS_API_KEY` (or `LLM_API_KEY`)

List remote names: `railway variables` (do not paste values into issues).

## 3. Same-input verify call (API parity)

Use the **same JSON** against local and production; compare `recommendation`, `confidence_score`, and evidence (not only headline copy).

```bash
# Minimal example (tune body to your case)
curl -sS -X POST "https://jobsignal.up.railway.app/v1/verify" \
  -H "Content-Type: application/json" \
  -d "{\"job_url\":\"https://example.com/jobs/1\",\"job_description\":null}" | python -m json.tool
```

Repeat with `http://127.0.0.1:8080` when the local server is running.

Sanity check after deploy: `meta.pipeline_version` / `meta.scorer_version` should match your **`SOURCE_PIPELINE_VERSION`** / **`SCORER_VERSION`** env vars; `cache.hit` may differ until inputs repeat after cold start.

**Why results can still differ when env matches:**

1. **No Redis on Railway** — each replica uses in-memory cache; load balancers see different cache state. Fix: attach Redis, set `CACHE_URL`, then `NODE_ENV=production` as in [RAILWAY.md](RAILWAY.md).
2. **Job page fetch** — requests originate from **datacenter IPs** on Railway; some boards (e.g. Indeed) may return **403** or empty HTML where your home IP succeeds. The pipeline should downgrade honestly (VERIFY / lower confidence); fixing that fully would require a different egress path, not a small config tweak.
3. **LLM** — low temperature but not bitwise-identical across runs.

## 4. Push script safety

See [RAILWAY.md](RAILWAY.md) — use `python scripts/push_env_to_railway.py --no-delete` when local `.env` omits secrets that exist only on Railway (e.g. `CACHE_URL`). The script still clears `JOBSIGNAL_SEARCH_FIXTURE_PATH` on the remote so fixtures never run in the cloud.

## 5. Audit snapshot (template)

Fill when debugging (do not commit secrets):

| Check | Local | Railway |
|-------|-------|---------|
| Date | | |
| `/ready` status | | |
| `checks.redis` | | |
| `features.job_fetch_enabled` | | |
| `NODE_ENV` (name only) | | |
| `CACHE_URL` set? (yes/no) | | |
| `SOURCE_PIPELINE_VERSION` / `SCORER_VERSION` | | |
