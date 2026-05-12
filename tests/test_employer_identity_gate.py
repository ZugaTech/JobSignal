import pytest

from backend.core.job_url_shortcuts import resolve_employer_identity
from backend.core.response_contract import validate_and_repair_response
from backend.evidence.company_reviews import get_company_reviews


class CountingCoordinator:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = 0

    async def search(self, *_args, **_kwargs):
        self.calls += 1
        return self.rows


def test_ambiguous_job_board_url_does_not_resolve_wrong_employer_entity():
    resolved = resolve_employer_identity(
        is_job_board_url=True,
        hardened_candidate="Example Careers",
        heuristic_candidate="Data Analyst",
    )

    assert resolved.name is None
    assert resolved.confirmed is False
    assert resolved.confidence in {"ambiguous", "weak", "none"}


def test_job_board_requires_confirmed_employer_before_reputation():
    resolved = resolve_employer_identity(
        is_job_board_url=True,
        hardened_candidate="Indeed",
        heuristic_candidate="Remote Software Engineer",
    )

    assert resolved.name is None
    assert resolved.confirmed is False


def test_job_board_confirms_when_structured_company_from_pasted_text():
    """Explicit employer in pasted body (same signal we now feed as structured_company)."""
    resolved = resolve_employer_identity(
        is_job_board_url=True,
        structured_candidate="Contoso Robotics",
        hardened_candidate=None,
        heuristic_candidate="Contoso Robotics",
    )
    assert resolved.confirmed is True
    assert resolved.name == "Contoso Robotics"


def test_job_board_confirms_hardened_name_when_only_extraction_signal():
    """LinkedIn/Indeed pages often yield a single LLM-hardened employer name — still run reputation."""
    resolved = resolve_employer_identity(
        is_job_board_url=True,
        structured_candidate=None,
        url_domain_candidate=None,
        hardened_candidate="Contoso Robotics",
        heuristic_candidate=None,
    )
    assert resolved.confirmed is True
    assert resolved.name == "Contoso Robotics"


def test_job_board_rejects_llm_monologue_as_hardened_employer():
    resolved = resolve_employer_identity(
        is_job_board_url=True,
        structured_candidate=None,
        url_domain_candidate=None,
        hardened_candidate="Let me look through the provided text carefully",
        heuristic_candidate=None,
    )
    assert resolved.confirmed is False
    assert resolved.name is None


@pytest.mark.asyncio
async def test_reputation_hidden_when_employer_unconfirmed():
    coord = CountingCoordinator(
        [{"title": "Acme Glassdoor Reviews", "snippet": "Acme has great culture.", "link": "https://glassdoor.com"}]
    )

    res = await get_company_reviews(coord, "Acme", employer_confirmed=False)

    assert coord.calls == 0
    assert res.status == "employer_unconfirmed"
    assert res.review_confidence_score is None
    assert res.plain_summary == ""


def test_verify_response_does_not_show_inflated_employer_coverage_when_unconfirmed():
    raw = {
        "verdict": "VERIFY",
        "confidence_score": 82,
        "confidence_label": "High",
        "trust_signals": [],
        "signals": [],
        "reasons": ["Posting needs manual confirmation."],
        "warnings": [],
        "llm_summary": "Posting needs manual confirmation.",
        "review_summary": {
            "status": "employer_unconfirmed",
            "review_confidence_score": 100,
            "plain_summary": "Based on many sources, WrongCo has a strong employer reputation.",
        },
        "company_legitimacy_score": 100,
        "cache": {"hit": False},
        "report_schema_version": "2.0.0",
        "request_id": "00000000-0000-4000-8000-000000000010",
    }

    out = validate_and_repair_response(raw, request_id="x")

    assert out["review_summary"]["review_confidence_score"] is None
    assert out["review_summary"]["plain_summary"] == ""
    assert out["company_legitimacy_score"] < 67
    assert out["meta"]["employer_identity_confirmed"] is False


@pytest.mark.asyncio
async def test_known_valid_employer_still_shows_reputation_normally():
    coord = CountingCoordinator(
        [
            {
                "title": "Acme Corp Glassdoor Reviews",
                "snippet": "Acme Corp rating: 4.5. Great culture and highly recommend.",
                "link": "https://glassdoor.com/reviews/acme",
            },
            {
                "title": "Acme Corp Indeed Reviews",
                "snippet": "Acme Corp rating: 4.2. Good perks and supportive team.",
                "link": "https://indeed.com/cmp/acme/reviews",
            },
        ]
    )

    res = await get_company_reviews(coord, "Acme Corp", employer_confirmed=True)

    assert res.status == "ok"
    assert res.review_confidence_score is not None
    assert res.sources_found >= 1
    assert "Acme Corp" in res.plain_summary
