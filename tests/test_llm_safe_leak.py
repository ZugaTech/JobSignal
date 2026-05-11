"""Regression: prompt-leak heuristics must not reject benign reputation prose."""

from backend.core.llm_safe import _looks_like_prompt_leak, _strip_llm_meta_preface


def test_task_paraphrase_opening_not_treated_as_leak() -> None:
    assert not _looks_like_prompt_leak(
        "The user wants a 2-3 sentence employer reputation briefing for Deloitte."
    )


def test_explicit_instruction_echo_still_flagged() -> None:
    assert _looks_like_prompt_leak("The user wants you to return only APPLY or VERIFY.")


def test_briefing_style_paragraph_with_summary_preamble_is_leak() -> None:
    txt = (
        "The user wants a 2-sentence briefing about Deloitte. "
        "Here is the summary: Deloitte is a global professional services firm."
    )
    assert _looks_like_prompt_leak(txt)


def test_tier_one_prose_not_flagged_as_leak() -> None:
    assert not _looks_like_prompt_leak("Deloitte is a tier-one employer with strong audit practices.")


def test_job_seeker_address_not_flagged_as_leak() -> None:
    """Bare \"you are a ...\" is common in legitimate briefing copy; must not match leak markers."""
    assert not _looks_like_prompt_leak(
        "You are a strong candidate if your profile aligns with Deloitte consulting norms."
    )


def test_meta_then_you_are_a_candidate_not_flagged() -> None:
    full = (
        "The user wants a 2-sentence briefing for a job seeker about Deloitte, based on the provided signals. "
        "You are a job seeker evaluating risk—cross-check this posting on Deloitte careers before investing time."
    )
    assert not _looks_like_prompt_leak(full)


def test_assistant_identity_echo_still_flagged() -> None:
    assert _looks_like_prompt_leak("You are a helpful assistant; here is the APPLY verdict.")


def test_strip_meta_preface_keeps_substance() -> None:
    raw = (
        "The user wants a 2-sentence briefing about Deloitte, based on the provided signals. "
        "Verify this role on Deloitte careers before applying."
    )
    stripped = _strip_llm_meta_preface(raw)
    assert stripped.startswith("Verify")
    assert "user wants" not in stripped.lower()
