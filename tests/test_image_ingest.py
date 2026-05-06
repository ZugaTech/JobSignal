import base64

import pytest

from backend.core.image_ingest import (
    ExtractedVisionFields,
    detect_image_mime,
    extraction_usable_for_image_only,
    ingest_job_image,
    validate_image_bytes,
)

MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6XKp6sAAAAASUVORK5CYII="
)


def test_detect_png_magic():
    assert detect_image_mime(MINI_PNG) == "image/png"


def test_validate_rejects_empty():
    with pytest.raises(ValueError, match="IMAGE_EMPTY"):
        validate_image_bytes(b"", "image/png")


def test_validate_rejects_mime_mismatch():
    junk = b"\x89PNG\r\n\x1a\n" + b"x" * 200
    with pytest.raises(ValueError, match="IMAGE_MIME_MISMATCH"):
        validate_image_bytes(junk, "image/jpeg")


def test_extraction_usable_requires_substance():
    low = ExtractedVisionFields.model_validate(
        {
            "extraction_confidence": "low",
            "extracted_job_text": "short",
            "notes": "",
        }
    )
    assert extraction_usable_for_image_only(low) is False

    high_min = ExtractedVisionFields.model_validate(
        {
            "extraction_confidence": "high",
            "job_title": "Engineer",
            "company_name": "Acme",
            "extracted_job_text": "",
            "notes": "",
        }
    )
    assert extraction_usable_for_image_only(high_min) is True


def test_ingest_image_only_insufficient_when_vision_disabled(monkeypatch):
    monkeypatch.setattr(
        "backend.core.image_ingest.extract_job_fields_from_image_vision",
        lambda **kwargs: (None, [{"code": "VISION_DISABLED", "message": "off"}]),
    )
    out = ingest_job_image(MINI_PNG, declared_mime="image/png", user_supplied_url_or_text=False)
    assert out.status == "insufficient"


def test_ingest_image_only_ok_when_vision_returns_substance(monkeypatch):
    def fake(**kwargs):
        return (
            {
                "extraction_confidence": "high",
                "job_title": "Software Engineer",
                "company_name": "Acme Inc",
                "job_url_hint": "https://example.com/jobs/1",
                "extracted_job_text": "We are hiring for a backend role with Python experience. " * 4,
                "notes": "readable screenshot",
            },
            [],
        )

    monkeypatch.setattr("backend.core.image_ingest.extract_job_fields_from_image_vision", fake)
    out = ingest_job_image(MINI_PNG, declared_mime="image/png", user_supplied_url_or_text=False)
    assert out.status == "ok"
    assert out.fields is not None
    assert out.fields.extraction_confidence == "high"
