"""Regression: prompt-leak heuristics must not reject benign reputation prose."""

from backend.core.llm_safe import _looks_like_prompt_leak


def test_task_paraphrase_opening_not_treated_as_leak() -> None:
    assert not _looks_like_prompt_leak(
        "The user wants a 2-3 sentence employer reputation briefing for Deloitte."
    )


def test_explicit_instruction_echo_still_flagged() -> None:
    assert _looks_like_prompt_leak("The user wants you to return only APPLY or VERIFY.")


def test_briefing_style_paragraph_not_leak() -> None:
    txt = (
        "The user wants a 2-sentence briefing about Deloitte. "
        "Here is the summary: Deloitte is a global professional services firm."
    )
    assert not _looks_like_prompt_leak(txt)
