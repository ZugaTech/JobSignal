"""Heuristic prompt-injection risk assessment for untrusted job text (Sprint 4).

This does **not** prove safety; it surfaces high-risk patterns for orchestrators
to downgrade to VERIFY or strip before optional LLM calls.
"""

from __future__ import annotations

import re
from typing import List, Literal, Tuple

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
