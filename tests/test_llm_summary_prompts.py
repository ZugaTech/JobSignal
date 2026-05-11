from backend.core.orchestrator import build_verdict_summary_messages


def test_verdict_summary_prompt_keeps_instructions_in_system_only():
    messages = build_verdict_summary_messages(
        verdict="VERIFY",
        confidence_band="medium",
        company_name="Deloitte",
        findings=["Cross-platform freshness is weak.", "Employer-domain verification is strong."],
    )
    assert messages[0]["role"] == "system"
    assert "respond with the summary only" in messages[0]["content"].lower()
    assert "start directly with the advice" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "i need to write" not in messages[1]["content"].lower()
    assert "write exactly" not in messages[1]["content"].lower()
    assert "verdict=verify" in messages[1]["content"].lower()
