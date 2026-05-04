from backend.core.source_evidence import sort_evidence_by_trust


def test_orders_tier_then_strength_then_id():
    rows = [
        {"id": "z", "tier": "T3", "strength": "high"},
        {"id": "a", "tier": "T1", "strength": "low"},
        {"id": "m", "tier": "T2", "strength": "high"},
        {"id": "b", "tier": "T1", "strength": "high"},
    ]
    out = sort_evidence_by_trust(rows)
    ids = [r["id"] for r in out]
    assert ids == ["b", "a", "m", "z"]
