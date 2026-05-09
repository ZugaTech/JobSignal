# JobSignal Deploy Checklist

1. Confirm Railway project is linked and environment is selected.
2. Set required env vars: `NODE_ENV`, `ALLOWED_ORIGINS`, one LLM key (`FIREWORKS_API_KEY` or `LLM_API_KEY`).
3. Required in `production`/`staging`: set `CACHE_URL` for Redis. Local development may leave it empty.
4. Optional: set SERP key (`SERPAPI_API_KEY` or `SEARCH_API_KEY`) when recommendations are enabled.
5. Verify `Procfile` uses `PORT` (`uvicorn ... --port ${PORT:-8080}`).
6. Deploy with `railway up`.
7. Check `/health` returns `{"status":"ok"}`.
8. Check `/ready` returns `ready` or `degraded` (not `unavailable`).
9. Run one `POST /v1/verify` smoke request with URL/text input.
10. Confirm `/metrics` returns counters and watch logs for `report_returned` entries.

Notes:
- Frontend can be served separately as static files, or proxied by your web tier to this API.
- In degraded mode, core verify still works; optional sources are limited.
- Clipboard auto-detect needs HTTPS in production (Clipboard API); localhost works for dev.
- Leave `PROBE_PROVIDERS_ON_READY=0` in production unless you explicitly want `/ready` to spend provider quota on live Fireworks/Serper checks.
