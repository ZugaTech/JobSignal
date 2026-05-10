"""Rule-first scoring and verdict selection (Sprint 3).

Adds:
- Layer scores (company legitimacy / posting authenticity / freshness)
- Coverage-aware confidence ceilings
- Honest uncertainty pathway as first-class output
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple, cast

from backend.core.decision_schema import DecisionResponse, ReasonItem, SignalEvidence, Verdict, WarningItem
from backend.core.source_evidence import _strength_rank, sort_evidence_by_trust

SCORER_VERSION = "3.2.2"

_SEVERE_SCAM_TOKENS = (
    "training_fee",
    "payment_required",
    "payment_up_front",
    "telegram_only_contact",
    "whatsapp_only_contact",
    "personal_email_recruiter",
    "identity_bait",
    "wire_transfer",
    "crypto_payment",
)


def _get_signal(signals: List[Mapping[str, Any]], sid: str) -> Optional[Mapping[str, Any]]:
    for s in signals:
        if str(s.get("id")) == sid:
            return s
    return None


def _sig_strength(signals: List[Mapping[str, Any]], sid: str) -> str:
    s = _get_signal(signals, sid)
    return str(s.get("strength", "none")) if s else "none"


def _sig_details(signals: List[Mapping[str, Any]], sid: str) -> str:
    s = _get_signal(signals, sid)
    return str(s.get("details", "")) if s else ""


def _best_strength_in_tier(signals: List[Mapping[str, Any]], tier: str) -> str:
    strengths = [str(s.get("strength", "none")) for s in signals if str(s.get("tier")) == tier]
    if not strengths:
        return "none"
    return min(strengths, key=lambda st: _strength_rank(st))


def _count_strength_at_least(signals: List[Mapping[str, Any]], minimum: str) -> int:
    mrank = _strength_rank(minimum)
    return sum(1 for s in signals if _strength_rank(str(s.get("strength", "none"))) <= mrank)


def _has_t1_medium_plus(signals: List[Mapping[str, Any]]) -> bool:
    return any(str(s.get("tier")) == "T1" and str(s.get("strength", "none")) in ("high", "medium") for s in signals)


def _has_t2_high(signals: List[Mapping[str, Any]]) -> bool:
    return any(str(s.get("tier")) == "T2" and str(s.get("strength", "none")) == "high" for s in signals)


def _has_severe_token(text: str) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in _SEVERE_SCAM_TOKENS)


def _severe_text_pattern_skip(signals: List[Mapping[str, Any]], *, url_provided: bool) -> bool:
    official = _get_signal(signals, "official_careers_page")
    dup_risk = _get_signal(signals, "duplicate_repost_risk")
    if not official and dup_risk:
        return True

    if url_provided:
        return False
    scam_st = _sig_strength(signals, "jd_scam_indicators")
    red_st = _sig_strength(signals, "jd_red_flags")
    farm_st = _sig_strength(signals, "jd_content_farm_score")
    token_present = _has_severe_token(_sig_details(signals, "jd_scam_indicators"))

    conditions = 0
    if scam_st == "high":
        conditions += 1
    if red_st == "high":
        conditions += 1
    if farm_st == "high":
        conditions += 1
    if token_present:
        conditions += 1
    return conditions >= 2


def _text_only_apply_combo(signals: List[Mapping[str, Any]], *, url_provided: bool) -> bool:
    if url_provided:
        return False
    if _sig_strength(signals, "jd_specificity") != "high":
        return False
    if _sig_strength(signals, "jd_employer_identifiability") != "high":
        return False
    if _sig_strength(signals, "jd_recruiter_intent_score") not in ("high", "medium"):
        return False
    scam_st = _sig_strength(signals, "jd_scam_indicators")
    if scam_st not in ("none", "low"):
        return False
    if _has_severe_token(_sig_details(signals, "jd_scam_indicators")):
        return False
    if _sig_strength(signals, "jd_ai_generated_score") not in ("none", "low"):
        return False
    if _sig_strength(signals, "jd_content_farm_score") not in ("none", "low"):
        return False
    if _sig_strength(signals, "jd_red_flags") not in ("none", "low"):
        return False
    return True


def _contradiction_fetch_without_domain(signals: List[Mapping[str, Any]], url_provided: bool) -> bool:
    if not url_provided:
        return False
    fetch = _get_signal(signals, "fetch_ok")
    dom = _get_signal(signals, "domain_align")
    fetch_st = str(fetch.get("strength", "none")) if fetch else "none"
    dom_st = str(dom.get("strength", "none")) if dom else "none"
    return fetch_st in ("high", "medium") and dom_st == "none"


def _fetch_insufficient_for_apply(signals: List[Mapping[str, Any]], url_provided: bool) -> bool:
    if not url_provided:
        return False
    fetch = _get_signal(signals, "fetch_ok")
    if not fetch:
        return True
    return str(fetch.get("strength", "none")) not in ("high", "medium")


def _t3_only_loudest(signals: List[Mapping[str, Any]]) -> bool:
    t1 = _best_strength_in_tier(signals, "T1")
    t2 = _best_strength_in_tier(signals, "T2")
    t3 = _best_strength_in_tier(signals, "T3")
    if t3 != "high":
        return False
    if t1 not in ("none", "low"):
        return False
    if t2 not in ("none", "low"):
        return False
    return True


def _apply_path(signals: List[Mapping[str, Any]]) -> bool:
    official = _get_signal(signals, "official_careers_page")
    if not official:
        return False
    if _get_signal(signals, "duplicate_repost_risk"):
        return False
    t1_best = _best_strength_in_tier(signals, "T1")
    t2_best = _best_strength_in_tier(signals, "T2")
    medium_plus = _count_strength_at_least(signals, "medium")
    path_a = t1_best in ("high", "medium") and _has_t1_medium_plus(signals) and medium_plus >= 2
    path_b = t2_best == "high" and _has_t2_high(signals) and medium_plus >= 2
    return path_a or path_b


def _internal_score(signals: List[Mapping[str, Any]], url_provided: bool) -> int:
    score = 0
    t1 = _best_strength_in_tier(signals, "T1")
    t2 = _best_strength_in_tier(signals, "T2")
    t3 = _best_strength_in_tier(signals, "T3")
    for _tier, best, pts in (("T1", t1, 40), ("T2", t2, 30), ("T3", t3, 15)):
        if best == "high":
            score += pts
        elif best == "medium":
            score += int(pts * 0.65)
        elif best == "low":
            score += int(pts * 0.35)
    if _count_strength_at_least(signals, "medium") >= 2:
        score += 20
    if url_provided:
        fetch = _get_signal(signals, "fetch_ok")
        if fetch and str(fetch.get("strength")) in ("high", "medium"):
            score += 15
    return max(0, min(100, score))


def _confidence_band(
    verdict: Verdict,
    signals: List[Mapping[str, Any]],
    *,
    had_contradiction: bool,
    honesty_forced_verify: bool,
) -> str:
    if verdict == Verdict.SKIP:
        return "low"
    if honesty_forced_verify or had_contradiction:
        return "low"
    if verdict == Verdict.VERIFY:
        if _count_strength_at_least(signals, "medium") >= 2:
            return "medium"
        return "low"
    t1 = _best_strength_in_tier(signals, "T1")
    if t1 == "high" and not had_contradiction:
        return "high"
    if t1 == "medium" and _count_strength_at_least(signals, "medium") <= 2:
        return "low"
    return "medium"


def _normalize_signal_row(row: Mapping[str, Any]) -> SignalEvidence:
    return cast(
        SignalEvidence,
        {
            "id": str(row.get("id", "unknown")),
            "label": str(row.get("label", row.get("id", "signal"))),
            "tier": row.get("tier", "none"),
            "strength": row.get("strength", "none"),
            "details": str(row.get("details", ""))[:512],
        },
    )


def _strength_points(strength: str) -> int:
    return {"high": 100, "medium": 70, "low": 30, "none": 0}.get(str(strength), 0)


def _signal_status(signal: Mapping[str, Any]) -> str:
    v = str(signal.get("status", "")).lower()
    if v in ("pass", "fail", "unknown"):
        return v
    strength = str(signal.get("strength", "none"))
    if strength in ("high", "medium"):
        return "pass"
    if strength == "low":
        return "fail"
    return "unknown"


def _coverage(signals: List[Mapping[str, Any]]) -> tuple[int, int, float]:
    total = sum(1 for s in signals if str(s.get("tier")) in ("T1", "T2", "T3"))
    verified = sum(1 for s in signals if str(s.get("tier")) in ("T1", "T2", "T3") and _signal_status(s) in ("pass", "fail"))
    ratio = (verified / total) if total else 0.0
    return verified, total, ratio


def _layer_score(signals: List[Mapping[str, Any]], ids: set[str]) -> int:
    rows = [s for s in signals if str(s.get("id")) in ids]
    if not rows:
        return 0
    return int(sum(_strength_points(str(s.get("strength", "none"))) for s in rows) / max(1, len(rows)))


def decide_from_signals(
    signals: List[Mapping[str, Any]],
    *,
    url_provided: bool = False,
    policy_skip: Optional[Tuple[str, str]] = None,
) -> DecisionResponse:
    sorted_rows = sort_evidence_by_trust(signals)
    normalized: List[SignalEvidence] = [_normalize_signal_row(r) for r in sorted_rows]

    reasons: List[ReasonItem] = []
    warnings: List[WarningItem] = []

    company_ids = {"company_linkedin_presence", "careers_domain_match", "company_registry_presence", "cross_platform_freshness"}
    posting_ids = {"salary_range_plausibility", "role_title_consistency", "jd_red_flags", "contact_legitimacy", "posting_duplication_signal"}
    freshness_ids = {"staleness_flag", "first_seen_estimate", "cross_platform_freshness"}

    company_score = _layer_score(sorted_rows, company_ids)
    posting_score = _layer_score(sorted_rows, posting_ids)
    freshness_score = _layer_score(sorted_rows, freshness_ids)
    llm_conf = _layer_score(sorted_rows, {"jd_specificity", "jd_recruiter_intent_score", "jd_employer_identifiability"})

    verified_signal_count, total_signal_count, coverage_ratio = _coverage(sorted_rows)
    weighted_score = int((company_score * 0.35) + (posting_score * 0.35) + (freshness_score * 0.20) + (llm_conf * 0.10))
    legacy_score = _internal_score(sorted_rows, url_provided)
    coverage_cap = min(100, int(30 + (coverage_ratio * 100)))
    confidence_score = min(max(weighted_score, legacy_score), coverage_cap)
    confidence_score_int = max(0, min(100, int(confidence_score)))

    staleness_flag = _sig_strength(sorted_rows, "staleness_flag") == "low"
    first_seen_estimate = _sig_details(sorted_rows, "first_seen_estimate") or None

    company_pass = company_score >= 60
    posting_pass = posting_score >= 60
    freshness_pass = freshness_score >= 60 and not staleness_flag

    if policy_skip:
        code, msg = policy_skip
        reasons.extend([ReasonItem(code="POLICY_SKIP", message=msg), ReasonItem(code="POLICY_CODE", message=f"Skip code: {code}")])
        return DecisionResponse(
            verdict=Verdict.SKIP,
            confidence="low",
            reasons=reasons,
            warnings=[WarningItem(code="POLICY", message="Automated policy blocked further promotion to APPLY.")],
            signals=normalized,
            company_legitimacy_score=company_score,
            company_signals=[],
            posting_authenticity_score=posting_score,
            posting_signals=[],
            freshness_score=freshness_score,
            staleness_flag=staleness_flag,
            first_seen_estimate=first_seen_estimate,
            verified_signal_count=verified_signal_count,
            total_signal_count=total_signal_count,
            coverage_ratio=coverage_ratio,
            confidence_score=confidence_score_int,
            disclaimer="Some checks were blocked by policy controls, so this result may be incomplete.",
        )

    if _severe_text_pattern_skip(sorted_rows, url_provided=url_provided):
        reasons.extend(
            [
                ReasonItem(
                    code="TEXT_PATTERN_MATCH",
                    message="Strong patterns associated with low-trust postings were detected in the description text (this is a pattern match, not a fraud claim).",
                ),
                ReasonItem(code="NEXT_STEP", message="Retry with the employer's official posting URL for stronger corroboration."),
            ]
        )
        return DecisionResponse(
            verdict=Verdict.SKIP,
            confidence="low",
            reasons=reasons,
            warnings=[WarningItem(code="LOW_TRUST_PATTERN", message="Text-only patterns are not conclusive; prefer an employer URL and verify again.")],
            signals=normalized,
            company_legitimacy_score=company_score,
            company_signals=[],
            posting_authenticity_score=posting_score,
            posting_signals=[],
            freshness_score=freshness_score,
            staleness_flag=staleness_flag,
            first_seen_estimate=first_seen_estimate,
            verified_signal_count=verified_signal_count,
            total_signal_count=total_signal_count,
            coverage_ratio=coverage_ratio,
            confidence_score=confidence_score_int,
            disclaimer="This is a pattern-based warning from limited evidence; verify using official sources.",
        )

    if _text_only_apply_combo(sorted_rows, url_provided=url_provided):
        reasons.extend(
            [
                ReasonItem(code="TEXT_ONLY_APPLY", message="Description-only signals align under a strict combo; promoting to APPLY with capped confidence."),
                ReasonItem(code="NO_URL_CORROBORATION", message="No URL was provided; corroboration against employer-controlled sources was not performed."),
            ]
        )
        return DecisionResponse(
            verdict=Verdict.APPLY,
            confidence="medium",
            reasons=reasons,
            warnings=[WarningItem(code="TEXT_ONLY_NOT_CORROBORATED", message="This is based on description text only; confirm on the employer's official careers page before applying.")],
            signals=normalized,
            company_legitimacy_score=company_score,
            company_signals=[],
            posting_authenticity_score=posting_score,
            posting_signals=[],
            freshness_score=freshness_score,
            staleness_flag=staleness_flag,
            first_seen_estimate=first_seen_estimate,
            verified_signal_count=verified_signal_count,
            total_signal_count=total_signal_count,
            coverage_ratio=coverage_ratio,
            confidence_score=confidence_score_int,
            disclaimer="No URL corroboration was available, so this outcome remains partially uncertain.",
        )

    had_contradiction = _contradiction_fetch_without_domain(sorted_rows, url_provided)
    fetch_weak = _fetch_insufficient_for_apply(sorted_rows, url_provided)
    t3_only = _t3_only_loudest(sorted_rows)
    apply_ok = _apply_path(sorted_rows)

    hard_red_flag_ids = {"careers_domain_match", "contact_email_free_domain", "posting_duplication_signal"}
    hard_red_flag = any(str(s.get("id")) in hard_red_flag_ids and _signal_status(s) == "fail" for s in sorted_rows)
    insufficient_data = verified_signal_count < 3
    broad_coverage = total_signal_count >= 5 and coverage_ratio >= 0.6

    verdict: Verdict = Verdict.VERIFY
    if hard_red_flag or (confidence_score <= 35 and verified_signal_count >= 3 and broad_coverage):
        verdict = Verdict.SKIP
        reasons.append(ReasonItem(code="HARD_RED_FLAG", message="High-risk signals were detected, so this posting is not recommended."))
    elif insufficient_data:
        verdict = Verdict.VERIFY
        reasons.append(ReasonItem(code="INSUFFICIENT_DATA", message="Insufficient data to assess, here is what we checked."))
    elif had_contradiction:
        verdict = Verdict.VERIFY
        reasons.append(ReasonItem(code="CONTRADICTION", message="Fetch looked healthy but employer-domain alignment is missing; not promoting to APPLY."))
        warnings.append(WarningItem(code="CONTRADICTION", message="Conflicting signals downgraded trust."))
    elif fetch_weak and url_provided:
        verdict = Verdict.VERIFY
        reasons.append(ReasonItem(code="FETCH_INSUFFICIENT", message="A URL was provided but fetch evidence is missing or too weak to trust the posting page."))
        warnings.append(WarningItem(code="FETCH", message="Primary page evidence insufficient for a confident recommendation."))
    elif t3_only:
        verdict = Verdict.VERIFY
        reasons.append(ReasonItem(code="T3_ONLY", message="We found general web mentions, but couldn't confirm this role directly with the employer's official channels or trusted job boards."))
        warnings.append(WarningItem(code="SOURCES", message="Evidence relies mostly on unverified secondary sources."))
    elif apply_ok and (
        (confidence_score >= 75 and company_pass and posting_pass and freshness_pass)
        or (company_score == 0 and posting_score == 0 and freshness_score == 0)
    ):
        verdict = Verdict.APPLY
        reasons.append(ReasonItem(code="GATES_PASSED", message="We found strong corroborating evidence from official employer channels or verified job boards."))
    else:
        reasons.append(ReasonItem(code="INSUFFICIENT_CORROBORATION", message="Not enough signals passed to confidently recommend applying. Some checks came back unclear."))

    if (not url_provided) and (_sig_strength(sorted_rows, "jd_red_flags") in ("medium", "high") or _sig_strength(sorted_rows, "jd_content_farm_score") in ("medium", "high")):
        reasons.append(ReasonItem(code="TEXT_RED_FLAGS", message="Description-only signals include risk patterns; add the posting URL for stronger cross-checks."))

    if len(reasons) < 2:
        reasons.append(ReasonItem(code="INCOMPLETE_EVIDENCE", message="Evidence collection was partial. Unable to build a complete profile for this role."))

    honesty_forced_verify = False
    provisional_conf = _confidence_band(verdict, sorted_rows, had_contradiction=had_contradiction, honesty_forced_verify=False)
    if provisional_conf == "low" and verdict == Verdict.APPLY:
        verdict = Verdict.VERIFY
        honesty_forced_verify = True
        warnings.append(WarningItem(code="HONESTY_GUARD", message="Low confidence would contradict an APPLY recommendation; defaulted to VERIFY."))
        reasons.append(ReasonItem(code="HONESTY_LOW_CONFIDENCE", message="Confidence band was low; VERIFY is the safer output."))

    final_conf = _confidence_band(verdict, sorted_rows, had_contradiction=had_contradiction, honesty_forced_verify=honesty_forced_verify)
    layer_data_present = (company_score > 0) or (posting_score > 0) or (freshness_score > 0)
    if layer_data_present and confidence_score >= 80 and not (company_pass and posting_pass and freshness_pass):
        final_conf = "medium"

    if final_conf in ("medium", "low"):
        warnings.append(WarningItem(code=f"CONFIDENCE_{final_conf.upper()}", message="Treat this output as advisory; verify on official channels when unsure."))

    # Description-only VERIFY: lead with an explicit CTA to add the listing URL (stronger than generic corroboration copy).
    if verdict == Verdict.VERIFY and not url_provided:
        reasons.insert(
            0,
            ReasonItem(
                code="PREFER_POSTING_URL",
                message=(
                    "Paste the job posting URL when you can—we could not run listing-page checks without it. "
                    "A direct link from the job board or employer careers site is recommended over pasted description text alone."
                ),
            ),
        )

    return DecisionResponse(
        verdict=verdict,
        confidence=cast(Any, final_conf),
        reasons=reasons[:12],
        warnings=warnings[:12],
        signals=normalized,
        company_legitimacy_score=company_score,
        company_signals=[dict(s) for s in sorted_rows if str(s.get("id")) in company_ids],
        posting_authenticity_score=posting_score,
        posting_signals=[dict(s) for s in sorted_rows if str(s.get("id")) in posting_ids],
        freshness_score=freshness_score,
        staleness_flag=staleness_flag,
        first_seen_estimate=first_seen_estimate if first_seen_estimate and first_seen_estimate != "unverified" else None,
        verified_signal_count=verified_signal_count,
        total_signal_count=total_signal_count,
        coverage_ratio=round(coverage_ratio, 3),
        confidence_score=confidence_score_int,
        disclaimer="This assessment uses available evidence only. Some checks may be unknown or unavailable.",
    )


def decision_to_jsonable(decision: DecisionResponse) -> dict[str, Any]:
    raw_cs = decision.get("confidence_score")
    if raw_cs is None:
        cs_out = 0
    else:
        cs_out = max(0, min(100, int(raw_cs)))
    return {
        "verdict": decision["verdict"].value,
        "confidence": decision["confidence"],
        "confidence_score": cs_out,
        "reasons": list(decision["reasons"]),
        "warnings": list(decision["warnings"]),
        "signals": list(decision["signals"]),
        "company_legitimacy_score": decision.get("company_legitimacy_score", 0),
        "company_signals": list(decision.get("company_signals", [])),
        "posting_authenticity_score": decision.get("posting_authenticity_score", 0),
        "posting_signals": list(decision.get("posting_signals", [])),
        "freshness_score": decision.get("freshness_score", 0),
        "staleness_flag": bool(decision.get("staleness_flag", False)),
        "first_seen_estimate": decision.get("first_seen_estimate"),
        "verified_signal_count": int(decision.get("verified_signal_count", 0)),
        "total_signal_count": int(decision.get("total_signal_count", 0)),
        "coverage_ratio": float(decision.get("coverage_ratio", 0.0)),
        "disclaimer": str(decision.get("disclaimer", "")),
    }

