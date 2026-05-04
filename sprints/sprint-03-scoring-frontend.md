# Sprint 3 — Scoring, decision output, and frontend flow

## Sprint goal

Connect signals to a **versioned rule engine** producing `APPLY` / `VERIFY` / `SKIP`, expose via API, and build UI that **surfaces uncertainty**.

## Scope

- Scoring engine: deterministic table-driven rules + version string.
- API route: `POST /v1/verify` (name flexible) returning frozen schema.
- Frontend: paste URL, show steps, render signals + warnings + cache badge.
- No hidden confidence: copy for VERIFY and low-confidence states.

## Tasks

1. Implement scorer from Sprint 1 trust matrix; unit tests per gate.
2. Wire orchestration: normalize → cache → collect → score → cache write.
3. Frontend states and error UX.
4. E2E smoke: at least one VERIFY and one error path.

## Done criteria

- Scorer version bumps invalidate cache keys as designed.
- UI shows per-signal rows and cache hit metadata when present.
- No `APPLY` in automated tests without T1/T2 fixture support.

## Risk

Overfitting fixtures → **Mitigation:** separate “demo golden” from “regression” sets.

## Fallback

If UI slips: ship API + minimal HTML debug page for demo with same schema.

## Manual checklist

- [ ] Demo script: 5-minute user test
- [ ] Copy review: no “guaranteed safe job” language
- [ ] Accessibility spot-check (labels, contrast)
