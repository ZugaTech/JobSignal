# JobSignal — Decision logic (Sprint 3)

## 1. Principles

- **Honesty over certainty:** prefer **`VERIFY`** to a weak **`APPLY`**.
- **No single source:** APPLY requires corroboration per gates below.
- **No invented evidence:** scorer only interprets provided signals; missing data → VERIFY with explicit reasons.

## 2. Input / output

- **Input:** ordered `signals: SignalEvidence[]` (use `sort_evidence_by_trust` before scoring), flags:
  - `url_provided: bool`
  - optional `policy_skip: (code, message)` → immediate **SKIP**
- **Output:** `DecisionResponse` (`decision_schema.py`): `verdict`, `confidence` band, `reasons` (**≥ 2** items), `warnings`, `signals` (echo sorted input).

## 3. SKIP (hard policy)

Evaluated **first**. If `policy_skip` is set (e.g. SSRF deny, disallowed scheme):

- `verdict = SKIP`
- `confidence = low`
- `reasons` include policy entries + coverage explanation (still ≥ 2 items)

## 4. VERIFY gates (before APPLY)

Return **VERIFY** if any holds:

1. **Contradiction:** URL provided, `fetch_ok` strength in `{high, medium}`, and best `domain_align` strength is `none`.
2. **Fetch required but missing/failed:** URL provided and no `fetch_ok` signal or `fetch_ok.strength == none`.
3. **T3-only path:** best T1/T2 strengths ∈ `{none, low}` and strongest overall narrative is T3-heavy (best T3 `high` without qualifying T1/T2).
4. **Insufficient corroboration for T2-high path:** best T2 is `high` but no second `medium`+ signal from any tier.
5. **Insufficient T1 path:** best T1 is below `medium` **and** best T2 is below `high`.
6. **Honesty guard:** computed confidence band is `low` → **VERIFY** even if numeric components suggested APPLY (documented improvement over “score-only APPLY”).

## 5. APPLY (all required)

1. No SKIP.
2. No VERIFY gate triggered (after honesty guard: evaluate APPLY candidate **before** forcing low-confidence VERIFY; see implementation order in `scoring.py` comments).
3. **Path A — T1-led:** best T1 strength ∈ `{high, medium}` **and** at least one other signal with strength `medium`+ (any tier).
4. **Path B — T2-led:** best T2 is `high` **and** at least one other signal with strength `medium`+ (any tier).
5. Contradiction check passes.

> **Implementation note:** the code evaluates APPLY candidates, then applies the **low-confidence → VERIFY** override last so borderline numeric APPLY does not leak past weak evidence.

## 6. Confidence mapping (summary)

| Verdict | Confidence (typical) |
|---------|----------------------|
| SKIP | `low` |
| VERIFY | `low`–`medium` (MVP: VERIFY is rarely paired with `high` confidence; see `scoring.py`) |
| APPLY | `high` or `medium` only — **never** `low` (`low` forces VERIFY via honesty guard) |

### 6.1 Borderline APPLY (Sprint 3 improvement)

If `verdict` would be **`APPLY`** but the best T1 strength is only **`medium`** and there are **at most two** `medium+` supporting rows, the confidence band is set to **`low`**, triggering the **honesty guard** that **downgrades to `VERIFY`**. This prevents a “green APPLY” on thin employer-controlled evidence. Documented in `scoring.md` and implemented in `backend/core/scoring.py` (`_confidence_band`).

## 7. Low-confidence warnings

When confidence is `medium` or `low`, the response **must** include warning codes such as:

- `CONFIDENCE_MEDIUM` / `CONFIDENCE_LOW`
- `THIN_T1_T2_COVERAGE`
- `CONTRADICTION_RESOLVED_TO_VERIFY` (if applicable)

UI copy guidance: `docs/frontend_flow.md`.

## 8. Report schema

Serialized JSON for API/UI: `VerifyResponse` plus optional `cache` and `meta` (`report.py` helper). Stable field names; no tenant-private fields.

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 3 | Added low-confidence VERIFY override | Stops borderline APPLY on thin evidence. |
