# JobSignal — Source validation and search enrichment (Sprint 2)

## 1. Principles

- **Never trust a single source.** Minimum narrative: fetch (if allowed) **plus** independent search packs, unless fetch is impossible (paste-only).
- **Do not invent evidence.** Empty results are explicit; heuristics emit **low** strength with clear `details`.
- **Trust tiers** align with `docs/trust_model.md`: **T1 > T2 > T3**.

## 2. Company and role extraction (`backend/core/extraction.py`)

| Field | Source priority | Notes |
|-------|-----------------|-------|
| `company_hint` | Registrable domain label from URL; optional patterns in text (`Company:`, `at Company`) | May be `null`; never asserted as legal entity name |
| `title_hint` | First non-empty line of description; `Title:` / `Job:` prefixes | Truncated; may be `null` |
| `location_hint` | Regex for `City, ST` style fragments (best-effort) | Optional; low confidence |

**Future:** optional LLM extraction **must** output structured fields with **provenance** and cannot add uncited “facts.” Sprint 2 is **heuristic-only** in code.

## 3. Search validation (design)

### 3.1 Query packs

Built deterministically from:

- canonical URL (quoted fragment in one query),
- `company_hint`, `title_hint` (if present),
- registrable domain as site restriction query variant (provider permitting).

### 3.2 Evaluation

- **Hit:** result URL domain matches registrable domain or known board allowlist (config) with token overlap on title/company strings.
- **Miss:** zero results or only unrelated domains → `search_corroboration` strength `none` / `low`, never upgraded without T1/T2 path.

### 3.3 Rate limits and safety

- Bounded concurrent queries (e.g. max 3 packs).
- No execution of arbitrary URLs from results (links stored as strings only).

**Adapter:** real HTTP to search provider is **not** required in Sprint 2 tests — tests use fake hit lists; interface documented here for Sprint 3 wiring.

## 4. Source trust ranking and evidence collection

| Stage | Output type | Tier hint |
|-------|-------------|-----------|
| Same-registrable-domain HTTPS fetch of job page | `fetch_ok`, `domain_align` | T1 path |
| Board URL in results with structured match | `board_corroboration` | T2 |
| Generic web snippets | `search_corroboration` | T2/T3 depending on domain class |

**Ordering:** sort for presentation and downstream scoring as:

1. Tier rank: T1 > T2 > T3 > none  
2. Strength rank: high > medium > low > none  
3. Stable tie-break: signal `id` lexicographic  

Implemented in `backend/core/source_evidence.py` as `sort_evidence_by_trust`.

## 5. Fallback when sources fail

| Condition | System behavior |
|-----------|-----------------|
| URL blocked / SSRF deny | No fetch; search may still run on text hints; **warnings** include `FETCH_SKIPPED_POLICY` |
| HTTP 403/451 | Same as partial fail; do not fabricate page content |
| Search API error | Retry ≤ N with backoff (orchestrator policy); if still fail → `SEARCH_UNAVAILABLE` warning, empty hits |
| Paste-only (no URL) | Fetch skipped; search relies on text-derived hints only |

All fallbacks must remain **explainable** in evidence metadata.

## 6. Uncertainty

If T1-class signals are absent, evidence summary must make **low coverage** obvious (Sprint 3 maps to VERIFY / low confidence).

## Related documents

- `data_flow.md`
- `trust_model.md`
- `architecture.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 2 | Initial `source_validation.md` | Sprint 2 deliverable. |
