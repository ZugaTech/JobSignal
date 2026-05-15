# JobSignal — vNext plan: screenshots + optional “similar jobs”

**Status:** planning / backlog (major multimodal + recommendation milestones shipped; remaining rows are polish and datasets).

**Historical:** Originally framed as sprint-sized increments for rapid iteration.  
**Date:** 2026-05-06 (expanded 2026-05-06 with Sprints 9–12 for gap closure).  
**Authority:** aligns with `.cursor/rules/JOBSIGNAL-RULES.mdc`, `docs/trust_model.md`, `docs/cache_design.md`, `docs/security.md`, and the post–Sprint 4 integration baseline (`docs/TECHNICAL-LEDGER.md`).

## 0) Scope acknowledgment (explicit expansion)

`docs/final_scope.md` (Sprint 4 freeze) currently lists **URL and/or pasted text** as primary inputs. This vNext plan adds:

1. **Screenshot / image input** (multimodal ingestion) with honest OCR/extraction uncertainty.
2. **Optional recommendations** (max **3** candidates) using **search-based retrieval + verify** (Option A), with **high confidence prioritized**, **medium allowed second**, always labeled.

Before shipping, update **`docs/final_scope.md`** (or add a dated `docs/scope_addendum_YYYY-MM-DD.md`) so the expansion is not “silent drift.”

## 1) Product decisions (locked for this plan)

### 1.1 Retrieval strategy for recommendations (Option A)

- Build query packs from the **seed job** (canonical URL fragments, company/title hints, domain-restricted variants where provider supports it).
- Retrieve candidate URLs via hosted search APIs (candidate providers already recorded in `docs/TECHNICAL-LEDGER.md` / `docs/source_validation.md`):
  - **SerpAPI**, **Zenserp**, **Bing Web Search**, **Google Programmable Search**
- For each candidate URL (bounded N), run the **same verification pipeline** (or a reduced-cost “pre-verify” stage if documented—default is **full verify** for honesty).
- **Not** a job board: no continuous crawling, no public blacklist, no “guaranteed best jobs.”

### 1.2 Screenshot insufficient-data UX

If image ingestion yields **low OCR/extraction quality** or missing critical fields (no meaningful title/company/domain/URL cues):

- Return a **blocking user message**: *“Screenshot doesn’t contain enough readable job details—please paste the job URL (preferred) or paste the full job text.”*
- Still allow partial progress only if policy explicitly documents it (default: **do not** pretend verification completeness).

### 1.3 Recommendations are optional + configurable

- Add a **user-visible toggle** (and optional advanced settings):
  - `recommendations_enabled` (default: **off** for conservative demos, or **on** if you want flashier judging—pick one default at implementation time and document it)
  - `recommendations_max_candidates` fixed cap **3** (hard max in API)
  - `recommendations_min_confidence` default: **high preferred**; allow **medium** only if labeled and sorted after highs

### 1.4 Candidate selection rules

- Maximum **3** recommendations.
- Ranking:
  1. **High** confidence first (stable tie-break: stronger corroboration / more independent tiers)
  2. **Medium** confidence second
- UI must show a **visible badge** per item: `HIGH` vs `MEDIUM` and a short “why similar” + “why this confidence.”

### 1.5 OCR / multimodal extraction preference (hackathon-pragmatic)

From `local-session-archive.md` (private reference; not committed): the hackathon path favors **fast managed inference** via **Fireworks** (OpenAI-compatible client, API key in env) for LLM-assisted extraction/reasoning, while **search** remains separate provider(s).

**Plan default (pragmatic):**

- **Primary:** Fireworks **vision-capable** chat completion for screenshot → structured extraction JSON (strict schema) + `extraction_confidence` + warnings.
- **Fallback:** if no key / model unavailable / low confidence → **prompt user for URL** (per §1.2).
- **Important:** confirm the exact **vision model id** from current Fireworks docs at implementation time (do not hardcode a stale model name in production config).

## 2) Non‑negotiables (doctrine)

- **Accuracy & honesty:** weak evidence → `VERIFY` + warnings; never fake job details from a blurry screenshot.
- **No invented evidence:** OCR output is **untrusted**; run `prompt_guard` findings as warnings; never let model alone force `APPLY`.
- **Cache:** recommendations must not introduce tenant-private fields into shared cache payloads; any new cache keys must include relevant **pipeline / provider-set / OCR / recommender** versions per `docs/cache_design.md`.
- **Security:** image upload size limits, MIME validation, ephemeral storage preferred, SSRF-safe fetch for candidate URLs.
- **Tests:** CI remains deterministic: **fixtures mode** for search + OCR stubs; live provider tests optional/marked.

## 3) Architecture sketch (minimal additions)

### New modules (conceptual)

