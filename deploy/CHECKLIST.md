# JobSignal Deploy Checklist

1. Confirm Railway project is linked and environment is selected.
2. Set required env vars: `NODE_ENV`, `ALLOWED_ORIGINS`, one LLM key (`FIREWORKS_API_KEY` or `LLM_API_KEY`).
3. Required in `production`/`staging`: set `CACHE_URL` for Redis. Local development may leave it empty.
4. Optional: set Serper key (`SERPER_API_KEY`) when recommendations or live search-backed evidence are enabled.
5. Verify `Procfile` uses `PORT` (`uvicorn ... --port ${PORT:-8080}`).
6. Deploy with `railway up`.
7. Check `/health` returns `{"status":"ok"}`.
8. Check `/ready` returns `ready` or `degraded` (not `unavailable`).
9. Run one `POST /v1/verify` smoke request with URL/text input.
10. Confirm `/metrics` returns counters and watch logs for `report_returned` entries.
11. Before a live demo on stage, run `python scripts/warm_cache.py` once (with `JOBSIGNAL_API_BASE` pointing at the deployed API) so demo URLs resolve from the URL-only cache for instant repeats.

Notes:
- Frontend can be served separately as static files, or proxied by your web tier to this API.
- In degraded mode, core verify still works; optional sources are limited.
- Clipboard detection requires HTTPS (Clipboard API). Confirm Railway deployment uses HTTPS before demo; localhost and `127.0.0.1` work for dev.
- Leave `PROBE_PROVIDERS_ON_READY=0` in production unless you explicitly want `/ready` to spend provider quota on live Fireworks/Serper checks.
