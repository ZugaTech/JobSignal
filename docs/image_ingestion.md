# JobSignal — image / screenshot ingestion (Sprint 5)

**Status:** implemented (Sprint 5)  
**Authority:** aligns with `docs/trust_model.md`, `docs/security.md`, and `.cursor/rules/JOBSIGNAL-RULES.mdc`.

## Purpose

Allow an optional **screenshot** of a job posting to seed verification when text/URL are missing or thin. Extraction is **untrusted**: it feeds the same normalize → evidence → score path as pasted text, with **honest blocking** when the image is unreadable or vision output fails validation.

## Supported formats

- **PNG**, **JPEG**, **WebP** (magic-byte verified; declared `Content-Type` must not contradict content).
- Default max size: **5 MiB** raw bytes (`IMAGE_MAX_BYTES`, clamped in code).

## API

- **`POST /v1/verify`**
  - **JSON** (unchanged): `job_url`, `job_description`.
  - **Multipart**: form fields `job_url`, `job_description` (optional strings) + file field **`job_image`**.
- Responses use `report_schema_version` **1.1.0** and may include an **`ingestion`** object:
  - `status`: `ok` | `insufficient`
  - `image_ingest_version`: pipeline tag for cache/docs
  - `extraction_confidence`: `high` | `medium` | `low` | `null` (when vision did not produce fields)
  - `detected_mime`: e.g. `image/png` (when an image was processed)
  - `message`: human-readable guidance when `insufficient`

## Vision provider (Fireworks)

- **Feature flag:** `ENABLE_IMAGE_VERIFY=1`
- **Auth:** `FIREWORKS_API_KEY` (or `LLM_API_KEY`)
- **Model:** `FIREWORKS_VISION_MODEL` (fallback: `FIREWORKS_MODEL`, then `accounts/fireworks/models/kimi-k2p6` per [Fireworks vision guide](https://docs.fireworks.ai/guides/querying-vision-language-models))
- **Timeout:** `FIREWORKS_TIMEOUT_S` (default 45s for vision calls)

When disabled or misconfigured, screenshot-only requests return **`ingestion.status: insufficient`** and a clear ask for URL/text (no fabricated job facts).

## Threats and mitigations

| Risk | Mitigation |
|------|------------|
| Huge uploads / DoS | Hard cap on bytes; reject empty payloads |
| MIME spoofing | Magic-byte check; reject declared vs detected mismatch |
| Model hallucination | Strict JSON schema; low confidence + missing substance → block image-only path; LLM never sole source for APPLY |
| Secret exfiltration via image | No image bytes in shared cache payload; only derived public normalization hashes + optional image SHA in **cache key** |
| PII in screenshots | Treat like user-supplied text; do not add tenant fields to shared cache rows |

## Retention

- Images are read in memory per request; **no default disk persistence**. Operate with ephemeral storage only unless an integration explicitly documents retention.

## Failure modes

- **Vision disabled / no key:** screenshot-only → insufficient + warning codes `VISION_DISABLED` / `VISION_NO_KEY`.
- **Provider error / non-JSON:** warnings `VISION_ERROR` / `VISION_MALFORMED`; screenshot-only → insufficient.
- **Schema mismatch:** `VISION_SCHEMA`; screenshot-only → insufficient.
- **Low confidence or thin extraction (image-only):** `IMAGE_INSUFFICIENT`; user asked for URL or full text.

## Cache keys

When an image is present, the public cache key includes `img:<sha256>` so different screenshots do not collide for the same extracted URL/text fingerprint.

## Testing

- Deterministic tests **monkeypatch** `extract_job_fields_from_image_vision` (no live network).
- Minimal valid PNG fixtures in `tests/test_image_ingest.py` and `tests/test_verify_image_flow.py`.
