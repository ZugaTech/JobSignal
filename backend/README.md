# backend/

Python service for JobSignal: **input validation**, **normalization**, **evidence collection** (search + optional live fetch), **scoring**, **public report shaping**, and **cache** read/write.

## Layout

| Area | Module(s) | Role |
|------|------------|------|
| HTTP | `api/main.py` | FastAPI app, CORS, rate limits, static / `dist/` UI |
| Orchestration | `core/orchestrator.py` | End-to-end `verify_job` pipeline |
| Trust / evidence | `core/evidence.py`, `source_evidence.py`, `fetch_job_page.py` | T1–T3 signals, SSRF-safe fetch |
| Scoring | `core/scoring.py`, `report.py`, `decision_schema.py` | Verdict + confidence |
| Cache | `core/cache_key.py`, `cache_payload.py`, `cache_store.py` | Keys, TTL, Redis / memory |
| Safety | `core/inputs.py`, `prompt_guard.py`, `env.py`, `health.py` | Bounds, injection hints, readiness |

## Tests

From repo root:

```bash
set PYTHONPATH=.
pytest
```
