# JobSignal — Master planning document

This document satisfies the planning deliverable defined in `.cursor/rules/JOBSIGNAL-RULES.mdc`. **No application code is specified here as implemented**; this is the agreed baseline before coding.

---

## 1. Product definition

JobSignal is a verification service for job seekers: the user submits a job URL and/or pasted job description, and the system gathers **multiple independent, explainable signals** (official careers presence, domain consistency, search corroboration, duplication and staleness hints). It returns a **recommendation** (`APPLY`, `VERIFY`, or `SKIP`) with **confidence**, **reasons**, and explicit **uncertainty** when data is thin. The product optimizes for **accuracy and reproducibility** over persuasive AI prose, and uses a **global cache** keyed on normalized inputs so identical public job fingerprints are not re-fetched unnecessarily, without storing tenant-private material in shared cache rows.

---

## 2. Exact MVP

| Area | MVP |
|------|-----|
| **Input types** | (a) Job posting URL. (b) Free-text job description paste (optional if URL provided). |
| **Output types** | Structured JSON (and mirrored UI): `verdict` (`APPLY` \| `VERIFY` \| `SKIP`), `confidence` (ordinal or 0–1 with bands), `reasons[]` (each tied to a signal id), `signals[]` (id, label, strength, source class), `cache` metadata (`hit` \| `miss`, `ttl_expires_at` if hit), `warnings[]` (e.g. weak source set, blocked fetch). |
| **Core signals** | Normalized URL; HTTP fetch of posting page when allowed (status, redirects, canonical hints); registrable domain vs careers subdomain heuristic; **search API** query packs (company name + role keywords + URL fragment) with result snippets counted and ranked; **duplicate** detection via normalized text hash + URL hash across recent cache window; **staleness** via posted date if present else “unknown” + listing age heuristics from search snippets if any. |
| **Minimum trust logic** | Tier sources: **T1** official company domain careers paths and same-domain HTTPS success; **T2** major job boards only as corroboration; **T3** generic web/search snippets. Never promote T3 to decisive without T1/T2 support. If T1 unavailable or contradictory → default **`VERIFY`**. If fetch blocked or content empty → **`VERIFY`** with warning. |
| **Minimum cache logic** | Normalize URL (scheme/host lowercase, strip tracking params per allowlist) and normalize text (Unicode NFKC, whitespace collapse, max length cap with hash of full text for key suffix). Key: `pipeline_version` + `model_or_scorer_version` + normalized fingerprint. TTL **10–30 days** (config default 14). Shared entry stores only **non-tenant-secret** fields. |
| **Minimum multi-tenant logic** | `tenant_id` on request for rate limits, audit, and **optional** tenant-scoped settings. **Verification pipeline output** for the same public fingerprint is shared. Per-tenant notes, internal recruiter notes, or PII **must not** be written into shared cache payload. |

---

## 3. Accuracy and trust principles

1. **Source ranking** — T1 (employer-controlled HTTPS same-registrable-domain careers) > T2 (reputable board listing match) > T3 (general web). Scores are **bounded** and **documented per signal**.
2. **Confidence handling** — Confidence is computed from **signal coverage** and **agreement**, not from LLM fluency. Disagreement lowers confidence and pushes toward `VERIFY`.
3. **Fallback behavior** — On any hard failure (timeout, 403, CAPTCHA, parse failure): return `VERIFY` or `SKIP` with explicit `warnings`, never `APPLY` based on guesswork.
4. **Stale data** — If posted date missing: label temporal certainty low; if TTL stale: refresh or mark response as `VERIFY` if refresh fails.
5. **Duplicate posting** — Same fingerprint in cache with different URLs → surface “likely duplicate” and reduce confidence for “unique opportunity” claims.
6. **Suspicious posting** — Mismatched domain, brand-new domain + high salary claims, missing company identity → increase `SKIP`/`VERIFY` weight; never assert fraud; use “suspicious pattern” language.
7. **When to return VERIFY** — Weak T1/T2; conflicting signals; partial fetch; ambiguous company; LLM used for structuring only and disagrees with rule engine; any policy flag “needs human”.

**AI role** — Optional: extract entities (company, title) and cluster evidence **with citations** to signal ids. **Never** let the LLM alone set `APPLY`.

---

## 4. Caching design

