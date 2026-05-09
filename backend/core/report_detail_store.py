"""In-memory store for full verify payloads (detail endpoint). Thread-safe, bounded."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


_lock = threading.Lock()
_store: Dict[str, tuple[float, Dict[str, Any]]] = {}
_MAX = 800
_TTL_SEC = 3600.0


def remember_report(request_id: str, payload: Dict[str, Any]) -> None:
    if not request_id:
        return
    now = time.monotonic()
    with _lock:
        _store[str(request_id)] = (now + _TTL_SEC, dict(payload))
        if len(_store) > _MAX:
            _evict_expired_unlocked(now)
            if len(_store) > _MAX:
                # Drop oldest fraction by insertion order approximation
                for k in list(_store.keys())[: len(_store) - _MAX + 50]:
                    _store.pop(k, None)


def get_report_detail(request_id: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _lock:
        _evict_expired_unlocked(now)
        row = _store.get(str(request_id))
        if not row:
            return None
        exp, payload = row
        if now >= exp:
            del _store[str(request_id)]
            return None
        return dict(payload)


def pop_report_detail(request_id: str) -> Optional[Dict[str, Any]]:
    """compat alias — detail reads are non-destructive."""

    return get_report_detail(request_id)


def _evict_expired_unlocked(now: float) -> None:
    dead = [k for k, (exp, _) in _store.items() if now >= exp]
    for k in dead:
        _store.pop(k, None)
