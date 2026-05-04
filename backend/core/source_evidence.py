"""Trust-tier ordering for evidence items (Sprint 2)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping

Tier = Literal["T1", "T2", "T3", "none"]
Strength = Literal["high", "medium", "low", "none"]

_TIER_ORDER: Dict[str, int] = {"T1": 0, "T2": 1, "T3": 2, "none": 3}
_STRENGTH_ORDER: Dict[str, int] = {"high": 0, "medium": 1, "low": 2, "none": 3}


def _tier_rank(tier: str) -> int:
    return _TIER_ORDER.get(tier, 99)


def _strength_rank(strength: str) -> int:
    return _STRENGTH_ORDER.get(strength, 99)


def sort_evidence_by_trust(items: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Stable sort: tier (T1 first), then strength (high first), then id."""

    def key(row: Mapping[str, Any]) -> tuple[int, int, str]:
        tid = str(row.get("id", ""))
        tier = str(row.get("tier", "none"))
        strength = str(row.get("strength", "none"))
        return (_tier_rank(tier), _strength_rank(strength), tid)

    sorted_rows = sorted(items, key=key)
    return [dict(r) for r in sorted_rows]
