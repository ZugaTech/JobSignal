"""Tests for jd_signals JSON parsing and ``build_llm_signals`` wiring."""

import json

import pytest

from backend.core.llm_fireworks import (
    build_llm_signals,
    jd_signals_parse_model_content,
)


FB = '{"specificity":"low","red_flags":[],"missing_fields":[],"notes":"Unavailable."}'


def test_jd_signals_parse_clean_json_object():
    raw = '{"specificity":"medium","red_flags":[],"missing_fields":["salary"],"notes":"Role described."}'
    out = jd_signals_parse_model_content(raw, fallback=FB)
    assert json.loads(out)["specificity"] == "medium"
    assert "salary" in json.loads(out)["missing_fields"]


def test_jd_signals_parse_strips_instruction_parroting_preamble():
    raw = (
        "The user wants me to analyze a job description and extract only what is explicitly stated, returning JSON.\n"
        '{"specificity":"high","red_flags":[],"missing_fields":[],"notes":"Explicit duties listed."}'
    )
    out = jd_signals_parse_model_content(raw, fallback=FB)
    data = json.loads(out)
    assert data["specificity"] == "high"
    assert data["notes"] == "Explicit duties listed."


def test_jd_signals_parse_no_user_wants_style_intros_in_output_keys():
    raw = (
        'Sure.\n{"specificity":"low","red_flags":["no_company_info"],"missing_fields":[],"notes":"Company name absent."}'
    )
    out = jd_signals_parse_model_content(raw, fallback=FB)
    data = json.loads(out)
    assert data["red_flags"] == ["no_company_info"]


def test_jd_signals_parse_markdown_fence():
    raw = '```json\n{"specificity":"medium","red_flags":[],"missing_fields":[],"notes":"Ok."}\n```'
    out = jd_signals_parse_model_content(raw, fallback=FB)
    assert json.loads(out)["notes"] == "Ok."


def test_jd_signals_parse_invalid_returns_fallback():
    raw = "not json at all"
    assert jd_signals_parse_model_content(raw, fallback=FB) == FB


def test_jd_signals_parse_missing_specificity_returns_fallback():
    raw = '{"red_flags":[],"missing_fields":[],"notes":"x"}'
    assert jd_signals_parse_model_content(raw, fallback=FB) == FB


@pytest.fixture
def enable_llm_signals_for_tests(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_SIGNALS", "1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "sk-test-placeholder")


@pytest.mark.usefixtures("enable_llm_signals_for_tests")
def test_build_llm_signals_happy_path_mocked_completion(monkeypatch):
    monkeypatch.setattr(
        "backend.core.llm_fireworks._jd_signals_chat_completion_json",
        lambda **kw: '{"specificity":"medium","red_flags":["vague_responsibilities"],'
        '"missing_fields":["salary"],"notes":"Sparse posting."}',
    )
    r = build_llm_signals(job_text="Engineer needed. Apply now.")
    ids = {s["id"] for s in r.signals}
    assert "jd_specificity" in ids
    assert "jd_red_flags" in ids
    assert "jd_missing_fields" in ids
    assert not r.warnings
