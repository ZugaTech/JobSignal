"""human_reason_warning_line prefers safe scorer messages over generic catalog copy."""

from backend.core.user_copy import human_reason_warning_line, plain_reason_for_code


def test_human_line_prefers_message_when_safe():
    msg = "Paste the posting URL when you can — we could not check the listing page without it."
    out = human_reason_warning_line(code="PREFER_POSTING_URL", message=msg)
    assert out == msg


def test_human_line_falls_back_when_message_has_jargon():
    bad = "Did not meet APPLY gates: need T1 medium+ with support."
    out = human_reason_warning_line(code="INSUFFICIENT_CORROBORATION", message=bad)
    assert out == plain_reason_for_code("INSUFFICIENT_CORROBORATION")


def test_human_line_uses_catalog_when_no_message():
    out = human_reason_warning_line(code="PREFER_POSTING_URL", message="")
    assert "URL" in out or "url" in out


def test_human_line_fetch_retry_browser_ua_catalog():
    out = human_reason_warning_line(code="FETCH_RETRY_BROWSER_UA", message="")
    assert "browser" in out.lower() or "profile" in out.lower()
