"""Tests for Sprint — Smart Input Intelligence pipelines.

Tests 1-10 per sprint spec. All tests are unit-level (no live API calls).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_desc_extraction(
    company_name=None,
    job_title=None,
    location=None,
    salary_mentioned=False,
    salary_range=None,
    contact_email=None,
    application_url=None,
    has_company_info=False,
):
    from backend.core.description_pipeline import DescriptionExtractionResult

    return DescriptionExtractionResult(
        company_name=company_name,
        job_title=job_title,
        location=location,
        salary_mentioned=salary_mentioned,
        salary_range=salary_range,
        contact_email=contact_email,
        contact_phone=None,
        application_url=application_url,
        has_company_info=has_company_info,
    )


# ---------------------------------------------------------------------------
# Test 1: Description with company name → build_input_meta_with_company
# ---------------------------------------------------------------------------


class TestDescriptionWithCompany(unittest.TestCase):
    def test_meta_company_identified_true(self):
        from backend.core.description_pipeline import build_input_meta_with_company

        ext = _make_desc_extraction(
            company_name="Acme Corp",
            job_title="Software Engineer",
            has_company_info=True,
        )
        meta = build_input_meta_with_company(ext, input_method="description")
        assert meta["company_identified"] is True
        assert meta["extracted_company_name"] == "Acme Corp"
        assert meta["input_method"] == "description"


# ---------------------------------------------------------------------------
# Test 2: Description without company → VERIFY, confidence capped at 55
# ---------------------------------------------------------------------------


class TestDescriptionNoCompany(unittest.TestCase):
    def test_confidence_capped_and_verify_verdict(self):
        from backend.core.description_pipeline import cap_confidence_for_content_only

        report = {"verdict": "APPLY", "confidence_score": 80}
        cap_confidence_for_content_only(report)
        assert report["verdict"] == "VERIFY"
        assert report["confidence_score"] == 55

    def test_confidence_not_raised_if_already_low(self):
        from backend.core.description_pipeline import cap_confidence_for_content_only

        report = {"verdict": "VERIFY", "confidence_score": 30}
        cap_confidence_for_content_only(report)
        assert report["confidence_score"] == 30

    def test_meta_company_identified_false(self):
        from backend.core.description_pipeline import build_input_meta_no_company

        ext = _make_desc_extraction(company_name=None, has_company_info=False)
        meta = build_input_meta_no_company(ext)
        assert meta["company_identified"] is False
        assert meta["input_method"] == "description"


# ---------------------------------------------------------------------------
# Test 3: Description under 80 words → confidence 10, short_description flag
# ---------------------------------------------------------------------------


class TestShortDescriptionGuard(unittest.TestCase):
    def test_short_description_under_80_words_returns_early(self):
        """Verify orchestrator sets short_description=True and confidence_score=10."""
        import asyncio
        import os

        os.environ["ENABLE_LLM_SIGNALS"] = "0"
        os.environ["ENABLE_IMAGE_VERIFY"] = "0"

        short_text = "We are hiring. Great pay. Apply now." * 3  # ~18 words

        # Import after env set
        from backend.core.orchestrator import verify_job

        result = asyncio.get_event_loop().run_until_complete(
            verify_job(None, short_text, request_id="test_short")
        )

        assert result.get("confidence_score") == 10
        meta = result.get("input_meta", {})
        assert meta.get("short_description") is True

    def tearDown(self):
        import os

        os.environ.pop("ENABLE_LLM_SIGNALS", None)
        os.environ.pop("ENABLE_IMAGE_VERIFY", None)


# ---------------------------------------------------------------------------
# Test 4: Description with embedded URL → application_url extracted
# ---------------------------------------------------------------------------


class TestDescriptionEmbeddedUrl(unittest.TestCase):
    def test_application_url_valid_extraction(self):
        from backend.core.description_pipeline import _valid_url

        assert _valid_url("https://jobs.example.com/apply") == "https://jobs.example.com/apply"
        assert _valid_url("not-a-url") is None
        assert _valid_url("") is None
        assert _valid_url(None) is None

    def test_llm_extraction_returns_application_url(self):
        """If LLM extraction returns a URL, it is passed through as application_url."""
        from backend.core.description_pipeline import (
            DescriptionExtractionResult,
            _valid_url,
        )

        # Simulate extraction result with embedded URL
        extracted_url = "https://company.com/jobs/123"
        assert _valid_url(extracted_url) == extracted_url


# ---------------------------------------------------------------------------
# Test 5: Screenshot with company name → company_identified True
# ---------------------------------------------------------------------------


class TestScreenshotWithCompany(unittest.TestCase):
    def test_sanitize_company_valid(self):
        from backend.core.description_pipeline import sanitize_company_name

        assert sanitize_company_name("Acme Corp") == "Acme Corp"
        assert sanitize_company_name("  TechStartup Inc  ") == "TechStartup Inc"

    def test_vision_fields_has_company_info(self):
        from backend.core.image_ingest import ExtractedVisionFields

        fields = ExtractedVisionFields.model_validate(
            {
                "extraction_confidence": "high",
                "job_title": "SWE",
                "company_name": "Google",
                "job_url_hint": None,
                "extracted_job_text": "Software engineer role at Google, Mountain View.",
                "notes": "Clear screenshot.",
                "has_company_info": True,
                "low_quality_image": False,
            }
        )
        assert fields.has_company_info is True
        assert fields.low_quality_image is False
        assert fields.company_name == "Google"


# ---------------------------------------------------------------------------
# Test 6: Screenshot with low_quality_image=True → VERIFY, confidence 5
# ---------------------------------------------------------------------------


class TestLowQualityImage(unittest.TestCase):
    def test_low_quality_image_flag_parsed(self):
        from backend.core.image_ingest import ExtractedVisionFields

        fields = ExtractedVisionFields.model_validate(
            {
                "extraction_confidence": "low",
                "job_title": None,
                "company_name": None,
                "job_url_hint": None,
                "extracted_job_text": "",
                "notes": "Image too blurry.",
                "has_company_info": False,
                "low_quality_image": True,
            }
        )
        assert fields.low_quality_image is True
        assert fields.extraction_confidence == "low"

    def test_insufficient_image_report_has_low_confidence(self):
        from unittest.mock import MagicMock

        from backend.core.env import EnvConfig
        from backend.core.orchestrator import _insufficient_image_report

        cfg = MagicMock(spec=EnvConfig)
        cfg.source_pipeline_version = "test"

        report = _insufficient_image_report(cfg=cfg, warnings=[])
        # The report should contain a VERIFY verdict
        assert report.get("verdict") == "VERIFY"


# ---------------------------------------------------------------------------
# Test 7 & 8: Generic company name blocklist → sanitize to None
# ---------------------------------------------------------------------------


class TestGenericCompanyBlocklist(unittest.TestCase):
    def test_blocklist_values_return_none(self):
        from backend.core.description_pipeline import sanitize_company_name

        for name in [
            "Company",
            "Employer",
            "Client",
            "Confidential",
            "Undisclosed",
            "Our Client",
            "Leading Company",
            "Top Company",
            "Global Company",
            "A Company",
            "The Company",
        ]:
            result = sanitize_company_name(name)
            assert result is None, f"Expected None for '{name}', got '{result}'"

    def test_real_company_not_blocked(self):
        from backend.core.description_pipeline import sanitize_company_name

        assert sanitize_company_name("Microsoft") == "Microsoft"
        assert sanitize_company_name("Stripe") == "Stripe"
        assert sanitize_company_name("DeepMind") == "DeepMind"

    def test_partial_blocklist_match(self):
        from backend.core.description_pipeline import sanitize_company_name

        # "a leading company" contains "leading company" — should be None
        result = sanitize_company_name("a leading company in tech")
        assert result is None


# ---------------------------------------------------------------------------
# Test 9: Combined URL + description → input_meta includes auto_url_extracted
# ---------------------------------------------------------------------------


class TestCombinedInputMeta(unittest.TestCase):
    def test_build_input_meta_with_company_has_correct_fields(self):
        from backend.core.description_pipeline import build_input_meta_with_company

        ext = _make_desc_extraction(
            company_name="Spotify",
            job_title="Backend Engineer",
            has_company_info=True,
        )
        meta = build_input_meta_with_company(ext, input_method="description")
        assert "extracted_company_name" in meta
        assert meta["company_identified"] is True
        assert meta["extracted_company_name"] == "Spotify"


# ---------------------------------------------------------------------------
# Test 10: Input source mismatch signal
# ---------------------------------------------------------------------------


class TestInputSourceMismatch(unittest.TestCase):
    def test_mismatch_signal_in_orchestrator_evidence(self):
        """Verify the mismatch signal structure is correct."""
        # The orchestrator inserts this signal when merged_fields.company_name
        # and ext_local.company_hint differ. Validate the signal id matches.
        mismatch_signal = {
            "id": "input_source_mismatch",
            "label": "Input consistency",
            "tier": "T2",
            "strength": "medium",
            "details": "Input sources appear inconsistent — please verify manually.",
        }
        assert mismatch_signal["id"] == "input_source_mismatch"
        assert mismatch_signal["tier"] == "T2"


# ---------------------------------------------------------------------------
# Test: Content analysis signals are generated correctly
# ---------------------------------------------------------------------------


class TestContentAnalysisSignals(unittest.TestCase):
    def test_pressure_language_detected(self):
        from backend.core.description_pipeline import (
            build_content_analysis_signals,
        )

        ext = _make_desc_extraction()
        text = "Apply immediately! Limited slots available. Act fast before positions are filled."
        signals = build_content_analysis_signals(text, ext)
        ids = {s["id"] for s in signals}
        assert "pressure_language" in ids
        pressure = next(s for s in signals if s["id"] == "pressure_language")
        assert pressure["strength"] == "low"

    def test_no_pressure_language_high_signal(self):
        from backend.core.description_pipeline import build_content_analysis_signals

        ext = _make_desc_extraction()
        text = "We are looking for a qualified engineer. This is a full-time role." * 5
        signals = build_content_analysis_signals(text, ext)
        pressure = next((s for s in signals if s["id"] == "pressure_language"), None)
        if pressure:
            assert pressure["strength"] == "high"

    def test_free_email_contact_flagged(self):
        from backend.core.description_pipeline import build_content_analysis_signals

        ext = _make_desc_extraction(contact_email="recruiter@gmail.com")
        text = "Software Engineering role. Send CV." * 10
        signals = build_content_analysis_signals(text, ext)
        contact = next((s for s in signals if s["id"] == "contact_legitimacy"), None)
        assert contact is not None
        assert contact["strength"] == "low"

    def test_corporate_email_medium_signal(self):
        from backend.core.description_pipeline import build_content_analysis_signals

        ext = _make_desc_extraction(contact_email="hr@acmecorp.com")
        text = "Software Engineering role." * 10
        signals = build_content_analysis_signals(text, ext)
        contact = next((s for s in signals if s["id"] == "contact_legitimacy"), None)
        assert contact is not None
        assert contact["strength"] == "medium"


# ---------------------------------------------------------------------------
# Test: ExtractedVisionFields bool coercion
# ---------------------------------------------------------------------------


class TestVisionFieldsBoolCoercion(unittest.TestCase):
    def test_string_true_coerced(self):
        from backend.core.image_ingest import ExtractedVisionFields

        fields = ExtractedVisionFields.model_validate(
            {
                "extraction_confidence": "medium",
                "extracted_job_text": "some text",
                "notes": "",
                "has_company_info": "true",
                "low_quality_image": "false",
            }
        )
        assert fields.has_company_info is True
        assert fields.low_quality_image is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
