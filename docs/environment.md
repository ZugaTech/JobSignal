# JobSignal — Environment variables (Sprint 1)

Operational and configuration variables expected at runtime. **Names are stable contracts**; values are never committed. Example placeholders live in repository root `.env.example`.

## 1. Core

| Variable | Required | Purpose |
|----------|----------|---------|
| `NODE_ENV` | Yes | `development` \| `staging` \| `production` |
| `LOG_LEVEL` | No | `debug` \| `info` \| `warn` \| `error` (default `info`) |
| `PORT` | Deploy-time | Backend port (Procfile defaults to `8080` locally) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins |
| `PROBE_PROVIDERS_ON_READY` | No | `1` enables live Fireworks/Serper checks in `/ready`; leave `0` in production to avoid quota burn |

## 2. Tenant and auth (MVP-friendly)

| Variable | Required | Purpose |
|----------|----------|---------|
This MVP does not currently ship tenant-header auth variables in code. Older planning docs mentioning `TENANT_ID_HEADER` or auth headers are not part of the live runtime contract.

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
| `SERPER_API_KEY` | When search enabled | Primary Serper.dev API key used by the live evidence coordinator |
| `SEARCH_API_KEY` | Optional | Generic fallback search key name |
| `SEARCH_API_ENDPOINT` | When search enabled | Serper endpoint; defaults to `https://google.serper.dev/search` |
| `SERPAPI_API_KEY` | Optional | Legacy fallback alias accepted by code; prefer `SERPER_API_KEY` |
| `JOBSIGNAL_SEARCH_FIXTURE_PATH` | Optional | JSON fixture for offline search results (tests/demos) |
| `RECOMMENDATIONS_ENABLED` | No | Default off; client can pass `recommendations_enabled` to override per request |
| `RECOMMENDATIONS_MAX` | No | Hard-capped at **3** in code |
| `RECOMMENDATIONS_CANDIDATE_POOL` | No | Max URLs to pull from search before verify (default 8) |
| `ENABLE_LLM_SIGNALS` | Optional | `1` enables LLM-derived *text-only* signals (`jd_specificity`, `jd_red_flags`, `jd_missing_fields`) from pasted/fetched job text. The model is instructed to return a single JSON object; the server strips optional preamble or markdown fences before parsing (see `build_llm_signals` in `backend/core/llm_fireworks.py`). |
| `FIREWORKS_API_KEY` | When LLM enabled | Fireworks API key for runtime inference |
| `FIREWORKS_BASE_URL` | No | Defaults to Fireworks OpenAI-compatible base URL |
| `FIREWORKS_MODEL` | No | Fireworks model id for chat completions (default: **Kimi K2.6** — canonical id in `backend/core/fireworks_defaults.py`) |
| `FIREWORKS_TIMEOUT_S` | No | LLM request timeout in seconds |
| `LLM_API_KEY` | Optional | Fallback key name (if not using Fireworks var names) |
| `LLM_MODEL_VERSION` | Optional | Model id for audit trail (if used elsewhere) |

## 6. Safety and limits

| Variable | Required | Purpose |
|----------|----------|---------|
| `RATE_LIMIT_PER_MINUTE_IP` | No | Default e.g. `30` |
| `RATE_LIMIT_PER_MINUTE_TENANT` | No | Default e.g. `120` |
| `ENABLE_JOB_FETCH` | No | `1` runs SSRF-bounded GET of the primary job URL (`backend/core/fetch_job_page.py`); default off for CI |
| `FETCH_MAX_BYTES` | No | Upper bound on downloaded job page |
| `FETCH_MAX_REDIRECTS` | No | Prevent redirect loops |
| `MAX_UPLOAD_BYTES` | No | Primary screenshot upload size cap |
| `IMAGE_MAX_BYTES` | No | Legacy alias still accepted by image ingest code |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | No | Current per-IP limit used by the FastAPI middleware |
| `RATE_LIMIT_BURST` | No | Current burst allowance used by the FastAPI middleware |

## 7. Observability

| Variable | Required | Purpose |
|----------|----------|---------|
The current codebase does not yet read `SENTRY_DSN`; keep it as future-facing documentation, not a required runtime value.

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
| 2026-05 | Documented jd_signals JSON-only contract | JD LLM path parses structured output locally without prose leak heuristics; reduces noisy logs when models add preamble. |