| Topic | Design |
|--------|--------|
| **Key strategy** | `v:{pipeline_version}|m:{scorer_version}|u:{normalized_url_hash}` and/or `t:{normalized_text_hash}`; if both URL and text, prefer URL-first with text hash as tie-breaker for URL-less submissions. |
| **Normalization** | URL: lowercase host, strip known tracking params, follow single-hop redirect for canonical URL capture (store final URL hash). Text: NFKC, collapse whitespace, remove zero-width, cap length (e.g. 32k) store `full_text_sha256` for identity. |
| **TTL** | 10–30 days configurable; default 14. Shorter TTL if labor market volatility is high (config only). |
| **Stale response policy** | On hit: return cached verdict with `cache.hit=true` and `ttl_expires_at`. Optional background refresh if past soft threshold (product decision in Sprint 2). |
| **Invalidation** | Bump `pipeline_version` or `scorer_version` to force new keys; manual admin invalidation by URL hash for incident response. |
| **Cross-tenant reuse** | Same key → same **public** verification payload. Tenant-specific fields stored **outside** shared document or in per-tenant store only. |
| **Privacy** | Shared cache: verdict, signal summaries, **redacted** snippets (length-capped), no user email, no internal notes, no API keys. |
| **Miss fallback** | Full pipeline run, then write shared row **after** stripping tenant data. |

---

## 5. Suggested workspace structure

```
docs/           Product, architecture, ADRs, API contracts (this file lives here)
prompts/        Paste-ready agent prompts per sprint
sprints/        Sprint goals, tasks, risks, checklists
frontend/       Future UI (URL paste, status, trust + uncertainty surfaces)
backend/        Future API, normalization, orchestration, scoring
cache/          Cache key helpers, TTL policies, invalidation docs/scripts
security/       Threat models, headers, rate limit policies, secret handling
deployment/     Infra diagrams-as-code notes, env matrices, rollback checklists
data_sources/   Provider contracts, query templates, allowed domains
tests/          Unit, integration, contract, e2e smoke
```

Each top-level folder includes a short `README.md` until code exists.

---

## 6. Data source plan

| Need | Approach |
|------|----------|
| Official careers | Fetch same-registrable-domain careers paths (robots.txt respected); match job title tokens if HTML available. |
| Search engine / API | Use a **hosted search API** (provider TBD at implementation); query packs with quoted URL fragments and company + title. |
| Company domain | Parse registrable domain from email/URL in posting; compare to careers fetch domain. |
| Repeated posting | Hash normalized description; compare to recent cache entries and search “exact phrase” samples. |
| Recruiter identity | MVP: surface only if **public** LinkedIn or company page corroboration exists; otherwise “unknown” — no OSINT deep dive in MVP. |
| Stale listing | Extract dates from page/metadata; else infer “unknown”; combine with listing first-seen in cache. |
| Public reputation | **Future** — optional review aggregators; not MVP unless clearly licensed and TOS-compliant. |

**Out of scope for MVP:** building a large-scale crawler beyond single-job fetches and search API calls.

---

## 7. Sprint roadmap

Detailed task breakdowns, risks, fallbacks, and manual checklists: **`sprints/sprint-01-architecture-trust.md`** through **`sprints/sprint-04-hardening-deploy.md`**.

Summary:

| Sprint | Goal |
|--------|------|
| **1** | Architecture, repo wiring, trust model as code/spec, empty vertical slice traced on paper |
| **2** | Ingestion (fetch + search), cache read/write, normalization, observability hooks |
| **3** | Scoring + verdict rules, API contract freeze, frontend flow with uncertainty UI |
| **4** | Test matrix, security pass, deployment checklist, scope freeze |

---

## 8. Sprint prompt pack

Paste-ready prompts (one file per sprint) live in:

- `prompts/sprint-01-agent.md`
- `prompts/sprint-02-agent.md`
- `prompts/sprint-03-agent.md`
- `prompts/sprint-04-agent.md`

Each file instructs an agent to stay in-sprint, update docs, add tests, preserve accuracy-first and cache/tenant rules, and document any deviation.

---

## 9. Frontend plan

- **Input** — URL field + optional description textarea; client-side length limits; disable submit while in-flight.
- **Status** — `idle` → `validating` → `running` → `complete` \| `error`.
- **Loading** — Determinate progress where possible (step labels: normalize, fetch, search, score); indeterminate spinner acceptable for MVP if steps not wired.
- **Trust** — Show verdict, confidence band, and **per-signal** rows (icon + label + strength), not a single opaque score.
- **Reasons** — Human-readable list mapped to signal ids; link to “why VERIFY” explainer when verdict is VERIFY.
- **Cache hit** — Badge: “Result from recent verification” + expiry date.
- **Warnings** — Yellow callouts: weak sources, blocked fetch, stale unknown date.
- **Errors** — Red, actionable (retry, check URL), no fake verdict on error.
- **Low confidence** — Always visible copy: “Limited data — consider VERIFY manually.”

