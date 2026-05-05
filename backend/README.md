# backend/

Core Python modules (incrementally added across sprints):

- `core/normalization.py`, `cache_key.py`, `cache_payload.py`, `cache_store.py`, `extraction.py`, `source_evidence.py` — Sprint 2 ingestion/cache contracts  
- `core/decision_schema.py`, `scoring.py`, `report.py` — Sprint 3 verdict + public report  
- `core/env.py`, `inputs.py`, `prompt_guard.py`, `health.py` — Sprint 4 hardening + readiness helpers  

Run tests from repo root: `python -m pytest`.
