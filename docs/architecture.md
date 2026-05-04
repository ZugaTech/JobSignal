# JobSignal — System architecture (Sprint 1)

This document defines the **logical architecture** for the job verification service. It is the canonical reference for how source validation, caching, multi-tenant boundaries, and future deployment fit together. Implementation details (frameworks, vendors) are deliberately left as pluggable choices.

## 1. Goals and constraints

- **Accuracy over speed:** weak evidence must yield **`VERIFY`**, not `APPLY`.
- **Reproducibility:** same normalized public fingerprint and same pipeline or scorer version should produce the same deterministic rule outcome (LLM may not override `APPLY`).
- **Global cache:** identical **normalized** public inputs share one cached **verification payload**; **tenant-private** data never enters that payload.
- **Hackathon-realistic scope:** one API, bounded fetches, hosted search API (adapter), rule engine, thin UI later—not a crawler platform.

## 2. High-level context diagram

```text
          +-------------+
 Tenant -> |   API GW    |  (auth / tenant id / rate limits)
          +------+------+
                 |
          +------v------+
          | Orchestrator |
          +------+------+
                 |
     +-----------+-----------+
     |           |           |
+----v---+  +----v----+ +----v----+
|Normalize| | Cache  | | Scorer  |
|         | | get/set| | (rules) |
+----+----+ +----+---+ +----+----+
     |           |          ^
+----v-----------v----------+----+
|        Source collectors    |
| (fetch, search, dedupe...)  |
+------------------------------+
```

## 3. Request lifecycle

1. **Authenticate / bind tenant** (even if MVP uses a static API key per demo tenant).
2. **Validate input** — reject oversize payloads; schema validate.
3. **Normalize** — produce `NormalizedJobInput` (see `trust_model.md` for field semantics).
4. **Cache lookup** — compute **public** cache key; on **hit**, return stored verification DTO + `cache.hit=true` (subject to TTL policy in `trust_model.md`).
5. **On miss — collect sources** — bounded parallel collection: HTTP fetch (if URL), search packs, in-process dedupe/stale helpers reading **cache metadata only** (no PII).
6. **Score** — rule engine consumes structured signal objects; outputs verdict + confidence band + reasons.
7. **Cache write** — serialize **tenant-safe** DTO only; attach `pipeline_version`, `scorer_version`, `ttl`.
8. **Respond** — merge tenant-allowed response fields (never merge secret notes from cache).

This flow supports **later deployment** as a single stateless API service behind a load balancer, with cache and optional DB as external services.

## 4. Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| **API gateway** | TLS termination (in prod), request IDs, tenant resolution, rate limits, request size caps. |
| **Orchestrator** | Ordered steps, timeouts, partial failure aggregation, never emits `APPLY` without passing trust gates. |
| **Normalization** | Single module; versioned; unit-tested golden vectors (Sprint 2). |
| **Source collectors** | Pluggable interfaces: `Fetcher`, `SearchAdapter`, `DuplicateChecker`, `StalenessHelper`. Each returns **typed evidence**, not prose verdicts. |
| **Scorer (rule engine)** | Deterministic mapping from evidence to `APPLY` \| `VERIFY` \| `SKIP` and confidence; version string bumps invalidate cache keys. |
| **Cache layer** | Get/set by public key; TTL enforcement; serialization guard (no tenant secrets). |
| **Observability** | Structured logs, metrics (latency per collector, cache hit rate), tracing (optional). |

## 5. Normalized input types (logical schema)

Defined in TypeScript-like pseudocode for API contracts; language-agnostic.

```text
type NormalizedJobInput = {
  /** Semantic version of normalization rules, e.g. "1.0.0" */
  normalization_version: string;

  /** Lowercase scheme/host, tracking params stripped, redirect policy applied */
  canonical_url: string | null;
  canonical_url_sha256: string | null;

  /** NFKC text, whitespace collapsed, max length truncated; hash of full pre-truncation text */
  description_text: string | null;
  description_full_sha256: string | null;

  /** Registrable domain derived from URL or text heuristics when possible */
  registrable_domain: string | null;
};
```

Requests may carry **raw** `job_url` and/or `job_description`; the orchestrator always computes `NormalizedJobInput` before cache lookup and collection.

## 6. API response schema (verify result)

Public JSON shape returned to clients (UI and integrations). Field names are stable for contract tests.

