"""Core verdict enum and public verify response shape (contract only)."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, TypedDict


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
    tier: str  # "T1" | "T2" | "T3" | "none"
    strength: str  # "high" | "medium" | "low" | "none"
    details: str


class CacheMeta(TypedDict):
    hit: bool
    ttl_expires_at: Optional[str]
    key_fingerprint: str


class ResponseMeta(TypedDict):
    pipeline_version: str
    scorer_version: str


class VerifyResponse(TypedDict, total=False):
    """Basic API output contract aligned with docs/architecture.md."""

    request_id: str
    verdict: str  # Verdict value
    confidence: float
    confidence_band: str  # "high" | "medium" | "low"
    signals: List[SignalEvidence]
    reasons: List[ReasonItem]
    warnings: List[WarningItem]
    cache: CacheMeta
    meta: ResponseMeta
