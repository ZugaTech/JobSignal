# JobSignal on Railway

## Live app

- **Public URL:** `https://jobsignal.up.railway.app`
- **Health:** `GET /health` → `{"status":"ok",...}`
- **Readiness:** `GET /ready` (set `PROBE_PROVIDERS_ON_READY=0` in production to avoid burning provider quota on every probe)

## How this repo deploys

- **`Dockerfile`:** multi-stage build — `npm ci` + `npm run build` → `dist/`, then Python 3.12 + `requirements-prod.txt`, `uvicorn` on `$PORT`.
- **`railway.toml`:** build from Dockerfile, health check on `/health`.
- **`Procfile`:** not used when Railway builds the Dockerfile; the image `CMD` runs uvicorn.

## Environment variables (JobSignal service)

| Variable | Notes |
|----------|--------|
| `PORT` | Set by Railway; do not override. |
| `NODE_ENV` | For **production**, set to `production` only after **Redis** is attached (see below). Until then, leaving it unset uses the app default and avoids the `CACHE_URL` requirement. |
| `CACHE_URL` | **Required** when `NODE_ENV` is `production` or `staging`. Use the Redis connection URL from a Railway **Redis** plugin (same value as `REDIS_URL` on the Redis service, or a variable reference in the dashboard). |
| `ALLOWED_ORIGINS` | e.g. `https://jobsignal.up.railway.app` or `*` for demos. |
| `SERPER_API_KEY` | Primary Serper.dev key for search-backed evidence and recommendations. If unset, `/ready` reports `checks.serp_key` **fail** and the API is **degraded** (unless `SERPAPI_API_KEY` alone is set). |
| `SERPAPI_API_KEY` | Optional **SerpApi** key. Used when Serper returns errors or when only SerpApi is configured. Coexists with Serper; Serper is tried first when both are set. |
| `SERPAPI_SEARCH_ENDPOINT` | SerpApi JSON endpoint (default `https://serpapi.com/search.json`). |
| `SEARCH_API_KEY` | Alias for **Serper** only (same as `SERPER_API_KEY`); not sent to SerpApi. |
| `FIREWORKS_API_KEY` / `LLM_API_KEY` | Enable LLM features when configured. |
| `PROBE_PROVIDERS_ON_READY` | Keep `0` in production unless you intentionally want live Fireworks/Serper checks on `/ready`. |
| `FETCH_MAX_BYTES` | Cap on raw HTML bytes read from the posting URL. |
| `FETCH_BODY_TEXT_MAX_CHARS` | Max characters of cleaned **main-body** text merged into fetch extraction (default `16000`). |
| `SEARCH_MAX_CALLS_EVIDENCE` | Serper POST budget for careers / boards / registry / duplicate queries. Pipeline issues **6** parallel searches — set **≥ 8** (default in repo `8`). |
| `SEARCH_MAX_CALLS_REPUTATION` | Serper budget for employer reputation. Code runs **6** parallel plain queries — set **≥ 6** (default `8`). Lower values silently skip searches and show “0 sources”. |
| `SEARCH_MAX_CALLS_RECOMMENDATIONS` | Serper budget when **similar jobs** are requested (default `8`). |
| `SCORER_VERSION` | Bump when scoring rules change (invalidates client expectations / docs only; cache keys use `SOURCE_PIPELINE_VERSION` too). |

See **`.env.example`** for the full contract (`backend/core/config.py` → `ENV_SPECS`).

## Add Redis (production)

1. In the Railway project, **New** → **Database** → **Redis**.
2. On the **JobSignal** web service, add **`CACHE_URL`** and paste the Redis URL (from the Redis service’s variables, often `REDIS_URL` / `REDIS_PRIVATE_URL`).
3. Set **`NODE_ENV=production`** on the JobSignal service.
4. Redeploy if needed.

Until **`CACHE_URL`** is set, `/ready` reports **`checks.redis`: `skip`** (in-memory cache per instance). That matches **`NODE_ENV=development`** and is fine for demos; for **consistent cache across replicas**, Redis is required.

### Clearing in-memory cache without Redis

Each deploy starts with an empty process-local cache. To **wipe stale hits** when you are not using Redis, trigger a redeploy (for example add a dummy variable **`CACHE_BUST`** with a timestamp value such as `20250511_001`, save so Railway redeploys, verify behaviour, then **delete** `CACHE_BUST`). Alternatively call **`POST /v1/verify`** with **`force_refresh: true`** for the same inputs.

Readiness always includes **`checks.serp_key`** and **`checks.llm_key`** (`pass` / `fail`) based on whether API keys are configured—no live probe required when `PROBE_PROVIDERS_ON_READY=0`.

Copy the Redis URL into your **private** local [`.env`](.env) as **`CACHE_URL=`** before running [`scripts/push_env_to_railway.py`](../scripts/push_env_to_railway.py) without **`--no-delete`**, so the next sync does not clear Redis on Railway.

## Sync local `.env` to Railway (secrets stay off git)

After `railway login` and linking this directory to the service:

```bash
python scripts/push_env_to_railway.py
python scripts/push_env_to_railway.py --deploy   # optional: one `service redeploy` after bulk apply
```

**Warning:** keys that are **empty** in your local `.env` trigger `railway variable delete` for that name (Railway cannot set empty values). That can remove **`CACHE_URL`** or other secrets that exist only on Railway. Use:

```bash
python scripts/push_env_to_railway.py --no-delete
```

…when you want to **update** variables from `.env` but **preserve** remote-only values for keys left blank locally. The script always clears **`JOBSIGNAL_SEARCH_FIXTURE_PATH`** on the service (fixtures must not run in the cloud).

Before production parity, put **`CACHE_URL`** (and matching **`NODE_ENV`**) in [`.env`](.env) **before** running the push script without `--no-delete`, so Redis is not wiped accidentally.

## Parity checklist (local vs deployed)

See **[deploy/RAILWAY_PARITY.md](RAILWAY_PARITY.md)** for `/ready` comparison, verify POST examples, and why job-board fetch may differ from localhost (datacenter egress).

## CLI quick reference

```bash
railway login
railway link -p JobSignal -s <service>   # or railway service link <id>
railway up                                # deploy current directory
railway domain                            # show / assign public URL
railway variables                         # list vars
railway logs                              # runtime logs
```

If `railway add -d redis` returns **Unauthorized**, run **`railway login`** again or add Redis from the Railway dashboard.

## Frontend API base

The React bundle is served from the **same origin** as the API. Leave **`VITE_API_BASE`** empty at build time so the browser calls `/v1/verify` on the Railway host.
