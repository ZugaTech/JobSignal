"""Plain-language user copy — never expose internal scorer / tier jargon."""

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
    "TEXT_PATTERN_MATCH": "Strong patterns associated with low-trust postings were detected in the description (pattern match only, not a fraud claim).",
    "POLICY_CODE": "Additional policy detail is available to operators only.",
    "HARD_RED_FLAG": "High-risk patterns were detected in this posting.",
    "INCOMPLETE_EVIDENCE": "Evidence collection was partial; unable to build a complete profile.",
    "INSUFFICIENT_DATA": "Limited information was available for a full assessment.",
    "REC_SEARCH_EMPTY": "No cross-platform results were found for comparison.",
    "CONFIDENCE_LOW": "Evidence was too limited for a confident verdict.",
    "CONFIDENCE_MEDIUM": "Some signals were unclear; treat this result as a guide.",
    "INSUFFICIENT_CORROBORATION": "Not enough signals passed to confidently recommend applying. Some checks came back unclear.",
    "PREFER_POSTING_URL": "Add the job posting URL from the board or employer site when you can—checks are much stronger with the original listing link than with pasted text alone.",
    "GATES_PASSED": "We found strong corroborating evidence from official employer channels or verified job boards.",
    "T3_ONLY": "We found general web mentions, but could not confirm this role directly with the employer's official channels or trusted job boards.",
    "CONTRADICTION": "The posting page looked reachable, but employer-domain alignment was unclear.",
    "FETCH_INSUFFICIENT": "A URL was provided, but we could not fully verify the posting page.",
    "TEXT_RED_FLAGS": "The description alone showed some risk patterns; adding the posting URL would allow stronger checks.",
    "TEXT_ONLY_APPLY": "Based on the pasted description only, signals looked reasonable, but confidence is capped without a direct posting link.",
    "NO_URL_CORROBORATION": "No posting URL was provided, so employer-hosted sources could not be checked.",
    "HONESTY_LOW_CONFIDENCE": "Confidence was limited, so we kept a safer recommendation.",
    "HONESTY_GUARD": "Low confidence would contradict a strong apply recommendation; we defaulted to verify.",
    "POLICY_SKIP": "Automated policy blocked promoting this listing.",
    "NEXT_STEP": "Retry with the employer's official posting URL for stronger corroboration.",
    "IMAGE_INSUFFICIENT": "The screenshot did not contain enough readable job details.",
    "LOW_TRUST_PATTERN": "Text-only patterns are not conclusive; prefer an employer URL and verify again.",
    "TEXT_ONLY_NOT_CORROBORATED": "This is based on description text only; confirm on the employer's official careers page before applying.",
    "FETCH": "Primary page evidence was insufficient for a confident recommendation.",
    "SOURCES": "Evidence relies mostly on unverified secondary sources.",
    "POLICY": "Automated policy blocked further promotion to apply.",
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
        return "Signals look good. Proceed with confidence."
    if v == "SKIP":
        return "We recommend passing on this one."
    return "Check the official careers page before applying."


def build_fallback_llm_summary(report: Mapping[str, Any]) -> str:
    """Template fallback when LLM output is missing or unsafe — calm, non-robotic, no signal arithmetic."""

    v = str(report.get("verdict") or "VERIFY").upper()
    reasons = report.get("reasons") or []
    primary_plain = "Public evidence did not fully corroborate this listing."
    if isinstance(reasons, list) and reasons:
        r0 = reasons[0]
        if isinstance(r0, dict):
            primary_plain = plain_reason_for_code(str(r0.get("code") or "").strip())
        elif isinstance(r0, str) and r0.strip():
            primary_plain = scrub_internal_jargon(r0.strip(), replacement="Public evidence did not fully corroborate this listing.")
    primary_plain = scrub_internal_jargon(primary_plain, replacement="Public evidence did not fully corroborate this listing.")
    base = primary_plain.rstrip(".")
    if v == "APPLY":
        return f"{base}. Cross-check title and location on the employer's official posting before you share personal details."
    if v == "SKIP":
        return f"{base}. Unless new facts surface, we would not invest further effort here."
    return (
        f"{base}. This cautious stance is deliberate—confirm the role on the company's official careers channel "
        "before you spend meaningful time on an application."
    )
