"""Core verdict enum and public verify response shape (contract only)."""

from __future__ import annotations

from enum import Enum
try:
    from typing import Any, Dict, List, Literal, Optional, TypedDict, NotRequired
except ImportError:
    from typing import Any, Dict, List, Literal, Optional, TypedDict
    from typing_extensions import NotRequired


class Verdict(str, Enum):
    """User-facing recommendation; rule engine is authoritative."""

    APPLY = "APPLY"
    VERIFY = "VERIFY"
    SKIP = "SKIP"


class ReasonItem(TypedDict):
    code: str
    message: str


class WarningItem(TypedDict):
    code: str
    message: str


class SignalEvidence(TypedDict):
    id: str
    label: str
    tier: Literal["T1", "T2", "T3", "none"]
    strength: Literal["high", "medium", "low", "none"]
    details: str


class DecisionResponse(TypedDict):
    """Core decision payload; confidence is always explicit at top level."""

    verdict: Verdict
    confidence: Literal["high", "medium", "low"]
    # reasons: must contain at least 2 items
    reasons: List[ReasonItem]
    warnings: List[WarningItem]
    signals: List[SignalEvidence]

    # Sprint 3: Verification Depth
    company_legitimacy_score: int
    company_signals: List[Dict[str, Any]]
    posting_authenticity_score: int
    posting_signals: List[Dict[str, Any]]
    freshness_score: int
    staleness_flag: bool
    first_seen_estimate: Optional[str]

    # Honest Uncertainty
    verified_signal_count: int
    total_signal_count: int
    coverage_ratio: float
    disclaimer: str


class CacheMeta(TypedDict):
    hit: bool
    ttl_expires_at: Optional[str]
    key_fingerprint: str


class ResponseMeta(TypedDict):
    pipeline_version: str
    scorer_version: str
    pipeline_steps: NotRequired[List[dict[str, str]]]


class VerifyResponse(DecisionResponse):
    """Full API envelope: required decision fields plus optional transport metadata."""

    request_id: NotRequired[str]
    cache: NotRequired[CacheMeta]
    meta: NotRequired[ResponseMeta]
