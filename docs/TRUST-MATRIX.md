# Trust matrix (MVP)

Canonical principles: `JOBSIGNAL-MASTER-PLAN.md` §3 and §6.

## Source tiers

| Tier | Meaning | Examples (illustrative) |
|------|---------|-------------------------|
| **T1** | Employer-controlled same-registrable-domain HTTPS evidence | Careers site on company registrable domain; job HTML or listing reachable without contradiction |
| **T2** | Reputable aggregator corroboration | Major job board listing matching fingerprint (provider set configurable) |
| **T3** | General web / search snippets | Search API snippets, secondary pages |

Tiers are **not** vendors; implementers map concrete providers into T1–T3 in `data_sources/`.

## Verdict gates (rule-first)

| Verdict | Minimum evidence |
|---------|------------------|
| **APPLY** | T1 or strong T2 agreement **and** no hard contradiction **and** fetch/parser not in failed state **and** confidence ≥ agreed threshold |
| **VERIFY** | Default when T1 missing, T2 weak, signals conflict, fetch partial, dates unknown, or duplicate/stale ambiguous |
| **SKIP** | Hard red patterns per policy (e.g., irreconcilable domain fraud heuristic) **or** user-facing policy to refuse (documented); never claim legal certainty |

## Forbidden

- `APPLY` from T3 alone.
- `APPLY` when normalization or fetch produced empty primary content without documented exception (there should be none in MVP).
- Certainty language in UI/API when confidence is low.

## Signal ids (initial set — names stable for API)

| id | Description |
|----|-------------|
| `url_canonical` | Normalized URL / redirect chain summary |
| `fetch_ok` | Successful bounded fetch of posting |
| `domain_align` | Registrable domain alignment vs careers |
| `search_corroboration` | Search pack hits and snippet agreement |
| `text_dup` | Hash match against recent cache entries |
| `staleness` | Explicit dates or unknown |

Each signal emits: `strength`, `tier_used`, `details_redacted` suitable for shared cache.
