"""End-to-end verify orchestration (post–Sprint 4 vertical slice).

This is the smallest glue layer that connects:
validate -> normalize -> cache R/W -> fixtures evidence -> scoring -> report.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from backend.core.cache_key import build_public_cache_key
from backend.core.cache_payload import serialize_payload, strip_tenant_fields
from backend.core.cache_store import InMemoryCache
from backend.core.env import EnvConfig
from backend.core.fixtures import load_fixture_evidence
from backend.core.inputs import InputValidationError, validate_raw_job_inputs
from backend.core.normalization import normalize_job_input
from backend.core.report import build_public_report
from backend.core.scoring import SCORER_VERSION, decide_from_signals

_MEM_CACHE = InMemoryCache()


def _ttl_seconds(ttl_days: int) -> int:
    return int(ttl_days) * 24 * 60 * 60


def verify_job(*, job_url: Optional[str], job_description: Optional[str]) -> Dict[str, Any]:
    cfg = EnvConfig.load(strict=False)

    try:
        url, text = validate_raw_job_inputs(job_url, job_description)
    except InputValidationError as e:
        raise ValueError(f"{e.code}: {e}") from e

    norm = normalize_job_input(url, text)
    cache_key = build_public_cache_key(
        norm,
        pipeline_version=cfg.source_pipeline_version,
        source_set_version="fixtures-v1",
    )

    cached = _MEM_CACHE.get(cache_key.materialized)
    if cached:
        payload = json.loads(cached)
        # Cached rows are evidence-first; for demo, convert to scorer signals directly.
        signals = payload.get("signals", [])
        decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))
        report = build_public_report(
            decision,
            cache={"hit": True, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
            meta={"pipeline_version": cfg.source_pipeline_version, "scorer_version": SCORER_VERSION},
        )
        return report

    signals: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []

    # Deterministic demo mode: add minimal “url canonical” evidence.
    if norm.canonical_url:
        signals.append(
            {
                "id": "url_canonical",
                "label": "url_canonical",
                "tier": "none",
                "strength": "low",
                "details": norm.canonical_url[:256],
            }
        )

    fixtures_path = os.environ.get("JOBSIGNAL_FIXTURES_PATH", "data_sources/fixtures/verify_fixtures.json")
    fe = load_fixture_evidence(
        fixtures_path=fixtures_path,
        canonical_url_sha256=norm.canonical_url_sha256,
        description_full_sha256=norm.description_full_sha256,
    )
    if fe:
        signals.extend(fe.signals)
        warnings.extend(fe.warnings)
    else:
        warnings.append(
            {
                "code": "FIXTURES_MISS",
                "message": "No fixture evidence matched this input; result will likely VERIFY until live adapters are wired.",
            }
        )

    decision = decide_from_signals(signals, url_provided=bool(norm.canonical_url))
    report = build_public_report(
        decision,
        cache={"hit": False, "ttl_expires_at": None, "key_fingerprint": cache_key.fingerprint_preview},
        meta={"pipeline_version": cfg.source_pipeline_version, "scorer_version": SCORER_VERSION},
    )

    # Cache evidence-only, tenant-safe payload
    shared_payload = strip_tenant_fields(
        {
            "schema_version": "1",
            "pipeline_version": cfg.source_pipeline_version,
            "source_set_version": "fixtures-v1",
            "normalization_version": norm.normalization_version,
            "signals": signals,
            "warnings": [w["code"] for w in warnings],
            "coverage": "partial" if signals else "none",
        }
    )
    _MEM_CACHE.set(cache_key.materialized, serialize_payload(shared_payload), ttl_seconds=_ttl_seconds(cfg.cache_ttl_days))
    return report

