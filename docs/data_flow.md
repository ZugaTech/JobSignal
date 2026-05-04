# JobSignal — Data flow (Sprint 2)

This document is the **precise** ingestion → cache → evidence pipeline. It implements Sprint 2 scope only: **no** final verdict polish and **no** production deployment hardening.

## 1. Entry

| Input | Source | Max size (enforced at API) |
|-------|--------|----------------------------|
| `job_url` | Client | e.g. 2048 chars (config) |
| `job_description` | Client paste | e.g. 64k raw → normalized cap in `normalization.py` |

Optional: `tenant_id` (header/JWT) for **quota and audit only** — never part of the **public cache key**.

## 2. Ordered pipeline (single verify request)

```text
1. Validate raw request (size, allowed schemes for URL).
2. Normalize URL and/or text → NormalizedFingerprint + NormalizationResult
      (see backend/core/normalization.py)
3. Extract entities (company / title / location hints) → ExtractionResult
      — heuristic only; may be empty; never fabricated “facts”
      (see backend/core/extraction.py + docs/source_validation.md)
4. Build public cache key from:
      normalization_version + pipeline_version + source_set_version + fingerprint
      (see backend/core/cache_key.py + docs/cache_design.md)
5. Cache GET
   - HIT and not expired → return CachedPayload + metadata (skip collectors)
   - MISS or expired → continue
6. Collect sources (parallel with global timeout budget)
   a. Fetch adapter: HTTP GET job URL (SSRF-safe) → FetchEvidence | FailureEvidence
   b. Search adapter: query packs built from URL + extracted hints → SearchHit[]
   c. Dedupe/stale helpers: read only **public** cache index fields / hashes — no tenant PII
7. Assemble EvidenceBundle (ordered by trust tier, then strength)
      (see backend/core/source_evidence.py)
8. Cache SET (only if write policy allows — e.g. not on hard-abort)
   - Serialize **SharedCachePayload** after strip_tenant_fields()
9. Pass EvidenceBundle forward to **Sprint 3** scorer (out of scope here)
```

## 3. Data structures (logical)

| Artifact | Produced by | Consumed by |
|----------|---------------|-------------|
| `NormalizationResult` | `normalization` | `cache_key`, `extraction`, collectors |
| `ExtractionResult` | `extraction` | search query packs |
| `PublicCacheKey` | `cache_key` | `cache_store` |
| `SharedCachePayload` | orchestration (assembly) | `cache_store` after redaction |
| `EvidenceBundle` | collectors + ordering | Sprint 3 scorer |

## 4. Uncertainty surfacing (pre-verdict)

Sprint 2 code does **not** assign `APPLY`/`VERIFY`/`SKIP`. It **does** attach:

- per-source **failure** or **empty** flags in evidence metadata;
- **warnings** list suggestions (e.g. `SEARCH_EMPTY`, `FETCH_BLOCKED`) carried in bundle for the scorer/UI later.

Low trust from missing T1/T2 must be **visible** in evidence coverage, not hidden behind a single score.

## 5. Reproducibility

Same raw inputs → same normalization version → same fingerprint → same cache key (for fixed `pipeline_version` and `source_set_version`). Any intentional behavior change **must** bump `pipeline_version` and/or `source_set_version` per `docs/cache_design.md`.

## 6. Related documents

- `cache_design.md` — TTL, invalidation, cross-tenant rules, get/set
- `source_validation.md` — search packs, trust tiers, fallbacks
- `architecture.md` — system context
- `backend/core/*.py` — reference implementation

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 2 | Initial `data_flow.md` | Sprint 2 required output; pins orchestration order. |
