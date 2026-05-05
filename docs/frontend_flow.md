# JobSignal — Frontend flow (Sprint 3, minimal)

## 1. Goals

- **Judge-friendly:** one screen, obvious states, no framework ceremony.
- **Trust + uncertainty visible:** never hide VERIFY or weak evidence behind a green banner alone.
- **Not a job board / blacklist:** no employer shaming lists; language stays advisory.

## 2. Technology

Static **`index.html` + `app.js` + `styles.css`** under `frontend/`. Demo uses an in-file **mock verify** response; replace with `fetch("/v1/verify")` when the API exists.

## 3. UI states (client)

| State | Meaning | Visual |
|-------|---------|--------|
| **idle** | Waiting for user | Submit enabled, empty result panels hidden or dimmed. |
| **loading** | Verify in flight | Spinner / disabled submit; neutral banner “Checking sources…”. |
| **success** | Strong positive outcome | `verdict === APPLY` **and** confidence `high` (or `medium` without warnings) — calm positive panel **plus** per-signal list still shown. |
| **warning** | VERIFY / SKIP / APPLY with warnings / medium-low confidence | Amber panel; VERIFY copy prominent; reasons + warnings expanded by default. |
| **cache_hit** | **Overlay**, not mutually exclusive | Badge: “Recent shared check” + expiry if provided; can sit on **success** or **warning**. Implemented via `data-cache="hit"` alongside `data-ui-phase`. |
| **error** | Network/validation failure | Red panel; no fabricated verdict; suggest retry. |

**Orthogonality:** `data-ui-phase` ∈ `{idle,loading,success,warning,error}` and `data-cache` ∈ `{miss,hit}` so **cache_hit** is visible together with success or warning.

## 4. Uncertainty display

- Always render **verdict**, **confidence band**, **reasons** (≥2), **warnings**, and **signals** table (tier + strength + redacted details).
- For `VERIFY`, show explainer line: “We could not corroborate enough trusted sources—double-check on the employer site.”
- For `confidence: low` or non-empty warnings, show **amber** “Limited certainty” strip even if verdict were ever APPLY (guard prevents low+APPLY in MVP).

## 5. Cache hit display

- When `cache.hit === true`: show badge + `ttl_expires_at` (formatted local time) if present; tooltip “Same public job fingerprint as a recent check.”
- When miss: small muted text “Fresh check” (optional).

## 6. User flow (happy / unhappy)

1. User pastes URL and/or description → **idle** → submit.
2. **loading** → client calls API (mock for now).
3. Response maps to **success** or **warning** from `verdict` + `confidence` + `warnings.length`.
4. **cache_hit** badge from `cache.hit`.
5. On fetch exception → **error**, no verdict.

## 7. Accessibility / polish (minimal)

- Focus styles on button/input; `aria-live="polite"` on result region for screen readers.

## Related docs

- `decision_logic.md`, `scoring.md`, `architecture.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 3 | Initial static frontend + state model | Sprint 3 deliverable; no SPA build chain. |
