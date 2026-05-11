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


# The legacy vanilla-JS frontend was retired in favor of the React app under ``src/``.
# The original cached-handoff regression now lives in
# ``test_react_handoff_hydrates_cached_result_before_verify`` above, which asserts the
# same return-before-verify behavior on the supported code path.
