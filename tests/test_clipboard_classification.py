"""Mirror frontend clipboard classification + extension payload decode (see frontend/app.js)."""

from __future__ import annotations

import base64
import re
import urllib.parse

JOB_URL_PATTERN = re.compile(
    r"^https?:\/\/.*(linkedin\.com\/jobs|indeed\.com|glassdoor\.com\/job|greenhouse\.io|lever\.co|workday|wellfound\.com|jobvite|smartrecruiters|ashbyhq|bamboohr)",
    re.I,
)

JOB_DESCRIPTION_KEYWORDS = [
    "responsibilities",
    "requirements",
    "qualifications",
    "experience",
    "salary",
    "compensation",
    "apply",
    "hiring",
    "position",
    "role",
    "full-time",
    "part-time",
    "remote",
    "on-site",
    "hybrid",
    "benefits",
]


def count_job_keywords(text: str) -> int:
    lower = text.lower()
    return sum(1 for k in JOB_DESCRIPTION_KEYWORDS if k in lower)


def classify_clipboard_content(text: str) -> str:
    if re.match(r"^https?:\/\/", text, re.I):
        if JOB_URL_PATTERN.match(text):
            return "JOB_URL"
        return "OTHER_URL"
    if len(text) > 100:
        if count_job_keywords(text) >= 3:
            return "JOB_DESCRIPTION"
    return "UNKNOWN"


def test_classify_job_url_linkedin():
    u = "https://www.linkedin.com/jobs/view/123456789/"
    assert classify_clipboard_content(u) == "JOB_URL"


def test_classify_job_description_three_keywords():
    blob = (
        "We are hiring a senior engineer. Responsibilities include shipping features. "
        "Requirements: Python experience. Salary competitive. Apply today with your resume. "
        "This role is full-time and remote." + (" padding text." * 20)
    )
    assert len(blob) > 100
    assert classify_clipboard_content(blob) == "JOB_DESCRIPTION"


def test_classify_unknown_short():
    assert classify_clipboard_content("hello world") == "UNKNOWN"


def test_extension_job_description_encoding_roundtrip():
    """popup.js uses btoa(encodeURIComponent(jobDescription)); web decodes decodeURIComponent(atob(b64))."""
    text = "Salary: €80k\nResponsibilities: build APIs — apply today!"
    quoted = urllib.parse.quote(text, safe="")
    b64 = base64.b64encode(quoted.encode("ascii")).decode("ascii")
    decoded = urllib.parse.unquote(base64.b64decode(b64).decode("ascii"))
    assert decoded == text


def test_dismissed_list_blocks_reprompt_logic():
    dismissed: list[str] = []
    trimmed = "same clipboard payload"
    assert trimmed not in dismissed
    dismissed.append(trimmed)
    assert trimmed in dismissed


def test_classify_other_url_not_job_board():
    assert classify_clipboard_content("https://example.com/careers/foo") == "OTHER_URL"
