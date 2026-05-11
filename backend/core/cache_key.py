"""Public cache key materialization (no tenant identity)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.normalization import NormalizationResult


@dataclass(frozen=True, slots=True)
class PublicCacheKey:
    """Deterministic key inputs for a shared cache row."""

    materialized: str
    fingerprint_preview: str


def build_public_cache_key(
    norm: NormalizationResult,
    pipeline_version: str,
    source_set_version: str,
    *,
    image_bytes_sha256: str | None = None,
    image_ingest_version: str | None = None,
    fetch_profile: str | None = None,
    verify_depth: str | None = None,
) -> PublicCacheKey:
    """Build stable cache key string.

    Fingerprint: if both URL and text present, composite ``u:<sha>|t:<sha>``.
    If only one side present, use that hash alone. If neither, ``empty`` (caller
    should reject request earlier).
    """

    u = norm.canonical_url_sha256
    t = norm.description_full_sha256
    if u and t:
        fingerprint = f"u:{u}|t:{t}"
    elif u:
        fingerprint = f"u:{u}"
    elif t:
        fingerprint = f"t:{t}"
    else:
        fingerprint = "empty"

    parts = [
        f"nv:{norm.normalization_version}",
        f"pv:{pipeline_version}",
        f"sv:{source_set_version}",
        f"fp:{fingerprint}",
    ]
    if image_bytes_sha256:
        parts.append(f"img:{image_bytes_sha256}")
    if image_ingest_version:
        parts.append(f"imgv:{image_ingest_version}")
    if fetch_profile and fetch_profile != "off":
        parts.append(f"fetch:{fetch_profile}")
    if verify_depth and str(verify_depth).strip().lower() == "quick":
        parts.append("vd:quick")
    materialized = "|".join(parts)
    preview = fingerprint[:16] + ("" if len(fingerprint) <= 16 else "…")
    return PublicCacheKey(materialized=materialized, fingerprint_preview=preview)
