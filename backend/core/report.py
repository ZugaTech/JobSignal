"""Public report envelope for API/UI (Sprint 3)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict, cast

from backend.core.decision_schema import CacheMeta, DecisionResponse, ResponseMeta
from backend.core.scoring import decision_to_jsonable


class PublicVerifyReport(TypedDict, total=False):
    """Stable JSON shape for clients; extends decision JSON with versioning."""

    report_schema_version: str
    verdict: str
    confidence: str
    reasons: list[dict[str, str]]
    warnings: list[dict[str, str]]
    signals: list[dict[str, Any]]
    cache: CacheMeta
    meta: ResponseMeta
    ingestion: dict[str, Any]


def build_public_report(
    decision: DecisionResponse,
    *,
    cache: Optional[CacheMeta] = None,
    meta: Optional[ResponseMeta] = None,
    ingestion: Optional[dict[str, Any]] = None,
) -> PublicVerifyReport:
    payload = decision_to_jsonable(decision)
    merged: dict[str, Any] = {"report_schema_version": "1.1.0", **payload}
    if cache is not None:
        merged["cache"] = cache
    if meta is not None:
        merged["meta"] = meta
    if ingestion is not None:
        merged["ingestion"] = ingestion
    return cast(PublicVerifyReport, merged)
