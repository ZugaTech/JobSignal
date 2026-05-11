"""Plain-language user copy: never expose internal scorer or tier jargon."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping

# Substrings that must never appear in user-facing strings (case-insensitive).
_INTERNAL_SUBSTRINGS = (
    "t1 medium",
    "t2 high",
    "apply gates",
    "did not meet apply",
    "need t1",
    "need t2",
    "with support",
    " medium+",
    "high with support",
    "verify gates",
    "apply gate",
    "honesty guard",
    "path a",
    "path b",
    "path c",
    "t3_only",
    "tier t1",
    "tier t2",
    "tier t3",
    "decision:",
    "confidence:",
    "signals:",
    "company_reputation_signal",
    "fetch_ok",
    "domain_align",
    "careers_page_match",
    "careers_domain_match",
    "staleness_flag",
    "first_seen_estimate",
    "cross_platform_freshness",
    "posting_duplication_signal",
    "company_registry_presence",
    "company_linkedin_presence",
)


def contains_internal_verdict_jargon(text: str) -> bool:
    if not text:
        return False
    tl = text.lower()
    for frag in _INTERNAL_SUBSTRINGS:
        if frag in tl:
            return True
    if re.search(r"\bgates?\b", tl) and ("apply" in tl or "verify" in tl or "verdict" in tl or "signal" in tl):
        return True
    if re.search(r"\btier\b", tl) and ("t1" in tl or "t2" in tl or "t3" in tl):
        return True
    if re.search(r"\bt[123]\b", tl):
        return True
    # Model occasionally echoes internal-style signal IDs in summaries.
    if re.search(r"\b[a-z]+_[a-z0-9_]+\b", tl) and ("signal" in tl or "signals:" in tl):
        return True
    return False


def scrub_internal_jargon(text: str, *, replacement: str) -> str:
    """If jargon detected, return replacement; else original stripped."""

    s = (text or "").strip()
    if not s or contains_internal_verdict_jargon(s):
        return replacement
    return s


# Authoritative plain explanations by reason code (internal codes only).
REASON_PLAIN_BY_CODE: Dict[str, str] = {
    "TEXT_PATTERN_MATCH": "The description matched patterns we often see on low-trust posts. That is a pattern match only, not a fraud claim.",
    "POLICY_CODE": "Additional policy detail is available to operators only.",
    "HARD_RED_FLAG": "We spotted high-risk patterns in this posting.",
    "INCOMPLETE_EVIDENCE": "We only gathered part of the picture for this role.",
    "INSUFFICIENT_DATA": "There was not enough here to judge the posting fully.",
    "REC_SEARCH_EMPTY": "We did not find other public listings to compare against.",
    "CONFIDENCE_LOW": "Public evidence was thin, so we could not be confident.",
    "CONFIDENCE_MEDIUM": "Some checks were unclear. Use this as a guide, not a guarantee.",
    "INSUFFICIENT_CORROBORATION": "Not enough checks lined up to say \"apply\" with confidence. A few items were unclear.",
    "PREFER_POSTING_URL": "If you can, add the real job link from the board or employer site. Checks are stronger with the listing URL than with pasted text alone.",
    "GATES_PASSED": "Employer or trusted job-board sources backed this listing well.",
    "T3_ONLY": "We saw general web mentions, but we could not tie this role to the employer's official channels or trusted boards.",
    "CONTRADICTION": "The page loaded, but employer domain alignment was fuzzy.",
    "FETCH_INSUFFICIENT": "We had a URL, but we could not fully verify the posting page.",
    "TEXT_RED_FLAGS": "The pasted text alone raised some risk flags. A posting URL would unlock stronger checks.",
    "TEXT_ONLY_APPLY": "From the pasted text alone, things looked okay, but we cap confidence without a direct listing link.",
    "NO_URL_CORROBORATION": "No posting URL was given, so we could not check employer-hosted sources.",
    "HONESTY_LOW_CONFIDENCE": "Confidence was low, so we steered toward a safer call.",
    "HONESTY_GUARD": "Low confidence would clash with a strong \"apply\" call, so we chose verify instead.",
    "POLICY_SKIP": "Policy blocked us from recommending this listing.",
    "NEXT_STEP": "Try again with the employer's official posting URL for stronger checks.",
    "IMAGE_INSUFFICIENT": "The screenshot did not have enough readable job details.",
    "LOW_TRUST_PATTERN": "Text-only clues are not enough to be sure. Prefer a real employer URL and run verify again.",
    "TEXT_ONLY_NOT_CORROBORATED": "This is from pasted text only. Confirm on the employer careers page before you apply.",
    "FETCH": "We could not lean on the posting page enough to be confident.",
    "SOURCES": "Most of what we saw came from secondary sources we could not fully trust.",
    "POLICY": "Policy blocked us from pushing this toward apply.",
}


def plain_reason_for_code(code: str) -> str:
    key = (code or "").strip()
    if not key:
        return "Not enough verified information was available to complete this check."
    if key in REASON_PLAIN_BY_CODE:
        return REASON_PLAIN_BY_CODE[key]
    lk = key.lower()
    for k, v in REASON_PLAIN_BY_CODE.items():
        if k.lower() == lk:
            return v
    return key.replace("_", " ").title().strip() + "."


def human_reason_warning_line(*, code: str, message: str) -> str:
    """Prefer the scorer/API message when jargon-safe; else catalog copy by code."""

    c = (code or "").strip()
    m = (message or "").strip()
    fallback = plain_reason_for_code(c) if c else plain_reason_for_code("")
    if m:
        return scrub_internal_jargon(m, replacement=fallback)
    return fallback


def signal_pass_fail_counts(report: Mapping[str, Any]) -> tuple[int, int]:
    """Count trust_signals as passed vs flagged for fallback copy."""

    ts = report.get("trust_signals") or []
    passed = 0
    failed = 0
    if isinstance(ts, list) and ts:
        for row in ts:
            if not isinstance(row, dict):
                continue
            st = str(row.get("status") or "").strip().lower()
            if st in ("strong match", "partial match", "verified", "pass"):
                passed += 1
            else:
                failed += 1
        return passed, failed

    signals = report.get("signals") or []
    if isinstance(signals, list):
        internal = {"url_canonical", "input_text_only"}
        for s in signals:
            if not isinstance(s, dict):
                continue
            if str(s.get("id") or "") in internal:
                continue
            st = str(s.get("strength") or "").lower()
            if st in ("high", "medium"):
                passed += 1
            else:
                failed += 1
    return passed, failed


def call_to_action_for_verdict(verdict: str) -> str:
    v = (verdict or "VERIFY").upper()
    if v == "APPLY":
        return "Looks reasonable from what we saw. Still double-check the official listing before you share personal info."
    if v == "SKIP":
        return "We would skip this one unless something important changes."
    return "Open the employer careers site and confirm the role before you spend real time on it."


def build_fallback_llm_summary(report: Mapping[str, Any]) -> str:
    """Template fallback when LLM output is missing or unsafe — calm, non-robotic, no signal arithmetic."""

    v = str(report.get("verdict") or "VERIFY").upper()
    reasons = report.get("reasons") or []
    primary_plain = "Public sources did not fully back this listing."
    if isinstance(reasons, list) and reasons:
        r0 = reasons[0]
        if isinstance(r0, dict):
            primary_plain = plain_reason_for_code(str(r0.get("code") or "").strip())
        elif isinstance(r0, str) and r0.strip():
            primary_plain = scrub_internal_jargon(r0.strip(), replacement="Public sources did not fully back this listing.")
    primary_plain = scrub_internal_jargon(primary_plain, replacement="Public sources did not fully back this listing.")
    base = primary_plain.rstrip(".")
    if v == "APPLY":
        return f"{base}. Match the title and location on the employer's official posting before you share personal details."
    if v == "SKIP":
        return f"{base}. Unless something big changes, we would not keep chasing this one."
    return (
        f"{base}. Take a minute on the company careers site to confirm the role is real before you sink time into an application."
    )
