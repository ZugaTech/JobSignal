# JobSignal

**JobSignal** helps job applicants sanity-check postings before they spend time applying. It combines normalized inputs, bounded web search and optional primary-page fetch, structured evidence (T1–T3 trust tiers), and conservative **APPLY / VERIFY / SKIP** outcomes—surfacing uncertainty instead of fake confidence.

The product is **decision support**, not a job board, blocklist, or guarantee of employer intent.

## Highlights

- **FastAPI** API: `POST /v1/verify` (JSON or multipart with optional screenshot), plus `GET /health` and `GET /ready`
- **Accuracy-first scoring** with explicit gates, honesty guards, and user-visible reasons
- **Global cache** keyed on normalized fingerprints (with TTL); shared entries never store tenant-private fields
- **Optional** similar-job recommendations (each candidate re-run through the same pipeline, capped)
- **React + Vite** UI in `src/` (production build emitted to `dist/`, served by the API). If `dist/` is missing, the server optionally serves a legacy **`frontend/`** directory when that folder exists (this clone may omit it).
- **Chrome extension** under `extension/` for in-page verification (default API: `http://localhost:8080`)
- **CI** (GitHub Actions): `npm ci` + `npm run build`, Python 3.10, `pytest`

## Quick start

**Requirements:** Python 3.10+, Node 20+ (matches CI).

```bash
cp .env.example .env
# Add provider keys in .env only on your machine — never commit .env.

pip install -r requirements.txt
npm ci
npm run build

set PYTHONPATH=.   # PowerShell: $env:PYTHONPATH="."
pytest
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` for the bundled UI. For Vite hot reload during UI work: `npm run dev` (see `.env.example` for `VITE_API_BASE` when the API is on another origin).

### Chrome extension

1. Open `chrome://extensions/` → enable **Developer mode**
2. **Load unpacked** → select the `extension/` folder in this repository
3. Pin the extension; use the gear icon if you need to change the API base URL (default `http://localhost:8080`)

## Configuration

Authoritative variable **names** live in `.env.example` and `backend/core/config.py`. Use a secret manager or platform env vars in production; rotate keys independently of code deploys.

## Documentation

| Area | Document |
|------|----------|
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| Trust tiers & signals | [`docs/trust_model.md`](docs/trust_model.md), [`docs/TRUST-MATRIX.md`](docs/TRUST-MATRIX.md) |
| Scoring & verdicts | [`docs/scoring.md`](docs/scoring.md), [`docs/decision_logic.md`](docs/decision_logic.md) |
| Cache & privacy | [`docs/cache_design.md`](docs/cache_design.md) |
| Security | [`docs/security.md`](docs/security.md), [`security/README.md`](security/README.md) |
| Deployment | [`docs/deployment_readiness.md`](docs/deployment_readiness.md), [`deploy/RAILWAY.md`](deploy/RAILWAY.md), [`deployment/RUNBOOK.md`](deployment/RUNBOOK.md) |
| Operational status board | [`docs/TECHNICAL-LEDGER.md`](docs/TECHNICAL-LEDGER.md) |
| Change journal | [`docs/PROGRESS-LOG.md`](docs/PROGRESS-LOG.md) |
| Frozen scope | [`docs/final_scope.md`](docs/final_scope.md) |

Planning baseline and sprint history: [`docs/JOBSIGNAL-MASTER-PLAN.md`](docs/JOBSIGNAL-MASTER-PLAN.md), [`docs/sprints/`](docs/sprints/), [`sprints/`](sprints/).

## Agent / editor rules

Cursor rules for this repo: [`.cursor/rules/JOBSIGNAL-EXECUTION.mdc`](.cursor/rules/JOBSIGNAL-EXECUTION.mdc) (shipping, env contract, hygiene).

## Repository layout

See [`docs/folder_structure.md`](docs/folder_structure.md) for the full tree and conventions.
