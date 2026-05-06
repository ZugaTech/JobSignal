"""Screenshot / image ingestion: validate bytes, optional vision extraction, sufficiency gates."""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.llm_fireworks import extract_job_fields_from_image_vision

IMAGE_INGEST_VERSION = "1.0.0"

# Default 5 MiB raw bytes (below typical hosted base64 limits).
_DEFAULT_MAX_IMAGE_BYTES = 5_242_880


def _max_image_bytes() -> int:
    raw = os.environ.get("IMAGE_MAX_BYTES", str(_DEFAULT_MAX_IMAGE_BYTES))
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_IMAGE_BYTES
    return max(64_000, min(n, 20_000_000))


def detect_image_mime(data: bytes) -> Optional[str]:
    """Return ``image/png``, ``image/jpeg``, or ``image/webp`` if magic bytes match."""

    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_client_image_type(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    ct = content_type.split(";")[0].strip().lower()
    if ct in ("image/jpg",):
        return "image/jpeg"
    if ct in ("image/png", "image/jpeg", "image/webp"):
        return ct
    return None


class ExtractedVisionFields(BaseModel):
    """Strict schema for vision model JSON; failures become insufficient ingestion."""

    model_config = ConfigDict(extra="forbid")

    extraction_confidence: Literal["high", "medium", "low"]
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    job_url_hint: Optional[str] = None
    extracted_job_text: str = ""
    notes: str = ""

    @field_validator("job_title", "company_name", "job_url_hint", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("extracted_job_text", "notes", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


@dataclass(frozen=True, slots=True)
class ImageIngestResult:
    """Outcome of validating image bytes and (optionally) running vision extraction."""

    status: Literal["ok", "insufficient"]
    fields: Optional[ExtractedVisionFields]
    warnings: List[Dict[str, str]]
    declared_mime: str
    detected_mime: Optional[str]


def _hint_looks_like_http_url(hint: str) -> bool:
    s = hint.strip()
    if not s:
        return False
    p = urlparse(s)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _substantive_extraction(fields: ExtractedVisionFields) -> bool:
    text = (fields.extracted_job_text or "").strip()
    if len(text) >= 120:
        return True
    title = (fields.job_title or "").strip()
    company = (fields.company_name or "").strip()
    if len(title) >= 3 and len(company) >= 2:
        return True
    hint = fields.job_url_hint or ""
    if _hint_looks_like_http_url(hint):
        return True
    if len(title) >= 3 and _hint_looks_like_http_url(hint):
        return True
    return False


def extraction_usable_for_image_only(fields: ExtractedVisionFields) -> bool:
    """Whether screenshot-only input is allowed to continue into normalize/score."""

    if fields.extraction_confidence == "low":
        return False
    return _substantive_extraction(fields)


def validate_image_bytes(data: bytes, declared_mime: Optional[str]) -> tuple[Optional[str], List[Dict[str, str]]]:
    """Return ``(detected_mime, warnings)`` or raise ``ValueError`` for hard rejects."""

    warnings: List[Dict[str, str]] = []
    if not data:
        raise ValueError("IMAGE_EMPTY: Image payload is empty.")
    max_b = _max_image_bytes()
    if len(data) > max_b:
        raise ValueError(f"IMAGE_TOO_LARGE: Image exceeds {max_b} bytes.")

    detected = detect_image_mime(data)
    norm_declared = normalize_client_image_type(declared_mime)

    if norm_declared and detected and norm_declared != detected:
        raise ValueError("IMAGE_MIME_MISMATCH: Declared type does not match image contents.")

    effective = detected or norm_declared
    if effective is None:
        raise ValueError("IMAGE_TYPE: Only PNG, JPEG, and WebP images are supported.")

    if norm_declared and not detected:
        warnings.append(
            {
                "code": "IMAGE_MAGIC_UNVERIFIED",
                "message": "Could not verify magic bytes; proceeding with declared MIME.",
            }
        )

    return effective, warnings


def ingest_job_image(
    data: bytes,
    *,
    declared_mime: Optional[str],
    user_supplied_url_or_text: bool,
) -> ImageIngestResult:
    """Validate bytes and run vision extraction when enabled; apply sufficiency rules for image-only."""

    effective_mime, vw = validate_image_bytes(data, declared_mime)
    warnings = list(vw)

    raw, vision_warnings = extract_job_fields_from_image_vision(
        mime_type=effective_mime,
        data_url=bytes_to_data_url(data, effective_mime),
    )
    warnings.extend(vision_warnings)

    if raw is None:
        if user_supplied_url_or_text:
            return ImageIngestResult(
                status="ok",
                fields=None,
                warnings=warnings,
                declared_mime=declared_mime or "",
                detected_mime=effective_mime,
            )
        return ImageIngestResult(
            status="insufficient",
            fields=None,
            warnings=warnings,
            declared_mime=declared_mime or "",
            detected_mime=effective_mime,
        )

    try:
        fields = ExtractedVisionFields.model_validate(raw)
    except Exception:  # noqa: BLE001
        warnings.append(
            {
                "code": "VISION_SCHEMA",
                "message": "Vision output did not match the required JSON schema; treating as insufficient.",
            }
        )
        if user_supplied_url_or_text:
            return ImageIngestResult(
                status="ok",
                fields=None,
                warnings=warnings,
                declared_mime=declared_mime or "",
                detected_mime=effective_mime,
            )
        return ImageIngestResult(
            status="insufficient",
            fields=None,
            warnings=warnings,
            declared_mime=declared_mime or "",
            detected_mime=effective_mime,
        )

    if not user_supplied_url_or_text and not extraction_usable_for_image_only(fields):
        warnings.append(
            {
                "code": "IMAGE_INSUFFICIENT",
                "message": "Screenshot does not contain enough readable job details for verification.",
            }
        )
        return ImageIngestResult(
            status="insufficient",
            fields=fields,
            warnings=warnings,
            declared_mime=declared_mime or "",
            detected_mime=effective_mime,
        )

    if fields.extraction_confidence == "low" and user_supplied_url_or_text:
        warnings.append(
            {
                "code": "VISION_LOW_CONFIDENCE",
                "message": "Extraction confidence is low; relying primarily on URL/text you provided.",
            }
        )

    return ImageIngestResult(
        status="ok",
        fields=fields,
        warnings=warnings,
        declared_mime=declared_mime or "",
        detected_mime=effective_mime,
    )


def bytes_to_data_url(data: bytes, mime: str) -> str:
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def merge_description_with_extraction(user_text: Optional[str], fields: Optional[ExtractedVisionFields]) -> Optional[str]:
    """Combine pasted description with model-extracted job text."""

    chunks: List[str] = []
    if user_text and user_text.strip():
        chunks.append(user_text.strip())
    if fields and (fields.extracted_job_text or "").strip():
        chunks.append(fields.extracted_job_text.strip())
    if fields:
        header_parts: List[str] = []
        if fields.job_title:
            header_parts.append(f"Title (from image): {fields.job_title.strip()}")
        if fields.company_name:
            header_parts.append(f"Company (from image): {fields.company_name.strip()}")
        if fields.job_url_hint and _hint_looks_like_http_url(fields.job_url_hint):
            header_parts.append(f"URL hint (from image): {fields.job_url_hint.strip()}")
        if header_parts:
            chunks.insert(0, "\n".join(header_parts))
    if not chunks:
        return None
    return "\n\n---\n\n".join(chunks)


def coalesce_url(user_url: Optional[str], fields: Optional[ExtractedVisionFields]) -> Optional[str]:
    if user_url:
        return user_url
    if not fields or not fields.job_url_hint:
        return None
    hint = fields.job_url_hint.strip()
    if _hint_looks_like_http_url(hint):
        return hint
    # tolerate missing scheme
    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\S*$", hint) and not hint.lower().startswith(("http://", "https://")):
        return f"https://{hint}"
    return None
