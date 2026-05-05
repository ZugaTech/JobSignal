"""Fixtures-backed evidence builder for deterministic demos and CI.

This is intentionally small: it turns known inputs into a small set of signals.
Real fetch/search adapters should be wired later behind the same interface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class FixtureEvidence:
    signals: List[Dict[str, Any]]
    warnings: List[Dict[str, str]]


def _load_fixtures(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture_evidence(
    *,
    fixtures_path: str,
    canonical_url_sha256: Optional[str],
    description_full_sha256: Optional[str],
) -> Optional[FixtureEvidence]:
    """Look up evidence by url hash first, then text hash."""

    p = Path(fixtures_path)
    if not p.is_file():
        return None

    root = _load_fixtures(p)
    by_url = root.get("by_url_sha256", {})
    by_text = root.get("by_text_sha256", {})

    row: Optional[dict[str, Any]] = None
    if canonical_url_sha256 and canonical_url_sha256 in by_url:
        row = by_url[canonical_url_sha256]
    elif description_full_sha256 and description_full_sha256 in by_text:
        row = by_text[description_full_sha256]

    if not row:
        return None

    signals = list(row.get("signals", []))
    warnings = list(row.get("warnings", []))
    return FixtureEvidence(signals=signals, warnings=warnings)

