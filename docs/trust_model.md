# JobSignal — Trust model and source ranking (Sprint 1)

## 1. Principles

1. **No overclaiming:** copy and APIs avoid words like “guaranteed,” “certified safe,” or “this employer is legitimate.” Use “evidence suggests,” “we could not corroborate,” “consider verifying manually.”
2. **VERIFY is the honest default** when T1/T2 evidence is missing, weak, or conflicting.
3. **Rule engine > model narrative:** an LLM must not be the sole basis for `APPLY`.
4. **Evidence is structured:** every score influence maps to a `signal` with a stable `id` for UI and audits.

## 2. Source tiers (ranking)

| Tier | Name | Intended evidence |
|------|------|-------------------|
| **T1** | Employer-controlled | HTTPS resources on the **same registrable domain** as the employer’s stated careers or official site paths; successful bounded fetch where policy allows. |
| **T2** | Aggregator corroboration | Well-known job boards or structured listings that **match** the fingerprint (title/company/URL snippet overlap); used as secondary, not as sole proof of employer legitimacy. |
| **T3** | Open web / search snippets | Search API results, secondary pages; **supporting context only**. |

**Ranking rule:** T1 beats T2 beats T3 for **trust weight**. T3 **cannot** trigger `APPLY` without at least one **T1 or T2** signal at **medium** or **high** strength per policy tables implemented in Sprint 3.

## 3. Signal catalog (MVP ids)

Implementations must emit zero or more of these; ids are stable for API contracts.

| id | Typical tier | Role |
|----|--------------|------|
| `url_canonical` | — | Normalized URL fingerprint present |
| `fetch_ok` | T1 path | Page fetched within limits; status and size healthy |
| `domain_align` | T1 | Registrable domain alignment between posting and careers |
| `careers_path_match` | T1 | Job-like content or listing path corroboration (heuristic) |
| `board_corroboration` | T2 | Board listing agreement |
| `search_corroboration` | T2/T3 | Search pack agreement (tier depends on result domains) |
| `text_dup` | — | Duplicate or near-duplicate of cached public text |
| `staleness` | — | Posted date known vs unknown; listing age hints |

## 4. Verdict gates (rule-first)

### 4.1 APPLY

Required (all must hold):

- At least one **T1** signal at `strength >= medium` **or** **T2** at `strength >= high` with supportive agreement from another signal; exact thresholds **versioned** in scorer config (`scorer_version`).
- No **hard contradiction** (e.g., domain mismatch flag) unless explicitly overridden by stronger T1 (documented edge cases only).
- `fetch_ok` is not in `failed` state for the primary URL when URL was provided.

### 4.2 VERIFY (default under uncertainty)

Use **`VERIFY`** when any of the following hold:

- T1 missing or only `low` strength while T3 is loudest signal.
- Conflicting signals (e.g., fetch says OK but domain_align fails).
- Blocked fetch (403, CAPTCHA, timeout), partial HTML, or parser could not extract minimal fields.
- Posted date unknown **and** search offers no temporal corroboration.
- Likely duplicate (`text_dup`) without clear “same legitimate repost” story.
- Any internal **policy flag** “needs_human”.

### 4.3 SKIP

Use **`SKIP`** only for **documented policy** cases (e.g., irreconcilable spoofing heuristics, disallowed URL schemes, SSRF-blocked URL). **Never** assert criminal fraud; message patterns like “high risk—do not apply” with codes, not legal accusations.

## 5. Confidence

- **Derived** from signal coverage: number of independent tiers represented, agreement, and absence of warnings.
- **Not derived** from LLM token probability.
- **Bands:** map numeric `confidence` to `high` / `medium` / `low`; `low` **always** pairs with prominent VERIFY-style UX copy even if verdict is `APPLY` (rare; prefer tightening rules so low → VERIFY).

## 6. Cache interaction (trust-relevant)

- Cached entries store **redacted** `SignalEvidence` suitable for **all** tenants.
- If a tenant-specific flag would **relax** trust rules, that flag **must not** be read from shared cache; re-run scorer tenant overlay in memory after loading shared evidence (MVP may omit overlays; default strict).

## 7. LLM usage (optional)

Allowed: extract company/title tokens, cluster snippets **with signal references**.  
Forbidden: LLM-only `APPLY`; tool execution from untrusted job text; hidden chain-of-thought as user-facing “reason.”

## Related documents

- `architecture.md` — orchestration and schemas.
- `scope.md` — what MVP will and will not do.

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Added `docs/trust_model.md` | Dedicated trust reference for implementation and judging. |
