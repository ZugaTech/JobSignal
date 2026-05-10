from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_extension_handoff_encodes_cached_result_and_size_caps():
    popup = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")
    assert "lastVerifyResult" in popup
    assert "cached_result" in popup
    assert "50 * 1024" in popup
    assert "openWebApp(currentJobData?.url, currentJobData?.description, lastVerifyResult)" in popup


def test_react_handoff_hydrates_cached_result_before_verify():
    hook = (ROOT / "src" / "hooks" / "useClipboardAndHandoff.ts").read_text(encoding="utf-8")
    app = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    cached_idx = hook.index('params.get("cached_result")')
    description_idx = hook.index('params.get("job_description")')
    assert cached_idx < description_idx
    assert "cachedResult" in hook
    assert "hydrateReport(data.cachedResult)" in app
    assert "return;" in app[app.index("if (data.cachedResult)") : app.index("if (data.text)")]


def test_legacy_handoff_returns_before_runflow_for_cached_result():
    app = (ROOT / "frontend-legacy" / "app.js").read_text(encoding="utf-8")
    cached_idx = app.index('params.get("cached_result")')
    run_idx = app.index("runFlow();", cached_idx)
    branch = app[cached_idx:run_idx]
    assert "populateModal(sanitizeApiResponse(decoded))" in branch
    assert 'window.history.replaceState({}, "", window.location.pathname)' in branch
    assert "return;" in branch
