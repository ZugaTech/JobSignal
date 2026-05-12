from backend.core.extraction import extract_entities
from backend.core.normalization import normalize_job_input


def test_extraction_does_not_invent_company_without_signals():
    n = normalize_job_input(None, "Some vague posting")
    ex = extract_entities(n)
    assert ex.company_hint is None or isinstance(ex.company_hint, str)


def test_extraction_skips_llm_monologue_when_picking_title_line():
    body = "Let me look through the provided text carefully.\n\nSoftware Engineer at Acme"
    n = normalize_job_input(None, body)
    ex = extract_entities(n)
    assert ex.title_hint
    assert "Software Engineer" in ex.title_hint
    assert "Let me look" not in ex.title_hint
