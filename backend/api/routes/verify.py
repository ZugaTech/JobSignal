from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from backend.core.metrics import METRICS
from backend.core.orchestrator import verify_job

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
    recommendations_enabled: Optional[bool] = Field(
        default=None,
        description="If set, request similar-job recommendations (still requires search config).",
    )


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
        return await verify_job(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/v1/classify-url")
async def classify_url(url: str = Query(..., min_length=4, max_length=4096)) -> dict:
    value = url.strip()
    if not re.match(r"^https?://", value, re.I):
        return {"is_job_posting": False, "confidence": 0.0, "platform": None}

    for platform, pattern in _JOB_URL_PATTERNS.items():
        if pattern.search(value):
            return {"is_job_posting": True, "confidence": 0.95, "platform": platform}

    if _JOB_HINT_PATTERN.search(value):
        return {"is_job_posting": True, "confidence": 0.7, "platform": "unknown"}

    return {"is_job_posting": False, "confidence": 0.2, "platform": None}


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

        rec_raw = form.get("recommendations_enabled")
        rec_opt = _coerce_optional_bool(rec_raw)

        report = await _verify_or_http_exc(
            job_url=url_s,
            job_description=text_s,
            image_bytes=raw if raw else None,
            image_media_type=mime,
            recommendations_enabled=rec_opt,
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        report["request_id"] = getattr(request.state, "request_id", "unknown")
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
        recommendations_enabled=req.recommendations_enabled,
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    report["request_id"] = getattr(request.state, "request_id", "unknown")
    METRICS.record_verification(str(report.get("verdict", "VERIFY")), cache_hit=bool(report.get("cache", {}).get("hit")))
    return report