---

## 10. Backend plan

| Responsibility | Notes |
|----------------|--------|
| Normalization | Central module; unit-tested golden vectors. |
| Source collection | Pluggable providers; timeouts; parallel with ceiling. |
| Trust scoring | Rule-first engine; versioned; deterministic given same inputs. |
| Cache lookup / write | Before run and after successful run; strip tenant fields. |
| Verdict generation | Map score + gates to APPLY/VERIFY/SKIP. |
| Response schema | JSON Schema or OpenAPI; reject incomplete internal states. |
| Error handling | Typed errors → stable client codes; no stack traces to client. |
| Observability | Trace id, tenant id (hashed optional), latency per signal, cache hit/miss. |
| Rate limiting | Per IP + per tenant; backoff headers. |

---

## 11. Testing and reliability plan

- **Unit** — Normalization, URL parsing, key derivation, scoring gates, TTL math.
- **Integration** — Mocked HTTP + mocked search; golden “fixture jobs” folder.
- **Cache** — Hit/miss, TTL expiry simulation, key collision tests, tenant strip regression.
- **Source validation** — Each provider adapter: failure modes, empty results, rate limit.
- **Scoring** — Table-driven cases: conflicting T1/T3, missing T1, duplicate text, stale date.
- **Failure paths** — All providers down → VERIFY/SKIP only; partial data → VERIFY.
- **Frontend smoke** — Playwright or Cypress: happy path, error path, VERIFY path.
- **Regression** — Curated real URLs (non-PII) checked in CI with **recorded** mocks to avoid flake.

Focus: **no false confidence**; **no silent downgrade** of warnings.

---

## 12. Security and privacy plan

- **API keys** — Server-only; never log; rotate via `.env` / secret manager.
- **Env hygiene** — `.env.example` only placeholders; CI uses masked secrets.
- **Tenant isolation** — Auth boundary (even demo token) for tenant settings; logs include tenant id only if needed and policy-approved.
- **Shared cache safety** — Automated test that tenant-only fields never serialize into cache payload.
- **Log hygiene** — Redact query strings with tokens; truncate job text in logs.
- **Safe URL** — SSRF controls: allowlist schemes (http/https), block private IP ranges, limit redirects.
- **Safe text** — Max sizes; MIME sniff not trusted for execution.
- **Rate limits** — As in `.env.example`; stricter on expensive endpoints.
- **Prompt injection** — If LLM used: treat job text as untrusted data; system prompt boundaries; no tool execution from model.
- **Access control** — MVP demo: API key or JWT; roadmap for proper auth.

---

## 13. Deployment readiness plan

Before production-like deploy:

- [ ] All required env vars documented and validated at startup
- [ ] Backend service health: `/health`, `/ready` (cache + search reachability)
- [ ] Frontend build pinned; CDN or static host
- [ ] Cache backend provisioned with persistence policy
- [ ] External API keys rotated and scoped
- [ ] Rollback: previous container/image tag pinned; DB/cache migration backward-compatible or feature-flagged
- [ ] Monitoring: error rate, latency p95, cache hit ratio, per-signal failure rate
- [ ] On-call runbook one-pager in `deployment/`

---

## 14. Extension points

- Richer employer sources (ATS feeds where licensed)
- Stronger reputation and litigation/warn lists (legal review)
- User watchlists and alerts
- Browser extension / bookmarklet
- Saved history (per user, privacy-reviewed)
- Stronger dedup (embeddings **only** as duplicate hint, not truth)
- Cross-tenant **aggregated** analytics with k-anonymity thresholds (not MVP)

---

## 15. Final frozen scope

**In scope for JobSignal v1 (MVP):** single-user or lightly multi-tenant **verification** of a job URL and/or pasted description using **rule-first** scoring, **multiple explainable signals**, **global shared cache** of public fingerprints with TTL, and explicit **VERIFY** / low-confidence behavior when evidence is insufficient.

**Out of scope:** operating a job board, mass crawling the open web, hosting employer reputation blacklists, or claiming legal or factual certainty about fraud or scam status.
