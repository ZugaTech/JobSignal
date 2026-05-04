# Sprint 2 — Notes and completion record

**Status:** documentation + core ingestion/cache modules + tests (no frontend, no verdict polish, no deploy hardening).  
**Date:** 2026-05-04.

## Deliverables

| Item | Location |
|------|----------|
| Precise data flow | `docs/data_flow.md` |
| Cache design (TTL, cross-tenant, invalidation, fallbacks) | `docs/cache_design.md` |
| Source validation, extraction, search design | `docs/source_validation.md` |
| Normalization | `backend/core/normalization.py` + `tests/test_normalization.py` |
| Entity extraction (heuristic) | `backend/core/extraction.py` + `tests/test_extraction.py` |
| Public cache key | `backend/core/cache_key.py` + `tests/test_cache_key.py` |
| Shared payload + tenant strip + JSON guard | `backend/core/cache_payload.py` + `tests/test_cache_store.py` |
| In-memory cache (TTL) | `backend/core/cache_store.py` |
| Evidence ordering | `backend/core/source_evidence.py` + `tests/test_source_ordering.py` |
| Test runner config | `pyproject.toml` |

## Improvement documented (cache strategy)

**Composite fingerprint when both URL and pasted text are present** (`u:<sha>|t:<sha>`) replaces “URL OR text hash only” to reduce ambiguity when the same boilerplate appears under different URLs. Documented in `docs/cache_design.md` change log. Rollback: bump `source_set_version` or `normalization_version` and treat old keys as misses.

## Out of scope (honored)

- HTTP fetch / search HTTP adapters to real providers (interfaces deferred; tests are local).
- Final verdict / confidence mapping (Sprint 3).
- Production deployment / SSRF implementation in middleware (documented only at architecture level).

## Done criteria (Sprint 2 prompt)

- [x] Normalization defined and tested  
- [x] Cache key stability + TTL hit/miss tested  
- [x] Source trust **ordering** tested  
- [x] Tenant fields rejected in serialized cache path (test)  
- [x] Data flow / cache / source docs updated  

## Manual follow-ups

- [ ] Wire real `SearchAdapter` with recorded fixtures  
- [ ] Add PSL-aware domain parsing (would bump `NORMALIZATION_VERSION`)  

## Commands

```bash
python -m pytest
```
