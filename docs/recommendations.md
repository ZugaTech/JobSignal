# JobSignal — similar-job recommendations (Sprint 6)

**Status:** implemented (optional, honesty-first)  
**Not a job board:** no crawling, no rankings of “best jobs,” no guarantees.

## Behavior

- After the **primary** verify completes, the API may attach **`recommendations`** (max **3**, hard-capped).
- Each item is produced by **search → candidate URL → full `verify_job` again** with `skip_recommendations=True` (no nested similar-job expansion).
- **`confidence_band`** is **`HIGH`** only when the candidate verify returns **`confidence: high`**; **`MEDIUM`** for medium. Low-confidence candidates are **omitted** from the list.
- Ordering: **HIGH** rows first, then **MEDIUM** (stable tie-break by URL).

## Enabling

| Mechanism | Effect |
|-----------|--------|
| `RECOMMENDATIONS_ENABLED=1` | Default-on for requests that do not pass an override. |
| JSON / form `recommendations_enabled: true` | Request similar jobs for this call (if search is configured). |
| `recommendations_enabled: false` | Never attach recommendations for this call (overrides env default). |

Search must be configured:

- **`SERPER_API_KEY`** (preferred), or a legacy fallback alias (`SEARCH_API_KEY` / `SERPAPI_API_KEY`), and/or  
- **`JOBSIGNAL_SEARCH_FIXTURE_PATH`** pointing at a JSON file (CI / offline demos).

## Providers

- **`SEARCH_PROVIDER_ORDER`** — comma list, e.g. `serper,fixture` or `fixture`. Each provider is tried in order until enough URLs are collected (up to **`RECOMMENDATIONS_CANDIDATE_POOL`**, default 8).
- **Serper:** `https://google.serper.dev/search`, organic links only.
- **Fixture:** JSON with `urls` and optional `by_query_substring` map (see `data_sources/fixtures/search_stub.json`).

## Response shape (`report_schema_version` 1.2.0)

- **`recommendations`**: array of objects with `job_url`, `confidence_band`, `verdict`, `similarity_reasons`, `warnings`, `source_urls` (truncated).
- **`meta.recommendations_status`**: `ok` | `empty` | `unavailable`
- **`meta.recommendations_version`**: pipeline tag for clients

Shared **cache** rows for the primary job still **exclude** recommendation payloads (computed per response).

## Security

- Candidate URLs go through the same **normalize + optional live fetch** path as the primary job; SSRF protections apply to fetches when enabled.

## Related

- `docs/plan_vnext_multimodal_and_recommendations.md` — Sprint 6 definition  
- `backend/core/recommendations.py`
