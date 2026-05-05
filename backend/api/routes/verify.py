from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.orchestrator import verify_job

router = APIRouter()


class VerifyRequest(BaseModel):
    job_url: Optional[str] = Field(default=None, description="Job posting URL")
    job_description: Optional[str] = Field(default=None, description="Pasted job description text")


@router.post("/v1/verify")
def verify(req: VerifyRequest) -> dict:
    try:
        return verify_job(job_url=req.job_url, job_description=req.job_description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

