"""Trim verify JSON for default API responses; full detail lives in report_detail_store."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def trim_verify_response(report: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(report)
    out.pop("company_signals", None)
    out.pop("posting_signals", None)
    meta = out.get("meta")
    if isinstance(meta, dict):
        meta = dict(meta)
        meta.pop("pipeline_steps", None)
        out["meta"] = meta
    signals = out.get("signals")
    if isinstance(signals, list):
        slim: List[Dict[str, Any]] = []
        for s in signals:
            if not isinstance(s, dict):
                continue
            row = dict(s)
            det = str(row.get("details") or "")
            if len(det) > 200:
                row["details"] = det[:197] + "..."
            slim.append(row)
        out["signals"] = slim
    ts = out.get("trust_signals")
    if isinstance(ts, list):
        slim_ts = []
        for row in ts:
            if not isinstance(row, dict):
                continue
            r = dict(row)
            d = str(r.get("detail") or "")
            if len(d) > 200:
                r["detail"] = d[:197] + "..."
            slim_ts.append(r)
        out["trust_signals"] = slim_ts
    ev = out.get("evidence_sources")
    if isinstance(ev, list):
        out["evidence_sources"] = ev[:24]
    return out
