# Scope addendum — 2026-05-06 (Sprint 5)

**Parent:** `docs/final_scope.md` (Sprint 4 freeze)

## Change

**In scope (added):** optional **screenshot / image** input for verification, with:

- Multipart upload on `POST /v1/verify` (`job_image`)
- Optional Fireworks **vision** extraction behind `ENABLE_IMAGE_VERIFY`
- **Insufficient-data UX:** when the image cannot support verification alone, the API returns an explicit instruction to paste the **job URL** (preferred) or **full job text** — no fabricated completeness

## Non-goals (unchanged)

- Job board, mass crawler, public blacklist, legal fraud claims (`docs/final_scope.md`)

## Documentation

- `docs/image_ingestion.md` — operational detail
- `docs/plan_vnext_multimodal_and_recommendations.md` — Sprint 5 definition

## Report schema

- `report_schema_version` bumped to **1.1.0**; optional `ingestion` block documented in `docs/image_ingestion.md`.
