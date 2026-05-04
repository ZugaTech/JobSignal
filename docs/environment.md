# JobSignal — Environment variables (Sprint 1)

Operational and configuration variables expected at runtime. **Names are stable contracts**; values are never committed. Example placeholders live in repository root `.env.example`.

## 1. Core

| Variable | Required | Purpose |
|----------|----------|---------|
| `NODE_ENV` | Yes | `development` \| `staging` \| `production` |
| `APP_PUBLIC_BASE_URL` | Staging+ | Public URL of web UI (CORS, links) |
| `API_PUBLIC_BASE_URL` | Staging+ | Public URL of API |
| `LOG_LEVEL` | No | `debug` \| `info` \| `warn` \| `error` (default `info`) |

## 2. Tenant and auth (MVP-friendly)

| Variable | Required | Purpose |
|----------|----------|---------|
| `TENANT_ID_HEADER` | No | Header name carrying tenant id for demos (e.g. `x-tenant-id`) |
| `API_KEYS` or `JWT_ISSUER` | TBD at impl | Exact auth mechanism chosen in Sprint 2—document here when fixed |

## 3. Versioning (cache and reproducibility)

| Variable | Required | Purpose |
|----------|----------|---------|
| `SOURCE_PIPELINE_VERSION` | Yes | Bump when normalization or collectors change; invalidates cache keys |
| `SCORER_VERSION` | Yes | Bump when rule thresholds change |

## 4. Cache

| Variable | Required | Purpose |
|----------|----------|---------|
| `CACHE_URL` | Staging+ | Connection string for Redis-compatible cache |
| `CACHE_DEFAULT_TTL_DAYS` | No | Default **14**; keep within 10–30 day policy window |

## 5. External providers (names only; wire in Sprint 2)

| Variable | Required | Purpose |
|----------|----------|---------|
| `SEARCH_API_KEY` | When search enabled | API key for hosted search |
| `SEARCH_API_ENDPOINT` | When search enabled | Base URL for search provider |
| `LLM_API_KEY` | Optional | If LLM extraction enabled |
| `LLM_MODEL_VERSION` | Optional | Model id for cache/scorer audit trail |

## 6. Safety and limits

| Variable | Required | Purpose |
|----------|----------|---------|
| `RATE_LIMIT_PER_MINUTE_IP` | No | Default e.g. `30` |
| `RATE_LIMIT_PER_MINUTE_TENANT` | No | Default e.g. `120` |
| `FETCH_MAX_BYTES` | No | Upper bound on downloaded job page |
| `FETCH_MAX_REDIRECTS` | No | Prevent redirect loops |

## 7. Observability

| Variable | Required | Purpose |
|----------|----------|---------|
| `SENTRY_DSN` | No | Error reporting |

## 8. Validation rules

- On startup in staging/production, **fail fast** if required vars missing.
- Never log secrets or full job description bodies at info level.

## Related documents

- `architecture.md` — where these values influence behavior
- Root `.env.example`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Added `docs/environment.md` | Single reference for deployers and agents. |
| Sprint 1 | Added `SCORER_VERSION` distinct from pipeline | Clearer cache invalidation when only rules change. |
