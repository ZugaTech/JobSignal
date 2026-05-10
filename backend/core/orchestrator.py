"""End-to-end verify orchestration (post–Sprint 4 vertical slice).

validate → normalize → URL result cache / legacy cache → evidence (parallel) → scoring → report.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from functools import partial
from typing import Any, Dict, List, Optional

from backend.core.cache_key import build_public_cache_key
from backend.core.cache_payload import serialize_payload, strip_tenant_fields
from backend.core.cache_store import CacheStore, InMemoryCache, RedisCache
from backend.core.coordinator import EvidenceCoordinator
from backend.core.decision_schema import DecisionResponse, ReasonItem, Verdict, WarningItem
from backend.core.env import EnvConfig
from backend.core.fireworks_defaults import DEFAULT_FIREWORKS_MODEL
from backend.core.evidence import build_evidence_bundle, _collect_serper_queries
from backend.core.extraction import extract_entities
from backend.core.fetch_job_page import JobPageFetchOutcome, job_fetch_enabled, run_job_page_fetch
from backend.core.description_pipeline import (
    build_content_analysis_signals,
    build_input_meta_no_company,
    build_input_meta_with_company,
    cap_confidence_for_content_only,
    extract_fields_from_description,
    sanitize_company_name,
)
from backend.core.image_ingest import (
    IMAGE_INGEST_VERSION,
    ExtractedVisionFields,
    coalesce_url,
    ingest_job_image,
    merge_description_with_extraction,
)
from backend.core.inputs import InputValidationError, validate_verify_inputs
from backend.core.job_url_shortcuts import is_known_job_platform_url, pick_employer_display_name, is_scam_domain_url
from backend.core.llm_fireworks import build_llm_signals, llm_enabled
from backend.core.llm_safe import call_llm_safe
from backend.core.normalization import NormalizationResult, normalize_job_input, materialize_url_result_cache_key
from backend.core.quick_url_probe import probe_http_status_head
from backend.core.report import build_public_report
from backend.core.response_contract import (
    build_preflight_skip_report,
    build_preflight_verify_job_uncertain_report,
)
from backend.core.scoring import SCORER_VERSION, decide_from_signals
from backend.core.structured_log import log_stage
from backend.core.url_preflight import evaluate_job_url_preflight
from backend.core.url_result_cache import (
    RESULT_CACHE_KEY_PREFIX,
    decorate_hit_response,
    parse_stored_payload,
)
from backend.core.user_copy import build_fallback_llm_summary
from backend.evidence.company_reviews import ReviewSummary, extract_company_name_hardened, get_company_reviews

logger = logging.getLogger("jobsignal")


async def _shutdown_serp_coords(*coords: EvidenceCoordinator) -> None:
    await asyncio.gather(*(c.close() for c in coords), return_exceptions=True)


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


def _norm_with_fetch_hints(norm: NormalizationResult, fx: Optional[JobPageFetchOutcome]) -> NormalizationResult:
    """Use fetched page title/description as recommendation discovery text.

    The canonical URL remains unchanged. The fetched text is only used to build
    better similar-role search queries when the user did not paste a
    description; it is not stored as user-provided private text.
    """

    if norm.description_text or not fx or not fx.extracted_job_text:
        return norm
    return NormalizationResult(
        normalization_version=norm.normalization_version,
        canonical_url=norm.canonical_url,
        canonical_url_sha256=norm.canonical_url_sha256,
        description_text=fx.extracted_job_text,
        description_full_sha256=norm.description_full_sha256,
        registrable_domain=norm.registrable_domain,
    )


async def _fetch_hints_for_recommendations(norm: NormalizationResult, cfg: EnvConfig) -> NormalizationResult:
    if norm.description_text or not norm.canonical_url or not job_fetch_enabled():
        return norm
    try:
        fx = await asyncio.to_thread(run_job_page_fetch, norm.canonical_url, cfg)
    except Exception:  # noqa: BLE001 - recommendations are best-effort
        return norm
    return _norm_with_fetch_hints(norm, fx)


def _confidence_numeric(band: str) -> int:
    # Numeric confidence must come from scoring; missing scores are unavailable, not a band-derived default.
    return 0


async def verify_job(
    job_url: Optional[str],
    job_description: Optional[str],
    *,
    image_bytes: Optional[bytes] = None,
    image_media_type: Optional[str] = None,
    skip_recommendations: bool = False,
    include_similar_jobs: Optional[bool] = None,
    request_id: str = "unknown",
    force_refresh: bool = False,
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

    # --- SMART INPUT INTELLIGENCE ---
    # Determine whether we have a pure description/screenshot input (no URL yet)
    desc_only_input = not effective_url and effective_text and effective_text.strip()

    # Short description guard: under 80 words → reject early
    _desc_word_count = len((effective_text or "").split()) if effective_text else 0
    if desc_only_input and _desc_word_count < 80:
        short_report = build_preflight_verify_job_uncertain_report(
            reason=(
                "This description is too short to assess meaningfully. "
                "Please paste the full job posting text."
            ),
            request_id=request_id,
        )
        short_report["input_meta"] = {
            "input_method": "screenshot" if has_image else "description",
            "company_identified": False,
            "short_description": True,
            "word_count": _desc_word_count,
        }
        short_report["confidence_score"] = 10
        return short_report

    # Extract structured fields from description (for routing)
    _desc_extraction = None
    _auto_url_extracted = False
    if desc_only_input and effective_text:
        _desc_extraction = extract_fields_from_description(
            effective_text, request_id=request_id
        )
        # If the description contains a URL, auto-switch to URL pipeline
        if _desc_extraction.application_url:
            effective_url = _desc_extraction.application_url
            _auto_url_extracted = True
            log_stage(
                request_id=request_id,
                stage="auto_url_extracted_from_description",
                duration_ms=0.0,
            )

    # Legacy short-description guard (kept for backward-compat < 50 chars)
    if (
        not effective_url
        and effective_text
        and not has_image
        and len(effective_text.strip()) < 50
    ):
        return build_preflight_verify_job_uncertain_report(
            reason="Description too short to assess. Please paste the full job posting.",
            request_id=request_id,
        )

    norm = normalize_job_input(effective_url, effective_text)

    if norm.canonical_url:
        if is_scam_domain_url(norm.canonical_url):
            return build_preflight_skip_report(
                reason="This domain has been associated with fraudulent job postings.",
                request_id=request_id,
            )
        if is_known_job_platform_url(norm.canonical_url):
            st = await probe_http_status_head(norm.canonical_url)
            if st in (404, 410):
                return build_preflight_skip_report(
                    reason="This job posting appears to have been removed.",
                    request_id=request_id,
                )

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

    steps: List[Dict[str, Any]] = [{"id": "normalize", "label": "Normalized input"}]

    api_key = os.environ.get("SERPER_API_KEY") or os.environ.get("SEARCH_API_KEY") or ""
    endpoint = (cfg.search_api_endpoint or "").strip() or "https://google.serper.dev/search"
    timeout_s = float(cfg.search_timeout_s)
    coord_evidence = EvidenceCoordinator(
        api_key=api_key,
        search_timeout_s=timeout_s,
        max_calls=cfg.search_max_calls_evidence,
        search_endpoint=endpoint,
    )
    coord_reputation = EvidenceCoordinator(
        api_key=api_key,
        search_timeout_s=timeout_s,
        max_calls=cfg.search_max_calls_reputation,
        search_endpoint=endpoint,
    )
    coord_rec = EvidenceCoordinator(
        api_key=api_key,
        search_timeout_s=timeout_s,
        max_calls=cfg.search_max_calls_recommendations,
        search_endpoint=endpoint,
    )

    cache = _get_cache(cfg)

    url_only_cache = bool(norm.canonical_url) and not has_image and not (effective_text or "").strip()

    if url_only_cache and not force_refresh:
        rk = materialize_url_result_cache_key(norm.canonical_url)
        if rk:
            url_cache_key = RESULT_CACHE_KEY_PREFIX + rk
            hit_raw = cache.get(url_cache_key)
            parsed = parse_stored_payload(hit_raw) if hit_raw else None
            if parsed:
                rep, cat, exp_iso = parsed
                try:
                    exp_dt = datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > exp_dt:
                        parsed = None
                except ValueError:
                    pass
            if parsed:
                rep, cat, exp_iso = parsed
                out = decorate_hit_response(rep, cached_at=cat, expires_at_iso=exp_iso, now_iso=data_freshness)
                logger.info(
                    "cache_hit url_result request_id=%s cached_at=%s has_review=%s cache_complete=%s",
                    request_id,
                    cat,
                    out.get("review_summary") is not None,
                    out.get("cache_complete"),
                )
                log_stage(request_id=request_id, stage="url_result_cache_hit", duration_ms=(time.perf_counter() - t0) * 1000)
                # Cached payload may omit similar jobs or reflect an older request flag.
                # Honor the current request: attach fresh recommendations when asked; strip when not.
                if include_similar_jobs:
                    rec_norm = await _fetch_hints_for_recommendations(norm, cfg)
                    await _maybe_attach_recommendations(
                        out,
                        norm=rec_norm,
                        merged_fields=merged_fields,
                        skip_recommendations=skip_recommendations,
                        include_similar_jobs=True,
                        coordinator=coord_rec,
                    )
                    out["similar_jobs"] = list(out.get("recommendations") or [])
                    meta_m = dict(out.get("meta") or {})
                    meta_m["similar_jobs_requested"] = True
                    out["meta"] = meta_m
                else:
                    out["similar_jobs"] = None
                    meta_m = dict(out.get("meta") or {})
                    meta_m.pop("similar_jobs_requested", None)
                    out["meta"] = meta_m
                await _shutdown_serp_coords(coord_evidence, coord_reputation, coord_rec)
                log_stage(
                    request_id=request_id,
                    stage="report_returned",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    verdict=str(out.get("verdict", "")),
                )
                return out

    if not url_only_cache and not force_refresh:
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
                    "pipeline_steps": steps,
                    "canonical_job_url": norm.canonical_url,
                    "url_only_cache_eligible": False,
                },
                ingestion=_ingestion_payload(has_image, merged_fields, detected_mime, source="cache"),
                data_freshness=data_freshness,
            )
            rs_snap = payload.get("review_summary")
            if rs_snap is not None:
                report["review_summary"] = rs_snap
            if payload.get("llm_summary"):
                report["llm_summary"] = str(payload.get("llm_summary"))
            logger.info(
                "cache_hit legacy request_id=%s has_review=%s",
                request_id,
                report.get("review_summary") is not None,
            )
            log_stage(request_id=request_id, stage="cache_hit", duration_ms=(time.perf_counter() - t0) * 1000)
            await _maybe_attach_recommendations(
                report,
                norm=await _fetch_hints_for_recommendations(norm, cfg) if include_similar_jobs else norm,
                merged_fields=merged_fields,
                skip_recommendations=skip_recommendations,
                include_similar_jobs=include_similar_jobs,
                coordinator=coord_rec,
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
            await _shutdown_serp_coords(coord_evidence, coord_reputation, coord_rec)
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

    page_fetch_outcome: Optional[JobPageFetchOutcome] = None

    async def _evidence_phase() -> tuple[Any, ReviewSummary]:
        nonlocal page_fetch_outcome
        ext_local = extract_entities(norm)

        if norm.canonical_url and job_fetch_enabled():
            fx = await asyncio.to_thread(run_job_page_fetch, norm.canonical_url, cfg)
        else:
            fx = JobPageFetchOutcome(attempted=False)
        page_fetch_outcome = fx

        parts_txt: list[str] = []
        if (norm.description_text or "").strip():
            parts_txt.append(norm.description_text.strip())
        if (fx.extracted_job_text or "").strip():
            parts_txt.append(fx.extracted_job_text.strip())
        combined_text = "\n\n".join(parts_txt) if parts_txt else None

        url_for_company = norm.canonical_url
        if url_for_company and is_known_job_platform_url(url_for_company):
            url_for_company = None

        hardened_company = await asyncio.to_thread(
            partial(extract_company_name_hardened, url_for_company, combined_text, request_id=request_id),
        )

        signals.extend(fx.signals)
        warnings.extend(fx.warnings)

        fetch_norm = _norm_with_fetch_hints(norm, fx)
        ext_for_search = extract_entities(fetch_norm) if fetch_norm is not norm else ext_local
        employer_for_queries = pick_employer_display_name(
            ext_for_search.company_hint,
            hardened_company,
        )
        company = employer_for_queries or ""
        title = ext_for_search.title_hint or ""
        base_query = f"{company} {title}".strip() or (norm.canonical_url or "")

        if merged_fields and merged_fields.company_name and ext_local.company_hint:
            vc = merged_fields.company_name.strip().lower()
            uc = ext_local.company_hint.strip().lower()
            if vc and uc and vc not in uc and uc not in vc:
                signals.append(
                    {
                        "id": "input_source_mismatch",
                        "label": "Input consistency",
                        "tier": "T2",
                        "strength": "medium",
                        "details": "Input sources appear inconsistent — please verify manually.",
                        "name": "Input consistency",
                        "status": "warn",
                        "detail": "URL-derived employer hints differ from screenshot extraction.",
                        "source": "client",
                    }
                )

        evidence_task = asyncio.create_task(_collect_serper_queries(coord_evidence, base_query, company, title))
        review_task = asyncio.create_task(
            get_company_reviews(coord_reputation, employer_for_queries, request_id=request_id)
        )
        serp_results, review_summary = await asyncio.gather(evidence_task, review_task)
        bundle = build_evidence_bundle(norm, ext_local, serp_results, page_fetch=fx)
        signals.extend(bundle.signals)
        warnings.extend(bundle.warnings)
        return bundle, review_summary

    bundle = None
    review_summary: Optional[ReviewSummary] = None
    bundle, review_summary = await _evidence_phase()

    log_stage(request_id=request_id, stage="evidence_gathered", duration_ms=(time.perf_counter() - t0) * 1000)

    steps.append({"id": "evidence", "label": "Evidence collection"})
    steps.append({"id": "llm", "label": "AI-assisted signals"})
    llm_text_parts: List[str] = []
    if (norm.description_text or "").strip():
        llm_text_parts.append(norm.description_text.strip())
    if page_fetch_outcome and (page_fetch_outcome.extracted_job_text or "").strip():
        llm_text_parts.append(page_fetch_outcome.extracted_job_text.strip())
    merged_llm_job_text = "\n\n".join(llm_text_parts)
    llm = build_llm_signals(job_text=merged_llm_job_text)
    if llm.signals:
        signals.extend(llm.signals)
    if llm.warnings:
        warnings.extend(llm.warnings)

    steps.append({"id": "score", "label": "Scoring engine"})
    decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))

    from backend.core.llm_fireworks import _get

    verdict_raw = decision["verdict"]
    verdict_val = verdict_raw.value if hasattr(verdict_raw, "value") else str(verdict_raw)
    reasons_list = decision.get("reasons") or []
    conf_band = str(decision.get("confidence") or "low").lower()
    raw_cs = decision.get("confidence_score")
    if raw_cs is not None:
        cs_num = max(0, min(100, int(raw_cs)))
    else:
        cs_num = _confidence_numeric(conf_band)
    provisional_for_fallback: Dict[str, Any] = {
        "verdict": verdict_val,
        "confidence_score": cs_num,
        "signals": signals,
        "reasons": reasons_list,
    }
    fallback_txt = build_fallback_llm_summary(provisional_for_fallback)

    use_llm_summary = not (
        verdict_val in ("APPLY", "SKIP") and cs_num >= int(cfg.llm_summary_confidence_threshold)
    )

    api_key_llm = _get("FIREWORKS_API_KEY") or _get("LLM_API_KEY")
    llm_enabled_flag = llm_enabled()
    if api_key_llm and llm_enabled_flag and use_llm_summary:
        llm_summary = await call_llm_safe(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are JobSignal, a verification assistant. Write a 2-sentence briefing for a job seeker. "
                        "No jargon. Never mention internal tiers (such as T1/T2/T3), gates, or scoring rule names. "
                        "No headers. Output ONLY the briefing text."
                    ),
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
            model=_get("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
            temperature=0.3,
            max_tokens=150,
            timeout=8.0,
        )
    else:
        llm_summary = fallback_txt

    log_stage(
        request_id=request_id,
        stage="score_computed",
        duration_ms=(time.perf_counter() - t0) * 1000,
        verdict=decision["verdict"].value,
    )

    evidence_sources = getattr(bundle, "evidence_sources", None) if bundle else None

    report = build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
        meta={
            "pipeline_version": cfg.source_pipeline_version,
            "scorer_version": SCORER_VERSION,
            "pipeline_steps": steps,
            "canonical_job_url": norm.canonical_url,
            "url_only_cache_eligible": url_only_cache,
        },
        ingestion=_ingestion_payload(has_image, merged_fields, detected_mime, source="live"),
        evidence_sources=evidence_sources,
        data_freshness=data_freshness,
        review_summary=asdict(review_summary) if review_summary else None,
    )
    report["llm_summary"] = llm_summary

    await _maybe_attach_recommendations(
        report,
        norm=_norm_with_fetch_hints(norm, page_fetch_outcome),
        merged_fields=merged_fields,
        skip_recommendations=skip_recommendations,
        include_similar_jobs=include_similar_jobs,
        coordinator=coord_rec,
    )
    if include_similar_jobs:
        report["similar_jobs"] = list(report.get("recommendations") or [])
        meta_m = dict(report.get("meta") or {})
        meta_m["similar_jobs_requested"] = True
        report["meta"] = meta_m
    else:
        report["similar_jobs"] = None

    # ---- SMART INPUT INTELLIGENCE: attach input_meta & apply no-company pipeline caps ----
    _pure_desc_no_url = not norm.canonical_url and not has_image
    _pure_desc_or_image_no_url = not norm.canonical_url

    if _desc_extraction is not None and not _auto_url_extracted:
        if _desc_extraction.has_company_info:
            # STEP 2A — full verification (already ran), annotate with suggestion
            report["input_meta"] = build_input_meta_with_company(
                _desc_extraction,
                input_method="screenshot" if has_image else "description",
            )
        else:
            # STEP 2B — content analysis only: cap confidence, force VERIFY
            # Inject content-analysis signals
            ca_signals = build_content_analysis_signals(
                effective_text or "", _desc_extraction
            )
            # Attach them to the signals list but don't re-run the scorer;
            # instead inject directly into report as extra context
            report["content_analysis_signals"] = ca_signals
            cap_confidence_for_content_only(report)
            report["input_meta"] = build_input_meta_no_company(_desc_extraction)
    elif has_image and merged_fields:
        # Screenshot path: annotate based on vision extraction
        img_company = sanitize_company_name(merged_fields.company_name)
        if img_company:
            report["input_meta"] = {
                "input_method": "screenshot",
                "company_identified": True,
                "extracted_company_name": img_company,
                "extracted_job_title": merged_fields.job_title,
                "extracted_fields": {
                    "job_title": merged_fields.job_title,
                    "company_name": img_company,
                    "url_hint": merged_fields.job_url_hint,
                },
            }
        else:
            report["input_meta"] = {
                "input_method": "screenshot",
                "company_identified": False,
                "extracted_job_title": merged_fields.job_title,
                "extracted_fields": {
                    "job_title": merged_fields.job_title,
                    "company_name": None,
                    "url_hint": merged_fields.job_url_hint,
                },
            }
            cap_confidence_for_content_only(report)
    elif _auto_url_extracted:
        report["input_meta"] = {
            "input_method": "description",
            "company_identified": bool(_desc_extraction and _desc_extraction.has_company_info),
            "auto_url_extracted": True,
            "extracted_url": effective_url,
        }

    if not url_only_cache:
        shared_payload = strip_tenant_fields(
            {
                "schema_version": "1",
                "pipeline_version": cfg.source_pipeline_version,
                "source_set_version": "live-v1",
                "normalization_version": norm.normalization_version,
                "signals": signals,
                "warnings": [w["code"] for w in warnings],
                "coverage": "partial" if signals else "none",
                "review_summary": report.get("review_summary"),
                "llm_summary": report.get("llm_summary"),
            }
        )
        cache.set(cache_key.materialized, serialize_payload(shared_payload), ttl_seconds=_ttl_seconds(cfg.cache_ttl_days))

    log_stage(
        request_id=request_id,
        stage="report_returned",
        duration_ms=(time.perf_counter() - t0) * 1000,
        verdict=str(report.get("verdict", "")),
    )
    await _shutdown_serp_coords(coord_evidence, coord_reputation, coord_rec)
    return report
