# JobSignal — Folder structure and dependencies (Sprint 1)

## 1. Repository tree (authoritative for Sprint 1)

```text
JobSignal/
  .cursor/                 # Editor/agent rules (optional in remote; team choice)
  .env.example             # Placeholder env names only
  README.md
  backend/                 # Future API, orchestrator, collectors, scorer
  cache/                   # Docs/scripts for key derivation, TTL (code later)
  data_sources/            # Search/fetch contract notes and templates
  deployment/              # Runbooks, env matrices, health check notes
  docs/                    # Product and architecture (canonical)
    architecture.md
    trust_model.md
    scope.md
    environment.md
    folder_structure.md    # (this file)
    sprints/
      sprint-1.md
    JOBSIGNAL-MASTER-PLAN.md
    ADR-001-architecture.md
    TRUST-MATRIX.md
  frontend/                # Future UI (Sprint 3+)
  prompts/                 # Paste-ready per-sprint agent prompts
  security/                # Threat notes, SSRF/rate-limit policies
  sprints/                 # Sprint overview files (mirrors prompts scope)
  tests/                   # Unit, integration, e2e (Sprint 2+)
```

## 2. What belongs where (short)

| Path | Belongs |
|------|---------|
| `docs/` | All human-readable specifications; ADRs; sprint notes under `docs/sprints/`. |
| `backend/` | Server entry, routes, domain modules when implementation begins. |
| `frontend/` | SPA or static UI when implementation begins. |
| `tests/` | Mirrors production packages; fixtures with **mocked** HTTP/search. |
| `cache/` | Key helpers and TTL policy code co-located with docs until split. |
| `data_sources/` | Provider-specific query templates **without** secrets. |
| `deployment/` | Infra-as-code or compose files when added. |
| `security/` | Checklists, not secrets. |
| `prompts/` | Agent prompts; keep aligned with `docs/sprints/`. |

## 3. Minimal dependencies (Sprint 1 lock-in)

**No language runtime is mandated in Sprint 1.** The following is the **minimal dependency set** once implementation starts (expected smallest viable stack—adjust in ADR when chosen):

| Dependency | Role | When added |
|------------|------|------------|
| Runtime (Node **or** Python **or** other) | Execute API | Sprint 2 |
| HTTP framework for REST | `/v1/verify`, `/health` | Sprint 2 |
| JSON Schema or Zod/Pydantic equivalent | Request/response validation | Sprint 2 |
| HTTP client | Bounded job page fetch | Sprint 2 |
| Search SDK or raw HTTPS client | Search adapter | Sprint 2 |
| Redis client (or platform SDK) | TTL cache | Sprint 2 |
| Test framework + assertion lib | CI | Sprint 2 |
| Lint + formatter | Dev quality | Sprint 2 |

**Sprint 1 repo state:** documentation only; **no** `package.json` / `pyproject.toml` yet—adds noise until runtime choice is recorded. First dependency manifest commit should accompany ADR “Runtime choice” in Sprint 2.

## 4. Multi-tenant and cache files (future)

- Shared cache serialization lives under `backend/` or `cache/` once code exists; tests in `tests/cache/` prove tenant fields never serialize.

## Related documents

- `architecture.md`, `environment.md`, `scope.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Added `docs/folder_structure.md` | Required sprint artifact; defers lockfiles to Sprint 2. |
