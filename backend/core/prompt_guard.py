"""Heuristic prompt-injection risk assessment for untrusted job text (Sprint 4).

This does **not** prove safety; it surfaces high-risk patterns for orchestrators
to downgrade to VERIFY or strip before optional LLM calls.
"""

from __future__ import annotations

import re
from typing import Any, List, Literal, Optional, Tuple

_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "system prompt",
    "you are now",
    "developer message",
    "override instructions",
    "new instructions:",
    "sudo mode",
    "jailbreak",
)

_CONTROL_TOKEN = re.compile(r"```\s*system|<<\s*sys|</?\s*system\s*>", re.I)


def assess_prompt_injection_risk(text: str) -> Tuple[Literal["low", "medium", "high"], List[str]]:
    """Return risk band and human-readable findings (codes + snippets are redacted)."""

    lower = text.lower()
    findings: List[str] = []
    hits = 0
    for m in _MARKERS:
        if m in lower:
            hits += 1
            findings.append(f"marker:{m.split()[0]}")

    if _CONTROL_TOKEN.search(text):
        hits += 2
        findings.append("marker:control_tags")

    if hits >= 3:
        return "high", findings
    if hits >= 1:
        return "medium", findings
    return "low", findings


def extract_chat_completion_message_text(resp: Any) -> Optional[str]:
    """Extract assistant text from an OpenAI-compatible chat completion response."""
    try:
        choices = getattr(resp, "choices", None)
        if not choices:
            return None
        msg = getattr(choices[0], "message", None)
        if msg is None:
            return None
        raw = getattr(msg, "content", None)
    except (IndexError, AttributeError, TypeError):
        return None

    if raw is None:
        return None
    if isinstance(raw, str):
        out = raw.strip()
        return out if out else None
    if isinstance(raw, list):
        parts: List[str] = []
        for part in raw:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(str(part["text"]))
            else:
                t = getattr(part, "text", None)
                if t:
                    parts.append(str(t))
        joined = " ".join(parts).strip()
        return joined if joined else None
    out = str(raw).strip()
    return out if out else None


def _echoes_verdict_summary_user_message(text: str) -> bool:
    """True when the model echoed our structured verify briefing user message."""
    t = text.strip()
    if not t.startswith("Decision:"):
        return False
    head = t[:800]
    return "Confidence:" in head and ("Signals:" in head or "Reputation:" in head)


def _echoes_reputation_user_message(text: str) -> bool:
    """True when the model echoed our reputation summary user message."""
    t = text.strip()
    if not t.startswith("Company:"):
        return False
    return "\nData:\n" in t[:1200] or t.startswith("Company:\nData:\n")


def is_prompt_leak(text: str) -> bool:
    """Detect prompt / instruction leaks or invalid echoed payloads before showing LLM text in the UI."""
    if not text:
        return False

    leak_markers = [
        "The user wants",
        "Key constraints",
        "Data provided",
        "Wait, there's",
        "Constraints:",
        "Instructions:",
    ]
    if any(marker in text for marker in leak_markers):
        return True

    if _echoes_verdict_summary_user_message(text) or _echoes_reputation_user_message(text):
        return True

    # Long preamble without sentence punctuation in the opening — likely instructions, not a user-facing summary.
    if len(text) > 800 and "." not in text[:100] and "!" not in text[:100] and "?" not in text[:100]:
        return True

    return False
