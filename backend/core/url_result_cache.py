"""7-day (extendable) URL-only full-result cache — instant replay for identical cleaned URLs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jobsignal")

RESULT_CACHE_KEY_PREFIX = "js:urlres:v1:"

_CONFIRMED_TRUST_STATUSES = frozenset({"Strong Match", "Partial Match", "Verified", "Pass"})


def humanize_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "expired"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not parts and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append("less than a minute")
    return ", ".join(parts)


def confirmed_trust_signal_count(report: Dict[str, Any]) -> int:
    ts = report.get("trust_signals") or []
    if not isinstance(ts, list):
        return 0
    n = 0
    for row in ts:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status") or "").strip()
        if st in _CONFIRMED_TRUST_STATUSES:
            n += 1
    return n


def should_store_url_result_cache(report: Dict[str, Any]) -> bool:
    """CACHE_WRITE eligibility after validation repair."""

    verdict = str(report.get("verdict") or "").upper()
    try:
        cs = int(report.get("confidence_score") if report.get("confidence_score") is not None else -1)
    except (TypeError, ValueError):
        cs = -1

    if verdict == "VERIFY":
        return False
    if verdict not in ("APPLY", "SKIP"):
        return False
    if cs < 40:
        return False

    rs = report.get("review_summary")
    has_review = isinstance(rs, dict) and str(rs.get("plain_summary") or "").strip()
    if not has_review and confirmed_trust_signal_count(report) < 3:
        return False
    return True


def url_result_ttl_seconds(report: Dict[str, Any]) -> int:
    verdict = str(report.get("verdict") or "").upper()
    try:
        cs = int(report.get("confidence_score") if report.get("confidence_score") is not None else 0)
    except (TypeError, ValueError):
        cs = 0
    if verdict == "SKIP" and cs >= 80:
        return 14 * 24 * 60 * 60
    return 7 * 24 * 60 * 60


def wrap_stored_payload(*, report: Dict[str, Any], cached_at_iso: str, ttl_seconds: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds))
    envelope = {
        "cached_at": cached_at_iso,
        "expires_at": expires.isoformat(),
        "report": report,
    }
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)


def parse_stored_payload(raw: str) -> Optional[Tuple[Dict[str, Any], str, str]]:
    """Return (report, cached_at, expires_at_iso) or None."""

    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(env, dict):
        return None
    rep = env.get("report")
    cat = env.get("cached_at")
    exp = env.get("expires_at")
    if not isinstance(rep, dict) or not isinstance(cat, str):
        return None
    return rep, cat, str(exp or "")


def decorate_hit_response(
    report: Dict[str, Any],
    *,
    cached_at: str,
    expires_at_iso: str,
    now_iso: str,
) -> Dict[str, Any]:
    out = dict(report)
    out["cached"] = True
    out["cached_at"] = cached_at
    out["original_analysis_date"] = cached_at
    out["data_freshness"] = now_iso
    try:
        exp_dt = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        remaining = int((exp_dt - now_dt).total_seconds())
    except ValueError:
        remaining = 0
    out["cache_expires_in"] = humanize_remaining(remaining)
    cm = dict(out.get("cache") or {})
    cm["hit"] = True
    cm["url_result_cache"] = True
    out["cache"] = cm
    return out


async def schedule_cache_set(cache: Any, key: str, payload: str, ttl_seconds: int) -> None:
    import asyncio

    def _write() -> None:
        try:
            cache.set(key, payload, ttl_seconds=int(ttl_seconds))
        except Exception as e:  # noqa: BLE001
            logger.warning("url_result_cache_write_failed key=%s err=%s", key[:48], str(e))

    asyncio.get_running_loop().run_in_executor(None, _write)
