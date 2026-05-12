"""Detect model / paste monologue that must never become employer names or Serper query terms."""

from __future__ import annotations

from backend.core.prompt_guard import is_prompt_leak

_EMPLOYER_LLM_NOISE_MARKERS: tuple[str, ...] = (
    "let me look",
    "let me read",
    "provided text",
    "carefully, so",
    "i'll analyze",
    "i will analyze",
    "chain of thought",
    "looking at the",
    "based on my analysis",
    "first, i need",
    "as a language model",
    "i should note",
    "step-by-step",
    "the assistant",
    "here is the",
    "wait,",
)


def employer_label_is_llm_noise(name: str) -> bool:
    """True when ``name`` is instruction-like monologue, not a real employer or job title."""

    if not name or not str(name).strip():
        return False
    s = str(name).strip()
    if len(s) > 140:
        return True
    low = s.lower()
    if low.startswith("let me ") or low.startswith("i'll ") or low.startswith("i will "):
        return True
    if any(m in low for m in _EMPLOYER_LLM_NOISE_MARKERS):
        return True
    if is_prompt_leak(s):
        return True
    return False
