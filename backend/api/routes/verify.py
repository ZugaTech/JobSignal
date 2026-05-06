from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.core.orchestrator import verify_job

router = APIRouter()


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


def _verify_or_http_exc(**kwargs: Any) -> dict:
    try:
        return verify_job(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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

        return _verify_or_http_exc(
            job_url=url_s,
            job_description=text_s,
            image_bytes=raw if raw else None,
            image_media_type=mime,
            recommendations_enabled=rec_opt,
        )

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
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e

    return _verify_or_http_exc(
        job_url=req.job_url,
        job_description=req.job_description,
        recommendations_enabled=req.recommendations_enabled,
    )
