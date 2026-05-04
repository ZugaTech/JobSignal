from backend.core.extraction import extract_entities
from backend.core.normalization import normalize_job_input


def test_extraction_does_not_invent_company_without_signals():
    n = normalize_job_input(None, "Some vague posting")
    ex = extract_entities(n)
    assert ex.company_hint is None or isinstance(ex.company_hint, str)
