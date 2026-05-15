# JobSignal — Folder structure

Canonical architecture detail remains in [`architecture.md`](architecture.md). This file describes **where code and docs live today**.

## 1. Repository tree (high level)

```text
JobSignal/
  .cursor/              # Editor/agent rules (team choice whether to track)
  .github/workflows/    # CI (frontend build + pytest)
  backend/
    api/                # FastAPI app factory and routes
    core/               # Orchestration, scoring, cache, providers, inputs
  src/                  # React + TypeScript + Vite (primary UI)
  frontend/             # Optional legacy static UI (only if present; else build dist/)
  extension/            # Chrome extension (unpacked load)
  tests/                # Pytest suite (contract, integration, unit)
  docs/                 # Product and engineering specifications
  prompts/              # Paste-ready agent prompts (historical / process)
  sprints/              # Sprint overview documents
  deploy/               # Railway / PaaS checklists and notes
  deployment/           # Runbooks and operator docs
  security/             # Pointers + security README (no secrets)
  data_sources/         # Fixtures and query templates (no API keys)
  cache/                # Cache design notes
  dist/                 # Vite production build output (generated; gitignored)
  .env.example          # Safe placeholder env names only
  README.md
  package.json          # Frontend toolchain
  pyproject.toml        # Python project + pytest config
  requirements.txt      # Runtime + test dependencies
```

## 2. What belongs where

| Path | Purpose |
|------|---------|
| `docs/` | Human-readable specs, ADRs, sprint records under `docs/sprints/`. |
| `backend/` | Python service: API, orchestration, scoring, integrations. |
| `src/` | Primary user interface (React). |
| `frontend/` | Optional legacy static UI; used only when `dist/` is absent **and** this directory exists. |
| `tests/` | Pytest; HTTP and providers should be mocked or fixtured in CI. |
| `data_sources/` | Fixtures and templates—**never** committed secrets. |
| `deploy/` / `deployment/` | How to ship and operate the service. |
| `security/` | Security README and supplemental notes—not a secret store. |

## 3. Runtimes and manifests

| Stack | Manifest | Role |
|-------|-----------|------|
| Python 3.10+ | `requirements.txt`, `pyproject.toml` | API and core library |
| Node 20+ (see CI) | `package.json`, `package-lock.json` | Vite build and dev server |

## Related documents

- [`architecture.md`](architecture.md), [`environment.md`](environment.md), [`scope.md`](scope.md)

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Initial tree (docs-only phase) | Sprint deliverable |
| 2026-05-12 | Updated for React `src/`, CI, backend layout, extension | Repo drift repair |