- `backend/core/image_ingest.py` — validate bytes/MIME/size; call vision extractor; produce `ExtractedJobText` + `ingestion_warnings[]`.
- `backend/core/recommendations.py` — build query packs; call search providers with **multi-provider fallback**; verify candidates; rank top 3.
- Extend `backend/core/orchestrator.py` — branch: URL/text vs image vs combined; honor settings flags.
- Extend API schema — optional `multipart/form-data` or `image_base64` (choose one; prefer multipart for hackathon demos).
- Extend `PublicVerifyReport` / response JSON — optional `recommendations[]` with explicit confidence labels.

### Settings surface

- **MVP settings:** query params or JSON body flags on `/v1/verify` (fastest), later: user settings persistence (out of scope unless needed).

## 4) Hackathon-style sprint breakdown

> Convention per sprint: **Goal**, **Scope**, **Tasks**, **Done criteria**, **Demo script**, **Risks**, **Fallback**, **Commit discipline** (granular commits + push; no single mega-commit).

---

### Sprint 5 — Image ingestion + “insufficient screenshot” UX (no recommendations yet)

**Goal:** User can submit a screenshot and receive the same honesty-first verification output **when extraction is good enough**; otherwise get a clear “paste URL” instruction.

**Scope**

- Image upload path (multipart) OR base64 (pick one and document).
- Fireworks vision extraction behind feature flag env (`FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `FIREWORKS_VISION_MODEL`).
- Strict JSON schema validation for model output; on schema failure → treat as insufficient.
- Wire extracted text into existing normalize/score path (still fixtures/search as today).

**Tasks**

1. Docs: `docs/image_ingestion.md` (threats, retention, limits, failure modes).
2. API: extend `/v1/verify` to accept image + optional URL/text.
3. Core: `image_ingest` + tests (fixtures: fake extractor responses).
4. Frontend: file input + preview + show extraction confidence + warnings.
5. Update `docs/TECHNICAL-LEDGER.md` + `docs/PROGRESS-LOG.md`.

**Done criteria**

- `pytest` green with deterministic fixtures (no network).
- If extraction confidence low / missing fields → **no fabricated verdict**; user prompted to provide URL.
- No secrets committed; `.env.example` updated.

**Demo script (60–90s)**

- Upload clear screenshot → shows extracted fields + VERIFY/APPLY/SKIP.
- Upload blank/blur image → shows “please share URL” path.

**Risks**

- Vision model availability/cost; mitigate with fixtures + feature flag.

**Fallback**

- Disable image path via env; UI hides upload.

---

### Sprint 6 — Recommendations v1 (Option A: search + verify, max 3, optional) — **shipped**

**Goal:** After primary verification, optionally return up to **3** similar jobs, ranked **high then medium**, clearly labeled.

**Scope**

- Settings: `recommendations_enabled` + hard max 3.
- Query pack builder from seed normalization + extraction hints.
- Provider router: try provider A → on empty/error try B (SerpAPI/Zenserp/Bing/Google — order configurable via env).
- Candidate verification: reuse orchestrator in “candidate mode” with strict budgets (max URLs, timeouts).
- Response: `recommendations[]` with `similarity_reasons[]`, `confidence_band`, `warnings[]`, `source_urls` (redacted length caps).

**Tasks**

1. Docs: `docs/recommendations.md` (honesty rules, limits, “not a job board”).
2. Core: `recommendations.py` + provider adapter interfaces + fixtures.
3. API: extend response schema; version bump `report_schema_version` if needed (document).
4. Frontend: optional section + settings toggle + badges HIGH/MEDIUM.
5. Tests: fixture search JSON → deterministic ranking; ensure never returns >3.

**Done criteria**

- With `recommendations_enabled=false`, behavior identical to pre-Sprint-6.
- With enabled, never returns >3; never labels medium as high.
- Multi-provider fallback covered by unit tests (simulated failures).

**Demo script**

- Verify a real fixture seed → toggling recommendations shows 0–3 cards.
- Force provider A fail → provider B still returns (fixture).

**Risks**

- Cost + rate limits; mitigate with strict caps and caching of candidate verification.

**Fallback**

- Auto-disable recommendations if no search keys present (clear UI message).

---

### Sprint 7 — Production-ish hardening for multimodal + recommendations

**Goal:** Make the new paths safe enough for judges and early deploy without scope creep.

**Scope**

- SSRF checks for candidate fetches; byte/time caps; redirect limits.
- Abuse controls: max image size, per-IP rate limits (documented at gateway if not in app).
- Cache keys updated for OCR + recommender versions.
- `/ready` reflects dependency health (at least “search configured?” boolean without leaking secrets).

**Tasks**

1. Extend `docs/security.md` + `docs/reliability.md` minimally (facts only).
2. Add tests for failure modes (provider down, empty SERP, bad image).
3. Update `deployment_readiness.md` with new env vars.

**Done criteria**

- `pytest` green; no new linter issues in touched files.
- Ledger updated: OCR + recommendations marked 🟢/🟡 accurately.

---

### Sprint 8 — Hackathon polish: demo script, submission checklist, optional CI

**Goal:** Ship story is crisp: problem → verify → optional similar jobs → honesty.

**Scope**

- 2–3 minute demo narrative + screenshots.
- GitHub Actions: `pytest` on PR (if allowed time).
- Tag a release commit for submission.

**Tasks**

1. `docs/demo_script.md` + update `docs/PROGRESS-LOG.md`.
2. `.github/workflows/pytest.yml` (optional).
3. Final ledger “Last verified” + remaining risks.

**Done criteria**

- A new teammate can run locally with README + `.env.example` only.
- Demo path works without “works on my machine” secrets (fixtures mode).

---

### Suggested execution order (dependencies)

Use this when choosing **which sprint to run next**; adjust for hackathon deadlines.

| Order | Sprint | Why |
|-------|--------|-----|
| 1 | **9** — Primary job fetch | Biggest credibility gap: real page read for user-supplied URL (SSRF-safe). Feeds stronger `fetch_ok` / domain signals before recommendations. |
| 2 | **6** — Recommendations | Reuses the same safe fetch pattern for **candidate** URLs; search router + max 3 + labeled confidence. |
| 3 | **7** — Hardening | Tighten caps, abuse paths, cache-key versioning for recommender/OCR; `/ready` booleans without leaking secrets. |
| 4 | **10** — Redis + `/ready` | Production-leaning shared cache + readiness that matches deploy story. |
| 5 | **11** — Frontend explainability | Timeline, signal detail, settings, “from image” fields — high judge impact, can parallelize after API is stable. |
| 6 | **8** + **12** | CI, tag, demo script (**8**) + credible fixture dataset and narrative depth (**12**); merge if time-constrained. |

**UI-first shortcut:** If the deadline is visual only, do **11** earlier; keep **9** on the critical path before claiming “we verified the live posting.”

---

### Sprint 9 — Live primary job URL fetch (SSRF-safe evidence) — **shipped**

**Goal:** When the user supplies a **canonical job URL**, the backend **fetches that page once** (within strict limits) and derives **real** evidence signals (e.g. fetch success, size, final URL, safe excerpt/hash hooks) so scoring is not fixtures-only for that path.

**Scope**

- SSRF protections: block private/reserved IPs, non-HTTP(S), redirect cap, total byte cap, total time cap (align with `FETCH_MAX_BYTES` / `FETCH_MAX_REDIRECTS` / env).
- No tenant or secret data in shared cache payloads; optional content hash / length only in signals.
- Feature flag or `NODE_ENV`-style gating if needed for CI (fixtures mode remains default for deterministic tests).
- Orchestrator: after normalize, if URL present and fetch enabled → attach signals; on failure → VERIFY-leaning warnings, never invented page text.

**Tasks**

1. Docs: extend `docs/security.md` + short `docs/fetch_adapter.md` (threats, limits, failure modes).
2. Core: `fetch_job_page.py` (or equivalent) + interface for tests; wire into `orchestrator.py`.
3. Tests: local HTTP stub or `respx`/`httpx` mock; tests for SSRF blocks, redirect loop, oversize body.
4. Update `docs/TECHNICAL-LEDGER.md` + `docs/PROGRESS-LOG.md`.

**Done criteria**

- `pytest` green with **no live network** in default suite.
- With fetch disabled or URL absent, behavior unchanged vs current baseline.
- With fetch enabled and stub “200 OK”, new signals appear and are documented.

**Risks**

- Misconfigured allowlists; mitigate with conservative defaults and tests for blocked hosts.

**Fallback**

- Ship with fetch off; fixtures-only path remains.

---

### Sprint 10 — Shared cache (Redis) + truthful `/ready`

**Goal:** Optional **Redis**-backed cache via `CACHE_URL` for multi-instance deploys; **`/ready`** reflects real dependency health (cache reachable, optional “search configured” boolean) **without** exposing secrets.

**Scope**

- Implement `CacheStore` backend that speaks Redis when `CACHE_URL` set; retain in-memory for local dev.
- `EnvConfig.load(strict=True)` / production path already expects `CACHE_URL` — align implementation and docs.
- `/ready`: return 503 when strict dependencies fail; JSON fields are booleans + short codes only.

**Tasks**

1. Core: Redis cache adapter + connection timeout; fall back documented.
2. API: wire `/ready` to ping cache (and optionally flag file for “search keys present”).
3. Docs: `docs/deployment_readiness.md`, `.env.example`, `deployment/RUNBOOK.md`.
4. Tests: use `fakeredis` or container optional marker; unit tests for adapter contract.

**Done criteria**

- Local dev works with **no** `CACHE_URL` (in-memory).
- With fake/redis test double, `/ready` flips deterministically in tests.

**Risks**

- Redis TLS URL variants; document one supported format first.

**Fallback**

- Stay on in-memory cache; document single-instance deploy only.

---

### Sprint 11 — Frontend: explainability, settings, multimodal surfacing

**Goal:** Make the **honesty story obvious** in the UI: what ran, what was uncertain, and what came from the screenshot — without inventing certainty.

**Scope**

- **Pipeline timeline** (compact): normalize → cache → evidence → score (copy from server meta where available; client-side labels OK for static steps if API does not yet expose a full trace).
- **Signal detail:** expandable rows or “why this signal” using existing `signals[]`, `reasons[]`, `warnings[]`.
- **Settings strip:** API base URL (existing), toggles for features that exist (recommendations, vision) even if some are no-ops until backend ships — show disabled reason from `/ready` or static copy.
- **From image:** when `ingestion` + model fields exist, show a small read-only panel (title/company/URL hint) distinct from user paste.
- **Polish:** loading skeleton, mobile spacing, focus/aria for dynamic regions.

**Tasks**

1. `docs/frontend_flow.md` update (states + new sections).
2. `frontend/index.html` + `app.js` + `styles.css` (incremental; no framework migration required).
3. Optional: lightweight `GET /v1/capabilities` later — out of scope unless it reduces guesswork; prefer `/ready` JSON fields first.

**Done criteria**

- Manual pass: URL-only, text-only, screenshot-only (stub), and error path all readable.
- No verdict or APPLY styling that implies legal proof.

**Risks**

- Over-building “fake progress” steps; only show steps that reflect real backend behavior.

**Fallback**

- Ship timeline as 3 bullets + expanded signals table only.

---

### Sprint 12 — Demo dataset, narrative depth, submission crispness

**Goal:** Judges see **repeatable** outcomes: real URLs in `verify_fixtures.json` (correct hashes), a **2–3 minute script** with expected screenshots, and a checklist so “works on my machine” is minimized.

**Scope**

- Curate **3–5** real job postings (or stable archived pages if allowed); document how hashes were generated; expand fixtures.
- `docs/demo_script.md`: problem → verify (URL + screenshot) → optional recommendations → honesty disclaimer.
- Submission checklist: env template, `uvicorn` + static server commands, what works without API keys.
- Optional: screen recording storyboard (bullet list).

**Tasks**

1. Data: `data_sources/fixtures/verify_fixtures.json` + README in `data_sources/fixtures/`.
2. Docs: demo script + checklist; link from root `README.md` (one paragraph).
3. Align with Sprint **8** (CI/tag): same release commit can satisfy both.

**Done criteria**

- Fresh clone + `.env.example` only → **fixtures mode** demo runs end-to-end.
- At least one **live** demo path documented (keys required) vs **fixtures** path.

**Risks**

- Jobs expire offline; mitigate with fixture-backed primary judge path + optional live URL.

**Fallback**

- Fixtures-only demo with fictional but stable text fingerprints (document clearly).

---

## 5) Environment variables (planning list — implement later)

**OCR / extraction**

- `FIREWORKS_API_KEY`
- `FIREWORKS_BASE_URL` (default `https://api.fireworks.ai/inference/v1`)
- `FIREWORKS_VISION_MODEL` (must be validated against current docs)

**Search providers (multi-fallback)**

- `SERPAPI_API_KEY` / endpoint config (as per provider)
- `ZENSERP_API_KEY`
- `BING_SEARCH_KEY` + `BING_SEARCH_ENDPOINT`
- `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX`

**Feature flags**

- `JOBSIGNAL_IMAGE_INGEST_ENABLED` (default off/on per your demo choice)
- `JOBSIGNAL_RECOMMENDATIONS_ENABLED` (default off/on per your demo choice)
- `JOBSIGNAL_RECOMMENDATIONS_MAX` (hard-cap at 3 in code even if env tries higher)

## 6) “Next actions” for when you say proceed

1. ~~Add **`docs/scope_addendum_2026-05-06.md`** + update `docs/final_scope.md` pointers~~ (done for image scope).
2. ~~Implement Sprint 5 behind flags with fixtures-first tests.~~ (shipped.)
3. Pick next sprint from **§4.1 Suggested execution order** (typical: **9** then **6**).
4. Track implementation in `docs/PROGRESS-LOG.md` + `docs/TECHNICAL-LEDGER.md` after each sprint.

---

## Change log

| Date | Change | Why |
|------|--------|-----|
| 2026-05-06 | Created vNext sprint plan doc | User-approved scope expansion planning; execution deferred. |
| 2026-05-06 | Added **Sprints 9–12** + **§4.1 execution order** | Close ledger gaps: SSRF primary fetch, Redis/`/ready`, frontend explainability, demo dataset; align with backlog discussion. |
