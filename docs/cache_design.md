# JobSignal — Cache design (Sprint 2)

## 1. Goals

- **Global reuse:** identical **public** normalized fingerprints share one entry across tenants.
- **Accuracy > speed:** serve stale-within-TTL cached evidence rather than refetching every time; refetch when TTL expired or source set changed.
- **Privacy:** **no** tenant-private fields in shared values (enforced in code + tests).

## 2. Public cache key

Components (string parts joined deterministically — see `backend/core/cache_key.py`):

| Part | Description |
|------|-------------|
| `normalization_version` | Bumps when URL/text normalization rules change. |
| `pipeline_version` | Bumps when orchestration or collector contracts change. |
| `source_set_version` | Bumps when **which** external sources or query packs change (not each API credential rotation). |
| `fingerprint` | `url_sha256` **xor** priority: if URL fingerprint present use it as primary; if only text, use `text_sha256`. If both present, **composite** = `u:{url_sha256}|t:{text_sha256}` (documented in code). |

**Never included:** `tenant_id`, user id, API keys, internal notes, raw PII blobs.

### Improvement note (documented)

Earlier sketches used URL hash **or** text hash only. **Composite key when both are present** avoids collisions where different URLs share identical pasted boilerplate and better matches “same job check” semantics. If product later prefers URL-only for dual input, bump `normalization_version` or `source_set_version` and document in sprint notes.

## 3. TTL rules

| Setting | Default | Range |
|---------|---------|-------|
| `CACHE_DEFAULT_TTL_DAYS` | **14** | **10–30** per product policy |

- `expires_at` = `created_at` + TTL, stored on entry (UTC ISO-8601).
- **Hit:** `now < expires_at` → return payload; attach `ttl_expires_at` to response metadata in later sprint.
- **Miss:** absent key OR expired OR key mismatch after version bump.

Optional later (not implemented in Sprint 2 code): soft TTL refresh in background.

## 4. Cross-tenant reuse rules

| Data | Shared? |
|------|---------|
| Normalized fingerprint, evidence signals, redacted fetch/search summaries | **Yes** |
| Tenant feature flags affecting **strictness** | **No** in payload; applied **after** read in orchestrator |
| Recruiter notes, ATS ids, user emails | **Never** |

## 5. Cache lookup flow

1. Compute `PublicCacheKey.materialize()`.
2. `GET(key)` from store.
3. If miss → `MISS`, run collectors.
4. If hit → parse payload; validate schema version inside payload; if unknown version treat as **MISS** (safe).

## 6. Cache write flow

1. Build in-memory `SharedCachePayload` from collector outputs.
2. Run `strip_tenant_fields()` and `redact_for_cache()` (length caps, strip disallowed keys).
3. `SET(key, payload, ttl_seconds)`.
4. If write fails (store down) → request still may return fresh evidence but logs warning; scorer must tolerate no cache.

## 7. Invalidation

| Trigger | Action |
|---------|--------|
| `pipeline_version` change | New keys; old entries become orphans until eviction. |
| `source_set_version` change | Same — new keys. |
| `normalization_version` change | Same. |
| Security incident for a URL | Operational `DELETE` by url hash prefix (runbook; Sprint 4). |

No implicit invalidation on tenant activity.

## 8. Fallback when sources fail

| Failure | Cache behavior | Evidence behavior |
|---------|----------------|---------------------|
| Fetch timeout / block | Do not cache **successful** fetch; may cache partial bundle if policy explicitly allows `partial_ok` — **MVP: do not write cache on fetch hard-fail** | Record `fetch_failed` signal with empty body |
| Search empty | Optional cache of “negative evidence” only if scorer needs it — **MVP: still allow cache write** if fetch succeeded and bundle is schema-valid; otherwise skip write | `search_empty` warning |
| All collectors failed | **No cache write** | Bundle marks `coverage: none` for scorer → expect VERIFY |

## 9. Related code

- `backend/core/cache_key.py`
- `backend/core/cache_payload.py`
- `backend/core/cache_store.py` (in-memory reference for tests)

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 2 | Initial `cache_design.md` + composite fingerprint when URL+text | Sprint 2 deliverable; reduce collision. |
