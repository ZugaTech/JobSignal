# JobSignal — Trust score and scoring (Sprint 3)

## 1. Purpose

Turn **structured evidence** (`SignalEvidence` rows from Sprint 2 collectors) into:

1. A **transparent internal score** (for ordering and debugging—not shown as a single “truth number” to users).
2. A **verdict** (`APPLY` \| `VERIFY` \| `SKIP`) and **confidence band** (`high` \| `medium` \| `low`) via `backend/core/scoring.py`.

Scoring is **rule-first** and **reproducible** for the same inputs and `SCORER_VERSION`.

## 2. Internal score (0–100, capped)

Components (each bounded so the sum cannot silently “max out”):

| Component | Max pts | Rule (summary) |
|-----------|---------|----------------|
| **Tier presence** | 40 | T1 strong presence beats T2/T3; T3 alone caps contribution. |
| **Agreement** | 25 | Second independent signal at `medium`+ adds points; contradictions zero this bucket. |
| **Fetch health** | 20 | If URL provided: successful `fetch_ok` contributes; hard fetch failure caps APPLY elsewhere. |
| **Coverage** | 15 | Multiple distinct signal ids beyond URL-only. |

The raw sum is **clamped** to `[0, 100]`. The **verdict** is **not** `APPLY` whenever `raw_score >= threshold` alone—gates in `decision_logic.md` still apply (honesty guards).

## 3. Contradiction and penalty rules

- **Contradiction (example):** `fetch_ok` at `medium` or `high` while `domain_align` is `none` when a URL was provided → **VERIFY** (do not treat fetch as corroboration of employer control).
- **T3-only loudest path:** if best T1/T2 strengths are `none`/`low` but T3 is `high` → **VERIFY** (T3 cannot justify APPLY per trust model).
- **Borderline APPLY:** best T1 is only `medium` and there are at most two `medium+` rows → confidence band `low` → honesty guard forces **VERIFY** (see `decision_logic.md` §6.1).

## 4. Confidence band (output)

Derived from gates + coverage (not from LLM):

| Band | Typical meaning |
|------|-----------------|
| `high` | T1 `medium`+ with agreement; no contradiction; no hard warnings. |
| `medium` | Partial coverage, or T2-led path with some agreement, minor gaps. |
| `low` | Thin evidence, warnings, or disagreement between signals. |

**Honesty guard:** if the band is `low`, the verdict is **forced to `VERIFY`** even if the raw numeric components looked borderline—see `decision_logic.md`.

## 5. Versioning

- **`SCORER_VERSION`** lives in `backend/core/scoring.py` and must bump when thresholds or honesty guards change (cache keys per `docs/cache_design.md`).

## 6. Implementation

Reference: `backend/core/scoring.py` (single source of truth for thresholds).

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 3 | Initial scoring model + honesty guard | Sprint 3 deliverable; favors VERIFY over borderline APPLY. |
