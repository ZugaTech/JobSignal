# deployment/

Operator-facing material for running JobSignal beyond local development.

| Document | Purpose |
|----------|---------|
| [`RUNBOOK.md`](RUNBOOK.md) | Incidents, readiness semantics, rollback pointers |
| [`../deploy/CHECKLIST.md`](../deploy/CHECKLIST.md) | Short deploy checklist |
| [`../deploy/RAILWAY.md`](../deploy/RAILWAY.md) | Railway-oriented env and parity notes |
| [`../docs/deployment_readiness.md`](../docs/deployment_readiness.md) | Full pre-flight and monitoring expectations |

## Serving the UI

Production path: **`npm run build`** produces `dist/`; FastAPI serves that directory when present. If `dist/` is missing **and** a `frontend/` directory exists, that legacy folder is mounted instead (see `backend/api/main.py`). API routes work without either directory.

Separate-origin setups can host static files behind a CDN or reverse proxy and set `VITE_API_BASE` / `ALLOWED_ORIGINS` appropriately—see `.env.example`.
