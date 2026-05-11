from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

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
logger = logging.getLogger("jobsignal")

_BATCH_VERIFY_CONCURRENCY = 4


# Heuristic URL hints only — covers major ATS / boards used in production traffic.
# Host patterns align loosely with ``job_url_shortcuts.is_known_job_platform_url``.
_JOB_URL_PATTERNS = {
    "linkedin": re.compile(r"linkedin\.com/(jobs|job)", re.I),
    "indeed": re.compile(r"indeed\.com/(viewjob|jobs|cmp)", re.I),
    "glassdoor": re.compile(r"glassdoor\.com/(job|Interview)", re.I),
    "greenhouse": re.compile(r"greenhouse\.io|boards\.greenhouse\.io", re.I),
    "lever": re.compile(r"jobs\.lever\.co|lever\.co", re.I),
    "workday": re.compile(r"myworkdayjobs\.com|workday\.com", re.I),
    "ashby": re.compile(r"ashbyhq\.com", re.I),
    "smartrecruiters": re.compile(r"smartrecruiters\.com", re.I),
    "jobvite": re.compile(r"jobvite\.com", re.I),
    "icims": re.compile(r"icims\.com", re.I),
    "taleo": re.compile(r"taleo\.net", re.I),
    "successfactors": re.compile(r"successfactors\.com", re.I),
    "bamboohr": re.compile(r"bamboohr\.com", re.I),
    "teamtailor": re.compile(r"teamtailor\.com", re.I),
    "workable": re.compile(r"workable\.com", re.I),
    "recruitee": re.compile(r"recruitee\.com", re.I),
    "personio": re.compile(r"personio\.com", re.I),
    "ziprecruiter": re.compile(r"ziprecruiter\.com", re.I),
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
    verify_depth: Literal["full", "quick"] = Field(
        default="full",
        description=(
            "full: default pipeline (all configured Serper + LLM signals + recommendations when requested). "
            "quick: fewer searches, no LLM text signals, no similar-job recommendations (faster, less thorough)."
        ),
    )


class ValidateUrlsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=40)


class VerifyBatchOptions(BaseModel):
    """Options applied to every URL in the batch (same semantics as single /v1/verify JSON body)."""

    include_similar_jobs: Optional[bool] = Field(
        default=None,
        description="If set, request similar-job recommendations where supported.",
    )
    force_refresh: bool = Field(default=False, description="Skip cache reads for each URL.")
    verify_depth: Literal["full", "quick"] = Field(
        default="full",
        description="Same as single /v1/verify verify_depth (quick skips LLM signals and recommendations).",
    )


class VerifyBatchRequest(BaseModel):
    urls: Annotated[list[str], Field(max_length=40)] = Field(
        default_factory=list,
        description="HTTP(S) job posting URLs, max 40 after deduplicating whitespace-only repeats.",
    )
    options: VerifyBatchOptions = Field(default_factory=VerifyBatchOptions)

    @model_validator(mode="before")
    @classmethod
    def _normalize_and_dedupe_urls(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("urls")
        if not isinstance(raw, list):
            return data
        seen: set[str] = set()
        unique: list[str] = []
        for item in raw:
            if isinstance(item, str):
                s = item.strip()
                if s and s not in seen:
                    seen.add(s)
                    unique.append(s)
        out = dict(data)
        out["urls"] = unique
        return out


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
        vd = str(meta.get("verify_depth") or "full").strip().lower()
        rk = materialize_url_result_cache_key(meta.get("canonical_job_url"), verify_depth=vd)
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
        vd_raw = form.get("verify_depth") or form.get("depth")
        vd_s = str(vd_raw or "full").strip().lower()
        verify_depth_mp: Literal["full", "quick"] = "quick" if vd_s == "quick" else "full"

        report = await _verify_or_http_exc(
            job_url=url_s,
            job_description=text_s,
            image_bytes=raw if raw else None,
            image_media_type=mime,
            include_similar_jobs=rec_opt,
            force_refresh=force_refresh,
            request_id=getattr(request.state, "request_id", "unknown"),
            verify_depth=verify_depth_mp,
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
        verify_depth=req.verify_depth,
    )
    public_rep = await _finalize_verify_response(report)
    METRICS.record_verification(str(public_rep.get("verdict", "VERIFY")), cache_hit=_cache_hit_metric(public_rep))
    return public_rep


@router.post("/v1/verify/batch")
async def verify_batch(body: VerifyBatchRequest) -> StreamingResponse:
    """Verify many URLs; stream **NDJSON** lines as each job completes (order not guaranteed).

    Each line is a JSON object::

        {\"url\": \"...\", \"ok\": true, \"report\": { ... trimmed verify payload ... }}
        {\"url\": \"...\", \"ok\": false, \"error\": \"plain message\"}

    Use ``Accept: application/x-ndjson`` on the client; body is JSON
    ``{\"urls\": [...], \"options\": {\"include_similar_jobs\": bool?, \"force_refresh\": bool}}``.
    """

    urls = body.urls
    if not urls:
        raise HTTPException(status_code=400, detail="Provide at least one job URL.")
    opts = body.options
    sem = asyncio.Semaphore(_BATCH_VERIFY_CONCURRENCY)

    async def run_one(url: str) -> dict[str, Any]:
        rid = str(uuid.uuid4())
        async with sem:
            try:
                raw = await verify_job(
                    job_url=url,
                    job_description=None,
                    include_similar_jobs=opts.include_similar_jobs,
                    force_refresh=opts.force_refresh,
                    request_id=rid,
                    verify_depth=opts.verify_depth,
                )
                repaired = validate_and_repair_response(raw, request_id=str(raw.get("request_id") or rid))
                public = await _finalize_verify_response(repaired)
                METRICS.record_verification(
                    str(public.get("verdict", "VERIFY")),
                    cache_hit=_cache_hit_metric(public),
                )
                return {"url": url, "ok": True, "report": public}
            except ValueError as e:
                return {"url": url, "ok": False, "error": str(e)}
            except Exception as e:  # noqa: BLE001
                logger.exception("batch_verify_failed url=%s request_id=%s", url, rid)
                return {"url": url, "ok": False, "error": "Verification failed for this URL."}

    async def ndjson_lines() -> Any:
        tasks = [asyncio.create_task(run_one(u)) for u in urls]
        for fut in asyncio.as_completed(tasks):
            item = await fut
            yield (json.dumps(item, default=str) + "\n").encode("utf-8")

    return StreamingResponse(ndjson_lines(), media_type="application/x-ndjson")


@router.get("/v1/report/{request_id}")
async def get_report_detail(request_id: str) -> dict:
    """Full verify payload (including longer signal details) when still retained server-side."""

    detail = load_stored_report_detail(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Report not found or expired.")
    return detail


@router.delete("/v1/cache")
async def bust_url_cache(
    url: str = Query(..., min_length=8, max_length=4096),
    verify_depth: Literal["full", "quick"] = Query(
        "full",
        description="Which URL-result cache row to clear (quick vs full use different keys).",
    ),
) -> dict:
    """Hackathon/admin helper: clear URL-only cached verdict for a given URL string."""

    cfg = EnvConfig.load(strict=False)
    cache = _get_cache(cfg)
    u = url.strip()
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    rk = materialize_url_result_cache_key(u, verify_depth=verify_depth)
    if not rk:
        raise HTTPException(status_code=400, detail="Could not normalize URL for cache key.")
    cache.delete(RESULT_CACHE_KEY_PREFIX + rk)
    return {"ok": True, "cleared_key_suffix": rk[:16], "verify_depth": verify_depth}
