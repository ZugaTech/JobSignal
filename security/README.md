# security/

This directory holds **security notes and review surfaces** for JobSignal. It does **not** store credentials, `.env` files, or customer data.

## Canonical references

| Topic | Location |
|--------|----------|
| Threat assumptions, SSRF, cache privacy, logging | [`../docs/security.md`](../docs/security.md) |
| Environment contract and validation | [`../docs/environment.md`](../docs/environment.md), [`../.env.example`](../.env.example), [`../backend/core/config.py`](../backend/core/config.py) |
| Deployment hardening checklist | [`../docs/deployment_readiness.md`](../docs/deployment_readiness.md), [`../deploy/CHECKLIST.md`](../deploy/CHECKLIST.md) |
| SSRF-safe job fetch | [`../docs/fetch_job_page.md`](../docs/fetch_job_page.md) |

## Principles (short)

1. **Secrets** live only in environment / secret managers—never in git, logs, or shared cache payloads.
2. **Inputs** (URL, pasted JD, screenshots) are untrusted; optional LLMs see content as **data**, not trusted instructions (`prompt_guard.py` is a helper, not proof).
3. **Caches** shared across tenants must omit tenant-private fields (`cache_payload.py`, tests in `tests/test_cache_privacy.py`).
4. **Readiness** endpoints expose booleans and coarse checks—never raw keys (`PROBE_PROVIDERS_ON_READY` defaults off in production-style hosts).

When extending features, update `docs/security.md` in the same change so reviewers see one coherent story.
