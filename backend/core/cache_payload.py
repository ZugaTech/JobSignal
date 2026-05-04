"""Shared cache payload shape and tenant-field stripping."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, TypedDict

# Keys that must never appear in serialized shared cache entries.
_TENANT_FORBIDDEN = frozenset(
    {
        "tenant_id",
        "tenantId",
        "user_id",
        "userId",
        "internal_notes",
        "recruiter_notes",
        "api_key",
        "authorization",
    }
)


class SharedCachePayload(TypedDict):
    """Evidence-first cached snapshot (Sprint 2). Verdict may be absent until Sprint 3."""

    schema_version: str
    pipeline_version: str
    source_set_version: str
    normalization_version: str
    signals: List[Dict[str, Any]]
    warnings: List[str]
    coverage: str  # e.g. "full" | "partial" | "none"


def strip_tenant_fields(obj: Mapping[str, Any]) -> Dict[str, Any]:
    """Return shallow copy without forbidden keys (recursive for dict values)."""

    def _walk(o: Any) -> Any:
        if isinstance(o, dict):
            out: Dict[str, Any] = {}
            for k, v in o.items():
                if k in _TENANT_FORBIDDEN:
                    continue
                out[k] = _walk(v)
            return out
        if isinstance(o, list):
            return [_walk(i) for i in o]
        return o

    return _walk(dict(obj))  # type: ignore[arg-type]


def assert_shared_cache_json_safe(payload: Mapping[str, Any]) -> None:
    """Raise if forbidden keys exist at any depth (used by tests)."""

    def _scan(o: Any, path: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _TENANT_FORBIDDEN:
                    raise ValueError(f"forbidden cache key {k} at {path}")
                _scan(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                _scan(v, f"{path}[{i}]")

    _scan(dict(payload), "$")


def serialize_payload(payload: Mapping[str, Any]) -> str:
    """JSON for cache store; ensures tenant strip was applied."""
    assert_shared_cache_json_safe(payload)
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
