# Production parity audit — checklist + risk matrix

Use this after every deploy or when “it worked locally but Railway feels wrong.” Pair with [deploy/RAILWAY_PARITY.md](../deploy/RAILWAY_PARITY.md) and [deploy/RAILWAY.md](../deploy/RAILWAY.md). **Do not paste secrets** into tickets; use yes/no and variable *names* only.

---

## Known-safe vs known-risk (one-page matrix)

| Area | Known-safe when… | Known-risk when… | Fast signal |
|------|------------------|------------------|---------------|
| **Liveness** | `GET /health` returns 200 | You treat `/health` as “fully configured” | `/health` never proves keys, Redis, or fetch |
| **Readiness** | `GET /ready` is `ready`, `live_probe: false` in prod | `degraded` / `unavailable` but `/health` still 200 | Compare JSON: `checks.*`, `features.*` |
| **Shared cache** | `CACHE_URL` set + Redis reachable; multi-instance stable | `NODE_ENV=development` + multiple replicas + no Redis | `features.shared_cache_required` + `checks.redis` |
| **URL intake** | Same normalized URL + same pipeline versions | Different `SOURCE_PIPELINE_VERSION` / `SCORER_VERSION` between hosts | `meta.pipeline_version`, `meta.scorer_version` |
| **Job fetch** | `ENABLE_JOB_FETCH=1` and boards allow datacenter egress | 403/empty HTML from job boards on Railway IPs | `signals` include fetch warnings; VERIFY + lower confidence |
| **Search / evidence** | Serper key present; budgets ≥ pipeline needs | Missing `SERPER_API_KEY` (and no acceptable fallback) | `/ready` → `checks.serp_key: fail` |
| **Reputation** | Curated highlights drive `plain_summary`; no meta echo | Social SERP noise or instruction-like LLM text | Company trust panel reads calm; no “I need to…” |
| **Main summary** | Two short sentences; no raw `snake_case` signal IDs | Model echoes internal prompt lines | Summary has no `fetch_ok`, `Signals:`, `Decision:` |
| **LLM probes on health** | `PROBE_PROVIDERS_ON_READY=0` in prod | `1` in prod burns quota on every `/ready` | `/ready` → `live_probe` matches env |
| **Env sync** | `push_env_to_railway.py --no-delete` when local omits secrets | Blank local `CACHE_URL` deletes remote without `--no-delete` | Sudden Redis `fail` after env push |

---

## Operator checklist (15 minutes)

### A. Baseline endpoints

1. `GET /health` — expect **200**, minimal payload (liveness only).
2. `GET /ready` — expect **`status: "ready"`** for a healthy prod demo; note `checks.redis`, `checks.serp_key`, `checks.llm_key`, `features.*`, `live_probe`.

### B. Environment parity (names only)

3. Confirm on Railway (dashboard or CLI): `CACHE_URL` **set**, `JOBSIGNAL_REQUIRE_SHARED_CACHE` aligned with replica count, `SERPER_API_KEY` **set**, `ENABLE_JOB_FETCH` matches what you expect for prod demos.
4. Confirm `SOURCE_PIPELINE_VERSION` and `SCORER_VERSION` match what you believe is deployed (cache keys include these — drift causes “different body, same URL”).
5. Confirm `PROBE_PROVIDERS_ON_READY` is **0** unless you intentionally want live probes on `/ready`.

### C. Functional smoke (same JSON everywhere)

6. `POST /v1/verify` with a **fixed** `job_url` you trust; save JSON (or diff tool).
7. Repeat with `force_refresh: true` once — expect **fresh** evidence path; `cache.hit` behavior per contract.
8. Compare **verdict**, **confidence_score**, and **absence of internal jargon** in `llm_summary` and `review_summary.plain_summary` between local and prod (allow small LLM variance; **do not** allow raw signal IDs or instruction-echo).

### D. Trust UX invariants

9. **Summary** (`llm_summary`): no `Decision:`, no `Signals:`, no `fetch_ok` / `domain_align` style tokens.
10. **Company trust** (`review_summary`): no meta lines (“I need to…”, “Looking at the data…”); reputation stays in the right panel, not duplicated as a signal dump in Summary.

### E. When something fails

11. If only prod fails: re-read [deploy/RAILWAY_PARITY.md](../deploy/RAILWAY_PARITY.md) sections **Redis**, **datacenter fetch**, **LLM non-determinism**.
12. If `/ready` is red but app “works”: you likely have **partial** evidence — treat UI as advisory until readiness is green.

---

## Sign-off line

**Ship criteria:** `/ready` green for your intended prod profile, Redis wired when replicas >1, Serper configured, summaries clean, and one golden `POST /v1/verify` body matches expectations within the documented variance bands.
