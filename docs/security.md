# JobSignal — Security (Sprint 4)

## 1. Threat model (MVP)

| Threat | Mitigation |
|---------|------------|
| Secret leakage via logs | No full job bodies at `info`; redact API keys; structured logs without env dumps. |
| SSRF via job URL | Allowlist schemes (`http`, `https` only); block private IP literals in fetch layer (Sprint 2+ wiring); redirect cap (`FETCH_MAX_REDIRECTS`). |
| Oversized / abusive payloads | `backend/core/inputs.py` enforces max URL/text sizes before work. |
| Prompt injection into optional LLM | `backend/core/prompt_guard.py` flags delimiter-style patterns; treat job text as **untrusted data**; no tool execution from model output. |
| Cross-tenant cache leakage | `strip_tenant_fields` + `assert_shared_cache_json_safe` + expanded forbidden keys; tests in `tests/test_cache_privacy.py`. |
| Rate abuse | Env-driven limits (`RATE_LIMIT_PER_MINUTE_*`); enforce at gateway (documented for deploy). |

This document is **not** a penetration-test report; it encodes **explicit assumptions** and **controls to implement** at the edge (API gateway) and in workers.

## 2. Environment variables

- **Validated** via `backend/core/env.py` (`EnvConfig.load`). In **`strict`/`production`** mode, missing critical configuration fails closed at import/startup time rather than mid-request.
- **Never** commit `.env`; `.env.example` lists names only.
- **Rotation:** bump `SOURCE_PIPELINE_VERSION` / `SCORER_VERSION` when behavior changes (see `docs/cache_design.md` §7).

## 3. URL and text input hardening

- Central gate: `validate_raw_job_inputs` in `inputs.py` (length, NUL bytes, scheme allowlist for URLs, minimum content rule).
- Normalization (`normalization.py`) runs **after** validation.

## 4. Prompt injection resistance

- Job text may contain adversarial instructions. Rules:
  - LLM (if enabled) receives text in a **data** channel, never as system instructions.
  - `assess_prompt_injection_risk` returns findings; orchestrator may attach `warnings` or force `VERIFY` when risk is `high` (policy wired in future route; **tests** lock the detector behavior now).

## 5. Cache privacy and tenant isolation

- **Shared cache payload** must only include public verification fields (`SharedCachePayload` + signals).
- Forbidden keys list includes identifiers and auth-adjacent tokens (`backend/core/cache_payload.py`).
- **Tenant id** is used for quotas/audit **outside** the cache value; never serialize into shared rows.

## 6. Logging hygiene

- Do not log `Authorization` headers, cookies, or tenant private notes.
- Truncate URLs in logs if query strings may contain tokens (prefer logging normalized fingerprint prefix only).

## 7. Related documents

- `deployment_readiness.md`, `reliability.md`, `cache_design.md`, `environment.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 4 | Initial `security.md` + code gates (`env`, `inputs`, `prompt_guard`) | Sprint 4 deliverable. |
