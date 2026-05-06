"""End-to-end verify orchestration (post–Sprint 4 vertical slice).

This is the smallest glue layer that connects:
validate -> normalize -> cache R/W -> fixtures evidence -> scoring -> report.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from backend.core.cache_key import build_public_cache_key
from backend.core.cache_payload import serialize_payload, strip_tenant_fields
from backend.core.cache_store import CacheStore, InMemoryCache, RedisCache
from backend.core.decision_schema import DecisionResponse, ReasonItem, Verdict, WarningItem
from backend.core.env import EnvConfig
from backend.core.fetch_job_page import job_fetch_enabled, run_job_page_fetch
from backend.core.fixtures import load_fixture_evidence
from backend.core.image_ingest import (
    IMAGE_INGEST_VERSION,
    ExtractedVisionFields,
    coalesce_url,
    ingest_job_image,
    merge_description_with_extraction,
)
from backend.core.inputs import InputValidationError, validate_verify_inputs
from backend.core.llm_fireworks import build_llm_signals
from backend.core.normalization import NormalizationResult, normalize_job_input
from backend.core.report import build_public_report
from backend.core.scoring import SCORER_VERSION, decide_from_signals

_MEM_CACHE = InMemoryCache()
_REDIS_CACHE: CacheStore | None = None


def _get_cache(cfg: EnvConfig) -> CacheStore:
    global _REDIS_CACHE  # noqa: PLW0603 - simple module cache
    if cfg.cache_url:
        if _REDIS_CACHE is None:
            _REDIS_CACHE = RedisCache(cfg.cache_url)
        return _REDIS_CACHE
    return _MEM_CACHE


def _ttl_seconds(ttl_days: int) -> int:
    return int(ttl_days) * 24 * 60 * 60


def _ingestion_payload(
    has_image: bool,
    merged_fields: Optional[ExtractedVisionFields],
    detected_mime: Optional[str],
    *,
    source: str,
) -> Optional[Dict[str, Any]]:
    if not has_image:
        return None
    return {
        "status": "ok",
        "image_ingest_version": IMAGE_INGEST_VERSION,
        "extraction_confidence": (merged_fields.extraction_confidence if merged_fields else None),
        "detected_mime": detected_mime,
        "source": source,
    }


def _insufficient_image_report(
    *,
    cfg: EnvConfig,
    warnings: List[Dict[str, str]],
) -> Dict[str, Any]:
    decision: DecisionResponse = {
        "verdict": Verdict.VERIFY,
        "confidence": "low",
        "reasons": [
            ReasonItem(
                code="IMAGE_INSUFFICIENT",
                message=(
                    "Screenshot doesn't contain enough readable job details—please paste the job URL "
                    "(preferred) or paste the full job text."
                ),
            ),
            ReasonItem(
                code="NEXT_STEP",
                message="A direct posting URL or full pasted text enables stronger verification than a blurry screenshot alone.",
            ),
        ],
        "warnings": [WarningItem(code=str(w.get("code", "INGEST")), message=str(w.get("message", ""))) for w in warnings[:12]],
        "signals": [],
    }
    ingestion = {
        "status": "insufficient",
        "image_ingest_version": IMAGE_INGEST_VERSION,
        "message": (
            "Screenshot doesn't contain enough readable job details—please paste the job URL "
            "(preferred) or paste the full job text."
        ),
    }
    return build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        meta={"pipeline_version": cfg.source_pipeline_version, "scorer_version": SCORER_VERSION},
        ingestion=ingestion,
    )


def _maybe_attach_recommendations(
    report: Dict[str, Any],
    *,
    norm: NormalizationResult,
    merged_fields: Optional[ExtractedVisionFields],
    skip_recommendations: bool,
    recommendations_enabled: Optional[bool],
) -> None:
    if skip_recommendations:
        return
    from backend.core.recommendations import extend_report_with_recommendations

    def verify_candidate(candidate_url: str) -> Dict[str, Any]:
        return verify_job(
            candidate_url,
            None,
            skip_recommendations=True,
            recommendations_enabled=False,
            image_bytes=None,
            image_media_type=None,
        )

    extend_report_with_recommendations(
        report,
        norm,
        merged_fields,
        user_requested=recommendations_enabled,
        verify_candidate=verify_candidate,
    )


def verify_job(
    job_url: Optional[str],
    job_description: Optional[str],
    *,
    image_bytes: Optional[bytes] = None,
    image_media_type: Optional[str] = None,
    skip_recommendations: bool = False,
    recommendations_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    cfg = EnvConfig.load(strict=False)
    has_image = image_bytes is not None

    try:
        url, text = validate_verify_inputs(job_url, job_description, has_image=has_image)
    except InputValidationError as e:
        raise ValueError(f"{e.code}: {e}") from e

    user_supplied_url_or_text = bool(url or text)
    ingest_warnings: List[Dict[str, str]] = []
    merged_fields: Optional[ExtractedVisionFields] = None
    detected_mime: Optional[str] = None

    if has_image:
        assert image_bytes is not None
        ing = ingest_job_image(
            image_bytes,
            declared_mime=image_media_type,
            user_supplied_url_or_text=user_supplied_url_or_text,
        )
        ingest_warnings.extend(ing.warnings)
        detected_mime = ing.detected_mime
        if ing.status == "insufficient" and not user_supplied_url_or_text:
            return _insufficient_image_report(cfg=cfg, warnings=ingest_warnings)
        merged_fields = ing.fields

    effective_url = coalesce_url(url, merged_fields)
    effective_text = merge_description_with_extraction(text, merged_fields)

    if effective_url is None and (effective_text is None or not effective_text.strip()):
        return _insufficient_image_report(cfg=cfg, warnings=ingest_warnings)

    norm = normalize_job_input(effective_url, effective_text)
    image_sha = hashlib.sha256(image_bytes).hexdigest() if has_image and image_bytes else None
    fetch_profile = "live" if job_fetch_enabled() else "off"
    cache_key = build_public_cache_key(
        norm,
        pipeline_version=cfg.source_pipeline_version,
        source_set_version="fixtures-v1",
        image_bytes_sha256=image_sha,
        image_ingest_version=IMAGE_INGEST_VERSION if has_image else None,
        fetch_profile=fetch_profile,
    )

    steps = []
    steps.append({"id": "normalize", "label": "Normalized input"})
    
    cache = _get_cache(cfg)
    cached = cache.get(cache_key.materialized)
    if cached:
        steps.append({"id": "cache", "label": "Cache hit", "status": "ok"})
        payload = json.loads(cached)
        signals = payload.get("signals", [])
        decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))
        report = build_public_report(
            decision,
            cache={"hit": True, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
            meta={
                "pipeline_version": cfg.source_pipeline_version, 
                "scorer_version": SCORER_VERSION,
                "pipeline_steps": steps
            },
            ingestion=_ingestion_payload(has_image, merged_fields, detected_mime, source="cache"),
        )
        _maybe_attach_recommendations(
            report,
            norm=norm,
            merged_fields=merged_fields,
            skip_recommendations=skip_recommendations,
            recommendations_enabled=recommendations_enabled,
        )
        return report

    steps.append({"id": "cache", "label": "Cache miss", "status": "miss"})
    signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = list(ingest_warnings)

    if norm.canonical_url:
        signals.append(
            {
                "id": "url_canonical",
                "label": "Posting URL",
                "tier": "none",
                "strength": "low",
                "details": norm.canonical_url[:256],
            }
        )
    elif (norm.description_text or "").strip():
        signals.append(
            {
                "id": "input_text_only",
                "label": "What we checked",
                "tier": "none",
                "strength": "low",
                "details": (
                    "You shared pasted text only (no job link). We can read the description, but we can’t yet "
                    "cross-check the employer careers page or listing history—add the URL for a stronger result."
                ),
            }
        )

    live_fetch_attempted = False
    if norm.canonical_url and job_fetch_enabled():
        steps.append({"id": "fetch", "label": "Live page fetch"})
        fx = run_job_page_fetch(norm.canonical_url, cfg)
        live_fetch_attempted = fx.attempted
        signals.extend(fx.signals)
        warnings.extend(fx.warnings)

    steps.append({"id": "evidence", "label": "Evidence collection"})
    fixtures_path = os.environ.get("JOBSIGNAL_FIXTURES_PATH", "data_sources/fixtures/verify_fixtures.json")
    fe = load_fixture_evidence(
        fixtures_path=fixtures_path,
        canonical_url_sha256=norm.canonical_url_sha256,
        description_full_sha256=norm.description_full_sha256,
    )
    if fe:
        fsigs = fe.signals
        if live_fetch_attempted:
            fsigs = [s for s in fsigs if str(s.get("id")) not in ("fetch_ok", "domain_align")]
        signals.extend(fsigs)
        warnings.extend(fe.warnings)
    else:
        warnings.append(
            {
                "code": "FIXTURES_MISS",
                "message": "No fixture evidence matched this input; result will likely VERIFY until live adapters are wired.",
            }
        )

    steps.append({"id": "llm", "label": "AI intelligence (T3)"})
    llm = build_llm_signals(job_text=norm.description_text or "")
    if llm.signals:
        signals.extend(llm.signals)
    if llm.warnings:
        warnings.extend(llm.warnings)

    steps.append({"id": "score", "label": "Scoring engine"})
    decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))
    report = build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
        meta={
            "pipeline_version": cfg.source_pipeline_version, 
            "scorer_version": SCORER_VERSION,
            "pipeline_steps": steps
        },
        ingestion=_ingestion_payload(has_image, merged_fields, detected_mime, source="live"),
    )
    _maybe_attach_recommendations(
        report,
        norm=norm,
        merged_fields=merged_fields,
        skip_recommendations=skip_recommendations,
        recommendations_enabled=recommendations_enabled,
    )

    shared_payload = strip_tenant_fields(
        {
            "schema_version": "1",
            "pipeline_version": cfg.source_pipeline_version,
            "source_set_version": "fixtures-v1",
            "normalization_version": norm.normalization_version,
            "signals": signals,
            "warnings": [w["code"] for w in warnings],
            "coverage": "partial" if signals else "none",
        }
    )
    cache.set(cache_key.materialized, serialize_payload(shared_payload), ttl_seconds=_ttl_seconds(cfg.cache_ttl_days))
    return report