```text
type Verdict = "APPLY" | "VERIFY" | "SKIP";

type SignalEvidence = {
  id: string;                 // e.g. "fetch_ok", "search_corroboration"
  label: string;              // human-readable
  tier: "T1" | "T2" | "T3" | "none";
  strength: "high" | "medium" | "low" | "none";
  details: string;            // redacted, length-capped explanation
};

type VerifyResponse = {
  request_id: string;
  verdict: Verdict;
  confidence: number;         // 0..1 with documented bands; never alone as "truth"
  confidence_band: "high" | "medium" | "low";
  signals: SignalEvidence[];
  reasons: { code: string; message: string }[];
  warnings: { code: string; message: string }[];
  cache: {
    hit: boolean;
    ttl_expires_at: string | null;  // ISO-8601 when known
    key_fingerprint: string;          // opaque or hash prefix for debugging
  };
  /** Optional: same structure as cached global payload; never includes tenant-private notes */
  meta: {
    pipeline_version: string;
    scorer_version: string;
  };
};
```

**Uncertainty:** when `confidence_band` is `low` or `warnings` is non-empty, copy and UI must reinforce that the user should **manually verify**.

## 7. Multi-tenant separation model

| Concern | Model |
|---------|--------|
| **Identity** | Every request carries `tenant_id` (header or JWT claim). |
| **Quotas** | Rate limits keyed by `tenant_id` + IP (defense in depth). |
| **Audit** | Logs may record `tenant_id` and hashed user id per retention policy. |
| **Shared verification cache** | Keyed only on **public** normalized fingerprint + `pipeline_version` + `scorer_version`. Value = `VerifyResponse` subset without tenant fields. |
| **Tenant-private data** | Examples: internal recruiter notes, ATS IDs, user saved comments. Stored in **tenant-scoped** store (or omitted in MVP). **Never** written into shared cache value. |
| **Per-tenant feature flags** | e.g. stricter `APPLY` threshold; applied in scorer **after** reading shared evidence, may only tighten outcomes. |

This supports a **multi-tenant future** without cache leakage.

## 8. Cache key concept (high level)

A **cache key** identifies one **global** record for a **public job fingerprint**:

- **Inputs to the key:** `pipeline_version`, `scorer_version`, `canonical_url_sha256` (if URL present), else `description_full_sha256`, plus `normalization_version` if not already folded into `pipeline_version` (choose one scheme in Sprint 2 and document).
- **Not in the key:** `tenant_id`, user id, API keys, private notes.
- **TTL:** configurable 10–30 days (default 14). See `environment.md`.

## 9. Source ranking rules (summary)

Authoritative detail: `trust_model.md`. Summary: **T1 > T2 > T3**; T3 cannot justify `APPLY` alone; conflicts and missing T1/T2 push to **`VERIFY`**.

## 10. Minimal runtime dependencies (conceptual)

These are **categories**, not vendor commitments. Pick concrete packages or services in Sprint 2+.

| Category | Purpose |
|----------|---------|
| HTTP server library | REST API for `/v1/verify` (or equivalent). |
| JSON schema validation | Request/response validation. |
| HTTP client | Bounded fetch of job pages. |
| Search API client | Hosted search queries (adapter). |
| Cache client | Redis-compatible or managed cache (recommended for TTL). |
| Optional: LLM client | Entity extraction only; must not gate `APPLY` alone. |

**Development:** test runner, linter, formatter, type checker (choices recorded when code lands).

## 11. Deployment shape (future-ready)

- **Stateless API** instances horizontally scaled.
- **Cache** external (Redis, etc.).
- **Secrets** from environment or secret manager—not repo.
- **Health checks:** `/health` (live) and `/ready` (cache/search reachability optional).
- **Rollback:** pinned image/version; feature flag to disable `APPLY` globally in incident.

## 12. Simplicity check (short-build fit)

- Single verify endpoint plus health endpoints for MVP.
- No user-generated job hosting, no mass crawl, no public blacklist.
- Complexity budget: **N collectors** (small N) + **one** rule engine + **one** cache.

## Related documents

- `trust_model.md` — tiers, VERIFY gates, signal IDs.
- `scope.md` — MVP in/out.
- `environment.md` — variables and operational knobs.
- `folder_structure.md` — repository layout.
- `JOBSIGNAL-MASTER-PLAN.md` — earlier integrated baseline (keep in sync when principles change).

## Change log (plan improvements)

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Introduced `docs/architecture.md` as canonical architecture surface | Sprint 1 prompt requires dedicated file; improves navigability vs master plan only. |
