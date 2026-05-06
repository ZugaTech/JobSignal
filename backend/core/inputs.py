"""Raw URL and pasted-text validation before normalization (Sprint 4)."""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlparse

MAX_URL_CHARS = 2048
MAX_TEXT_CHARS = 100_000
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class InputValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_verify_inputs(
    job_url: Optional[str],
    job_text: Optional[str],
    *,
    has_image: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Return stripped ``(url, text)`` or raise ``InputValidationError``.

    Without an image, at least one of URL or text must be present. With an image,
    URL and text may both be absent (screenshot-only).
    """

    url = job_url.strip() if job_url else None
    text = job_text.strip() if job_text else None

    if url == "":
        url = None
    if text == "":
        text = None

    if url is None and text is None and not has_image:
        raise InputValidationError("EMPTY", "Provide a job URL and/or pasted job description.")

    if url is not None:
        if len(url) > MAX_URL_CHARS:
            raise InputValidationError("URL_TOO_LONG", f"URL exceeds {MAX_URL_CHARS} characters.")
        if "\x00" in url:
            raise InputValidationError("URL_NUL", "URL contains disallowed NUL bytes.")
        parsed = urlparse(url)
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            raise InputValidationError("URL_SCHEME", "Only http and https URLs are allowed.")
        if not parsed.netloc:
            raise InputValidationError("URL_HOST", "URL must include a host.")

    if text is not None:
        if len(text) > MAX_TEXT_CHARS:
            raise InputValidationError("TEXT_TOO_LONG", f"Description exceeds {MAX_TEXT_CHARS} characters.")
        if "\x00" in text:
            raise InputValidationError("TEXT_NUL", "Description contains disallowed NUL bytes.")

    return url, text


def validate_raw_job_inputs(job_url: Optional[str], job_text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Backward-compatible alias: no image; requires URL and/or text."""

    return validate_verify_inputs(job_url, job_text, has_image=False)
