from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from backend.core.env import EnvConfig
from backend.core.metrics import METRICS
from backend.core.normalization import materialize_url_result_cache_key
from backend.core.orchestrator import _get_cache, verify_job
from backend.core.report_detail_store import get_report_detail as load_stored_report_detail, remember_report
from backend.core.response_contract import validate_and_repair_response
from backend.core.response_trim import trim_verify_response
from backend.core.url_preflight import validate_url_format
from backend.core.url_result_cache import (
    RESULT_CACHE_KEY_PREFIX,
    schedule_cache_set,
    should_store_url_result_cache,
    url_result_ttl_seconds,
    wrap_stored_payload,
)

router = APIRouter()


_JOB_URL_PATTERNS = {
    "linkedin": re.compile(r"linkedin\.com/jobs", re.I),
    "indeed": re.compile(r"indeed\.com/(viewjob|jobs)", re.I),
    "greenhouse": re.compile(r"greenhouse\.io", re.I),
    "lever": re.compile(r"lever\.co", re.I),
    "workday": re.compile(r"workday\.(com|jobs)", re.I),
}

_JOB_HINT_PATTERN = re.compile(r"(job|jobs|career|careers|position|apply|hiring)", re.I)


class VerifyRequest(BaseModel):
    job_url: Optional[str] = Field(default=None, description="Job posting URL")
    job_description: Optional[str] = Field(default=None, description="Pasted job description text")
    include_similar_jobs: Optional[bool] = Field(
        default=None,
        description="If set, request similar-job recommendations (still requires search config).",
    )
    force_refresh: bool = Field(
        default=False,
        description="Skip cache reads and run a fresh verification (same inputs).",
    )


class ValidateUrlsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=40)


def _coerce_optional_bool(raw: Any) -> Optional[bool]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return None


async def _verify_or_http_exc(**kwargs: Any) -> dict:
    try:
        raw = await verify_job(**kwargs)
        rid = str(kwargs.get("request_id") or "unknown")
        return validate_and_repair_response(raw, request_id=rid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


async def _finalize_verify_response(report: dict) -> dict:
    """Store full report for detail endpoint; async-write URL result cache; return trimmed client JSON."""

    remember_report(str(report.get("request_id") or ""), dict(report))
    cfg = EnvConfig.load(strict=False)
    meta = report.get("meta") or {}
    if bool(meta.get("url_only_cache_eligible")) and should_store_url_result_cache(report):
        rk = materialize_url_result_cache_key(meta.get("canonical_job_url"))
        if rk:
            ttl = url_result_ttl_seconds(report)
            payload = wrap_stored_payload(
                report=dict(report),
                cached_at_iso=str(report.get("data_freshness") or ""),
                ttl_seconds=ttl,
            )
            cache = _get_cache(cfg)
            await schedule_cache_set(cache, RESULT_CACHE_KEY_PREFIX + rk, payload, ttl)
    return trim_verify_response(report)


def _cache_hit_metric(report: dict) -> bool:
    return bool(report.get("cached")) or bool((report.get("cache") or {}).get("hit"))


@router.get("/v1/classify-url")
async def classify_url(url: str = Query(..., min_length=4, max_length=4096)) -> dict:
    """Heuristic URL hint only — no numeric confidence (not derived from live verification)."""
    value = url.strip()
    fmt = validate_url_format(value)
    if fmt:
        return {
            "is_job_posting": False,
            "platform": None,
            "classification_basis": "invalid_url_format",
            "validation_message": fmt,
        }
    if not re.match(r"^https?://", value, re.I):
        return {
            "is_job_posting": False,
            "platform": None,
            "classification_basis": "invalid_or_non_http_url",
        }

    for platform, pattern in _JOB_URL_PATTERNS.items():
        if pattern.search(value):
            return {
                "is_job_posting": True,
                "platform": platform,
                "classification_basis": "known_job_board_url_pattern",
            }

    if _JOB_HINT_PATTERN.search(value):
        return {
            "is_job_posting": True,
            "platform": "unknown",
            "classification_basis": "url_keyword_hint_only",
        }

    return {
        "is_job_posting": False,
        "platform": None,
        "classification_basis": "no_job_posting_patterns_detected",
    }


@router.post("/v1/validate-urls")
async def validate_urls(body: ValidateUrlsRequest) -> dict:
    """Run the same urlparse-based format checks as the live verify pipeline (no external I/O)."""

    results: list[dict[str, Any]] = []
    for raw in body.urls:
        s = raw.strip() if isinstance(raw, str) else ""
        reason = validate_url_format(s) if s else "This does not appear to be a valid URL. Please check the link and try again."
        results.append(
            {
                "url": s,
                "ok": reason is None,
                "reason": reason or "",
            }
        )
    return {"results": results}


@router.post("/v1/verify")
async def verify(request: Request) -> dict:
    """Accept JSON (``application/json``) or multipart (``job_image`` + optional fields)."""

    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct:
        form = await request.form()
        job_url = form.get("job_url")
        job_description = form.get("job_description")
        url_s = job_url.strip() if isinstance(job_url, str) else None
        text_s = job_description.strip() if isinstance(job_description, str) else None
        if url_s == "":
            url_s = None
        if text_s == "":
            text_s = None

        up = form.get("job_image")
        raw: Optional[bytes] = None
        mime: Optional[str] = None
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            mime = getattr(up, "content_type", None)

        rec_raw = form.get("include_similar_jobs") or form.get("recommendations_enabled")
        rec_opt = _coerce_optional_bool(rec_raw)
        fr_raw = form.get("force_refresh")
        force_refresh = bool(_coerce_optional_bool(fr_raw))

        report = await _verify_or_http_exc(
            job_url=url_s,
            job_description=text_s,
            image_bytes=raw if raw else None,
            image_media_type=mime,
            include_similar_jobs=rec_opt,
            force_refresh=force_refresh,
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        public_rep = await _finalize_verify_response(report)
        METRICS.record_verification(str(public_rep.get("verdict", "VERIFY")), cache_hit=_cache_hit_metric(public_rep))
        return public_rep

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Expected JSON object body.") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object body.")

    try:
        req = VerifyRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    report = await _verify_or_http_exc(
        job_url=req.job_url,
        job_description=req.job_description,
        include_similar_jobs=req.include_similar_jobs,
        force_refresh=req.force_refresh,
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    public_rep = await _finalize_verify_response(report)
    METRICS.record_verification(str(public_rep.get("verdict", "VERIFY")), cache_hit=_cache_hit_metric(public_rep))
    return public_rep


@router.get("/v1/report/{request_id}")
async def get_report_detail(request_id: str) -> dict:
    """Full verify payload (including longer signal details) when still retained server-side."""

    detail = load_stored_report_detail(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Report not found or expired.")
    return detail


@router.delete("/v1/cache")
async def bust_url_cache(url: str = Query(..., min_length=8, max_length=4096)) -> dict:
    """Hackathon/admin helper: clear URL-only cached verdict for a given URL string."""

    cfg = EnvConfig.load(strict=False)
    cache = _get_cache(cfg)
    u = url.strip()
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    rk = materialize_url_result_cache_key(u)
    if not rk:
        raise HTTPException(status_code=400, detail="Could not normalize URL for cache key.")
    cache.delete(RESULT_CACHE_KEY_PREFIX + rk)
    return {"ok": True, "cleared_key_suffix": rk[:16]}
