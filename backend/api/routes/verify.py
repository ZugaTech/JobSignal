from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from backend.core.metrics import METRICS
from backend.core.orchestrator import verify_job
from backend.core.response_contract import validate_and_repair_response
from backend.core.url_preflight import validate_url_format

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

        report = await _verify_or_http_exc(
            job_url=url_s,
            job_description=text_s,
            image_bytes=raw if raw else None,
            image_media_type=mime,
            include_similar_jobs=rec_opt,
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        METRICS.record_verification(str(report.get("verdict", "VERIFY")), cache_hit=bool(report.get("cache", {}).get("hit")))
        return report

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
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    METRICS.record_verification(str(report.get("verdict", "VERIFY")), cache_hit=bool(report.get("cache", {}).get("hit")))
    return report
