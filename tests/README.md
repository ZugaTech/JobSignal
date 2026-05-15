# tests/

Pytest suite for JobSignal: scoring contracts, cache privacy, normalization, API smoke paths, fixture-backed flows, and provider mocks.

## Conventions

- **CI:** `.github/workflows/ci.yml` installs `fakeredis`, runs `npm run build`, then `pytest` with `PYTHONPATH=.`.
- **No live keys:** Tests must not require production API keys; use `monkeypatch`, stubs, or JSON fixtures under `data_sources/fixtures/`.
- **Frontend coupling:** After edits under `src/`, run `pytest tests/test_frontend_smoke.py` (and `npm run build` before release); legacy `frontend/*.js` may not exist in all clones.

## Running

```bash
pip install -r requirements.txt
pip install fakeredis   # matches CI extras if needed locally
set PYTHONPATH=.
pytest
```
