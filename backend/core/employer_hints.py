"""Small curated employer blurbs when the LLM baseline returns unknown (accuracy-first, low confidence)."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("jobsignal")

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "employer_hints.json"


@lru_cache(maxsize=1)
def _loaded_hints() -> tuple[list[dict[str, Any]], int]:
    if not _DATA_PATH.is_file():
        return [], 0
    try:
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        hints = raw.get("hints") if isinstance(raw, dict) else []
        ver = int(raw.get("version") or 0) if isinstance(raw, dict) else 0
        if not isinstance(hints, list):
            return [], ver
        return hints, ver
    except Exception as e:  # noqa: BLE001
        logger.warning("employer_hints_load_failed path=%s err=%s", _DATA_PATH, e)
        return [], 0


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def lookup_curated_employer(company_name: str) -> Optional[Dict[str, Any]]:
    key = _normalize_name(company_name)
    if len(key) < 2:
        return None
    hints, _ver = _loaded_hints()
    for row in hints:
        aliases = row.get("aliases") if isinstance(row, dict) else None
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            a = _normalize_name(alias)
            if not a:
                continue
            if key == a or a in key or key in a:
                summary = str(row.get("reputation_summary") or "").strip()
                if not summary:
                    continue
                return {
                    "known": True,
                    "reputation_summary": summary,
                    "known_positives": list(row.get("known_positives") or [])[:4],
                    "known_concerns": list(row.get("known_concerns") or [])[:4],
                    "confidence": str(row.get("confidence") or "low").lower() or "low",
                }
    return None


def merge_curated_baseline(company_name: str, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """If Kimi returned unknown/missing, optionally substitute vetted low-confidence facts."""

    curated = lookup_curated_employer(company_name)
    if not curated:
        return data
    if data and data.get("known"):
        conf = str(data.get("confidence") or "").lower()
        if conf not in ("none", "", "low") or len(str(data.get("reputation_summary") or "").strip()) > 80:
            return data
    return curated
