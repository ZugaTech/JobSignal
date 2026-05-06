# JobSignal — primary job page fetch (Sprint 9)

**Module:** `backend/core/fetch_job_page.py`  
**Flag:** `ENABLE_JOB_FETCH` — when not `1` / `true`, no HTTP requests are made (default for CI and local runs without network).

## Behavior

- **GET** the normalized **canonical job URL** (and follow **3xx** manually).
- **SSRF:** Before each request, the hostname is resolved with `getaddrinfo`; **every** resolved address must pass `ipaddress` checks (reject private, loopback, link-local, multicast, reserved, unspecified; reject IPv4 shared space `100.64.0.0/10`). Literal IPs in the URL are checked the same way.
- **Limits:** `FETCH_MAX_BYTES` (streamed read), `FETCH_MAX_REDIRECTS`, httpx timeouts (15s total / 5s connect).
- **Signals:** Adds **`fetch_ok`** (T1) and **`domain_align`** (T1) by comparing naive registrable domains of the **initial** vs **final** URL after redirects.

## Orchestrator

- Live fetch runs **after** `url_canonical` / `input_text_only` and **before** fixture evidence.
- If fetch ran (`attempted`), **`fetch_ok`** and **`domain_align`** rows from **fixtures** are stripped so live results win.

## Cache

- `build_public_cache_key` includes `fetch:live` when `ENABLE_JOB_FETCH` is on so toggling fetch does not reuse stale cache rows.

## Tests

- `tests/test_fetch_job_page.py` — SSRF blocks, mocked HTTP via `httpx.MockTransport`, patched `socket.getaddrinfo` for stable public IPs.

## Related

- `docs/security.md` — threat model row for SSRF  
- `.env.example` — `ENABLE_JOB_FETCH`, `FETCH_MAX_*`
