"""End-to-end verify orchestration (post–Sprint 4 vertical slice).

This is the smallest glue layer that connects:
validate -> normalize -> cache R/W -> live evidence -> scoring -> report.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.cache_key import build_public_cache_key
from backend.core.cache_payload import serialize_payload, strip_tenant_fields
from backend.core.cache_store import CacheStore, InMemoryCache, RedisCache
from backend.core.decision_schema import DecisionResponse, ReasonItem, Verdict, WarningItem
from backend.core.env import EnvConfig
from backend.core.fetch_job_page import job_fetch_enabled, run_job_page_fetch
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
from backend.core.structured_log import log_stage
from backend.evidence.company_reviews import get_company_reviews, extract_company_name_hardened
from backend.core.coordinator import EvidenceCoordinator
from backend.core.llm_safe import call_llm_safe
from backend.core.response_contract import (
    build_preflight_skip_report,
    build_preflight_verify_job_uncertain_report,
)

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
                    "The screenshot does not contain enough readable job details. Please paste the job URL "
                    "(preferred) or the full job text instead."
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
            "The screenshot does not contain enough readable job details. Please paste the job URL "
            "(preferred) or the full job text instead."
        ),
    }
    return build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": "n/a"},
        meta={"pipeline_version": cfg.source_pipeline_version, "scorer_version": SCORER_VERSION},
        ingestion=ingestion,
    )

async def _maybe_attach_recommendations(
    report: Dict[str, Any],
    norm: NormalizationResult,
    merged_fields: Optional[ExtractedVisionFields],
    skip_recommendations: bool,
    include_similar_jobs: Optional[bool],
    coordinator: Optional[EvidenceCoordinator] = None,
) -> None:
    if skip_recommendations:
        return
    from backend.core.recommendations import extend_report_with_recommendations

    async def verify_candidate(candidate_url: str) -> Dict[str, Any]:
        return await verify_job(
            candidate_url,
            None,
            skip_recommendations=True,
            include_similar_jobs=False,
            image_bytes=None,
            image_media_type=None,
        )

    await extend_report_with_recommendations(
        report,
        norm,
        merged_fields,
        user_requested=include_similar_jobs,
        verify_candidate=verify_candidate,
        coordinator=coordinator,
    )


async def verify_job(
    job_url: Optional[str],
    job_description: Optional[str],
    *,
    image_bytes: Optional[bytes] = None,
    image_media_type: Optional[str] = None,
    skip_recommendations: bool = False,
    include_similar_jobs: Optional[bool] = None,
    request_id: str = "unknown",
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    cfg = EnvConfig.load(strict=False)
    data_freshness = datetime.now(timezone.utc).isoformat()
    has_image = image_bytes is not None
    log_stage(request_id=request_id, stage="input_received", duration_ms=0.0)

    try:
        url, text = validate_verify_inputs(job_url, job_description, has_image=has_image)
    except InputValidationError as e:
        raise ValueError(f"{e.code}: {e}") from e

    if url:
        from backend.core.url_preflight import evaluate_job_url_preflight

        pf = await evaluate_job_url_preflight(url, text, cfg=cfg)
        if pf.outcome == "skip":
            return build_preflight_skip_report(reason=pf.plain_reason, request_id=request_id)
        if pf.outcome == "verify_weak":
            return build_preflight_verify_job_uncertain_report(reason=pf.plain_reason, request_id=request_id)

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
        source_set_version=f"pipeline-{cfg.source_pipeline_version}",
        image_bytes_sha256=image_sha,
        image_ingest_version=IMAGE_INGEST_VERSION if has_image else None,
        fetch_profile=fetch_profile,
    )

    steps = []
    steps.append({"id": "normalize", "label": "Normalized input"})
    
    api_key = os.environ.get("SERPER_API_KEY") or os.environ.get("SEARCH_API_KEY") or ""
    coordinator = EvidenceCoordinator(api_key=api_key)
    if include_similar_jobs:
        coordinator.set_max_calls(6) # Reserve 2 for recommendations
    
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
            data_freshness=data_freshness,
        )
        log_stage(request_id=request_id, stage="cache_hit", duration_ms=(time.perf_counter() - t0) * 1000)
        await _maybe_attach_recommendations(
            report,
            norm=norm,
            merged_fields=merged_fields,
            skip_recommendations=skip_recommendations,
            include_similar_jobs=include_similar_jobs,
            coordinator=coordinator,
        )
        if include_similar_jobs:
            report["similar_jobs"] = list(report.get("recommendations") or [])
            meta_m = dict(report.get("meta") or {})
            meta_m["similar_jobs_requested"] = True
            report["meta"] = meta_m
        else:
            report["similar_jobs"] = None
        log_stage(
            request_id=request_id,
            stage="report_returned",
            duration_ms=(time.perf_counter() - t0) * 1000,
            verdict=str(report.get("verdict", "")),
        )
        return report

    steps.append({"id": "cache", "label": "Cache miss", "status": "miss"})
    log_stage(request_id=request_id, stage="cache_miss", duration_ms=(time.perf_counter() - t0) * 1000)
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
                    "You shared pasted text only (no job link). We can read the description, but we cannot yet "
                    "cross-check the employer careers page or listing history; add the URL for a stronger result."
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
    
    from backend.core.extraction import extract_entities
    from backend.core.evidence import build_evidence_bundle, _collect_serper_queries
    
    # Extract structural hints from the raw inputs
    ext = extract_entities(norm)
    
    # SPRINT 9-B: Harden company name extraction
    hardened_company = extract_company_name_hardened(
        norm.canonical_url, norm.description_text, request_id=request_id
    )
    
    # Run evidence and reviews in parallel
    company = ext.company_hint or ""
    title = ext.title_hint or ""
    base_query = f"{company} {title}".strip() or (norm.canonical_url or "")
    
    evidence_task = asyncio.create_task(_collect_serper_queries(coordinator, base_query, company, title))
    review_task = asyncio.create_task(get_company_reviews(coordinator, hardened_company, request_id=request_id))
    
    serp_results = await evidence_task
    
    # Build the concrete evidence bundle
    bundle = build_evidence_bundle(norm, ext, serp_results)
    signals.extend(bundle.signals)
    warnings.extend(bundle.warnings)
    log_stage(request_id=request_id, stage="evidence_gathered", duration_ms=(time.perf_counter() - t0) * 1000)
    
    # Finalize coordinator limit for recommendations if needed
    if include_similar_jobs:
        coordinator.set_max_calls(8) # Allow remaining calls for recommendations
    
    # await coordinator.close() # Move to the end of verify_job

    steps.append({"id": "llm", "label": "AI intelligence (T3)"})
    llm = build_llm_signals(job_text=norm.description_text or "")
    if llm.signals:
        signals.extend(llm.signals)
    if llm.warnings:
        warnings.extend(llm.warnings)

    steps.append({"id": "score", "label": "Scoring engine"})
    decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))
    
    # Await reviews
    try:
        review_summary = await review_task
    except Exception:
        review_summary = None

    # Verdict briefing via Fireworks (safe wrapper)
    from backend.core.llm_fireworks import _get

    verdict_raw = decision["verdict"]
    verdict_val = verdict_raw.value if hasattr(verdict_raw, "value") else str(verdict_raw)
    reasons_list = decision.get("reasons") or []
    primary_reason = (
        str(reasons_list[0].get("message", "")).strip().rstrip(".")
        if reasons_list
        else "Manual verification is recommended."
    )
    signal_count = len(signals)
    conf_band = str(decision.get("confidence") or "low").lower()
    fallback_txt = (
        f"Based on {signal_count} signals checked, this posting received a {verdict_val} verdict "
        f"with {conf_band} confidence. {primary_reason}."
    )

    api_key_llm = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    llm_enabled = os.environ.get("ENABLE_LLM_SIGNALS", "1") != "0"
    if api_key_llm and llm_enabled:
        llm_summary = await call_llm_safe(
            messages=[
                {
                    "role": "system",
                    "content": "You are JobSignal, a verification assistant. Write a 2-sentence briefing for a job seeker. No jargon. No headers. Output ONLY the briefing text.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Decision: {decision['verdict'].value}, Confidence: {decision['confidence']}\n"
                        f"Signals: {', '.join([s.get('id', '') for s in signals if s.get('strength') in ('high', 'medium')])}\n"
                        f"Reputation: {review_summary.plain_summary if review_summary else 'N/A'}"
                    ),
                },
            ],
            fallback=fallback_txt,
            request_id=request_id,
            model=_get("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2-instruct"),
            temperature=0.3,
            max_tokens=150,
            timeout=10.0,
        )
    else:
        llm_summary = fallback_txt

    log_stage(request_id=request_id, stage="score_computed", duration_ms=(time.perf_counter() - t0) * 1000, verdict=decision["verdict"].value)
    report = build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
        meta={
            "pipeline_version": cfg.source_pipeline_version, 
            "scorer_version": SCORER_VERSION,
            "pipeline_steps": steps
        },
        ingestion=_ingestion_payload(has_image, merged_fields, detected_mime, source="live"),
        evidence_sources=getattr(bundle, "evidence_sources", None),
        data_freshness=data_freshness,
        review_summary=asdict(review_summary) if review_summary else None,
    )
    report["llm_summary"] = llm_summary
    await _maybe_attach_recommendations(
        report,
        norm=norm,
        merged_fields=merged_fields,
        skip_recommendations=skip_recommendations,
        include_similar_jobs=include_similar_jobs,
        coordinator=coordinator,
    )
    if include_similar_jobs:
        report["similar_jobs"] = list(report.get("recommendations") or [])
        meta_m = dict(report.get("meta") or {})
        meta_m["similar_jobs_requested"] = True
        report["meta"] = meta_m
    else:
        report["similar_jobs"] = None

    shared_payload = strip_tenant_fields(
        {
            "schema_version": "1",
            "pipeline_version": cfg.source_pipeline_version,
            "source_set_version": "live-v1",
            "normalization_version": norm.normalization_version,
            "signals": signals,
            "warnings": [w["code"] for w in warnings],
            "coverage": "partial" if signals else "none",
        }
    )
    cache.set(cache_key.materialized, serialize_payload(shared_payload), ttl_seconds=_ttl_seconds(cfg.cache_ttl_days))
    log_stage(
        request_id=request_id,
        stage="report_returned",
        duration_ms=(time.perf_counter() - t0) * 1000,
        verdict=str(report.get("verdict", "")),
    )
    await coordinator.close()
    return report
