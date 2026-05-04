# Sprint 2 — Data ingestion, search validation, and cache system

## Sprint goal

Implement **read-only data collection** (fetch + search adapters) and **cache read/write** with normalization and tenant-safe payloads—or fully specify and stub with contract tests if implementation starts this sprint.

## Scope

- Normalization module spec + tests (implementation when coding begins).
- HTTP fetch path with SSRF controls **as specified** in master plan.
- Search adapter contract: query shapes, rate limits, empty-result behavior.
- Cache: key derivation, TTL, read path, write path, strip tenant fields (test enforced).

## Tasks

1. Implement or specify normalization golden tests.
2. Fetch provider with timeout, redirect limit, size cap.
3. Search provider with parallel query budget.
4. Cache layer: get/set, serialization schema for cached row.
5. Observability: structured logs per signal (no secrets).

## Done criteria

- Contract tests pass for normalization and cache key stability.
- Integration test: cache miss → populate → hit (mocked external IO).
- Automated assertion: **no tenant-private fields** in serialized cache blob.

## Risk

External API flake → **Mitigation:** retries with jitter, circuit breaker, degrade to VERIFY.

## Fallback

If search API not ready: mock adapter + interface tests only; block `APPLY` in config until real adapter lands.

## Manual checklist

- [ ] Try three real URLs locally (recorded mocks for CI)
- [ ] Verify robots.txt / ToS respected for fetch depth
- [ ] Load test: single-tenant burst stays within rate limits
