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
| `SERPER_API_KEY` | Primary Serper.dev key for search-backed evidence and recommendations. |
| `SEARCH_API_KEY` / `SERPAPI_API_KEY` | Legacy fallback aliases accepted by code; prefer `SERPER_API_KEY` for Railway. |
| `FIREWORKS_API_KEY` / `LLM_API_KEY` | Enable LLM features when configured. |
| `PROBE_PROVIDERS_ON_READY` | Keep `0` in production unless you intentionally want live Fireworks/Serper checks on `/ready`. |

See **`.env.example`** for the full contract (`backend/core/config.py` → `ENV_SPECS`).

## Add Redis (production)

1. In the Railway project, **New** → **Database** → **Redis**.
2. On the **JobSignal** web service, add **`CACHE_URL`** and paste the Redis URL (from the Redis service’s variables, often `REDIS_URL` / `REDIS_PRIVATE_URL`).
3. Set **`NODE_ENV=production`** on the JobSignal service.
4. Redeploy if needed.

Until **`CACHE_URL`** is set, `/ready` reports **`checks.redis`: `skip`** (in-memory cache per instance). That matches **`NODE_ENV=development`** and is fine for demos; for **consistent cache across replicas**, Redis is required.

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
