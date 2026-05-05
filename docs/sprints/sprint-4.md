# Sprint 4 — Notes and completion record

**Status:** tests expanded, hardening utilities added, deployment/security/reliability/final-scope documentation completed. **No** major product features, redesign, crawler, or blacklist scope.

**Date:** 2026-05-04.

## Deliverables

| Item | Location |
|------|----------|
| Security posture + controls | `docs/security.md` |
| Reliability + health contracts | `docs/reliability.md` |
| Deployment readiness + rollback | `docs/deployment_readiness.md`, `deployment/RUNBOOK.md` |
| Final scope freeze | `docs/final_scope.md` |
| Env validation (strict / staging / prod) | `backend/core/env.py` + `tests/test_env.py` |
| Input validation (URL/text) | `backend/core/inputs.py` + `tests/test_inputs.py` |
| Prompt injection heuristics | `backend/core/prompt_guard.py` + `tests/test_prompt_guard.py` |
| Health/readiness payloads | `backend/core/health.py` + `tests/test_health.py` |
| Cache privacy expansion | `backend/core/cache_payload.py` + `tests/test_cache_privacy.py` |
| Frontend client-side validation + clearer errors | `frontend/app.js`, `frontend/index.html` + smoke test |

## Verification performed

- **Tests:** `python -m pytest` (full suite) — see CI expectation in `docs/reliability.md`.
- **Cache TTL / invalidation documentation:** cross-checked `docs/cache_design.md` §3 and §7 against `EnvConfig` TTL clamp (10–30 days).
- **Shared cache tenant leakage:** automated tests for nested `tenant_id` stripping and forbidden `password` key rejection before serialize.
- **Frontend error handling:** invalid URL / empty inputs / oversize paths show **error** phase without calling mock verify.
- **Backend health:** `build_health_payload` / `build_ready_payload` contracts documented and unit-tested (readiness fails closed when staging lacks cache URL or ping fails).

## Documented safeguards added in Sprint 4

| Safeguard | Why |
|-----------|-----|
| `EnvConfig.load(strict=True)` | Fail fast in real deploys without `CACHE_URL`. |
| `validate_raw_job_inputs` | Reject NUL bytes, oversize payloads, disallowed URL schemes before work. |
| `assess_prompt_injection_risk` | Surface adversarial instruction patterns for orchestrator policy (tests lock detector). |
| Expanded `_TENANT_FORBIDDEN` | Reduce accidental serialization of auth-adjacent fields. |

## Remaining risks (explicit)

| Risk | Mitigation status |
|------|-------------------|
| No real HTTP fetch/search adapters in-repo | Documented deferral; production must wire SSRF-safe fetch + signed outbound calls. |
| Prompt guard is heuristic only | Does not replace sandboxed LLM deployment; orchestrator must keep system prompts immutable. |
| Health `cache_ping` optional | Operators must wire actual Redis ping in readiness path for production. |
| PSL-naive domain normalization | Documented in `normalization.py`; may mis-parse some ccTLDs—accept or add PSL library later. |
| Static UI demo uses mock verify | Replace with API integration; add CSP and auth before public deploy. |

## Out of scope (honored)

- Crawler platform, job board, blacklist UX.
- Full cloud IaC, blue/green automation beyond rollback notes.

## Commands

```bash
python -m pytest
```
