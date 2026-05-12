"""Static frontend smoke checks (no Playwright required).

Primary UI is the Vite/React bundle under ``dist/`` (see ``backend/api/main.py``).
Legacy ``frontend/*.js`` may be absent when only the React app is shipped.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_dist_bundle_exists():
    """Production UI served by FastAPI when ``dist/`` is present."""
    idx = ROOT / "dist" / "index.html"
    assert idx.is_file(), "missing dist/index.html — run `npm install && npm run build`"
    assets_dir = ROOT / "dist" / "assets"
    assert assets_dir.is_dir(), "missing dist/assets"
    js_bundles = list(assets_dir.glob("*.js"))
    assert js_bundles, "missing vite JS bundle under dist/assets"


def test_dist_bootstraps_react_shell():
    html = _read("dist/index.html")
    assert 'id="root"' in html
    assert "/assets/" in html


@pytest.mark.parametrize(
    "token",
    ("phase", "loading", "success", "error"),
)
def test_react_source_documents_core_flow_tokens(token: str):
    app_tsx = _read("src/App.tsx")
    assert token in app_tsx


def test_formatters_exports_ui_safety_helpers():
    blob = _read("src/utils/formatters.ts")
    assert "isUnsafeUserProse" in blob
    assert "looksLikeModelMonologue" in blob
    assert "sanitizeProseForUi" in blob
    assert "buildWhatWeFoundBullets" in blob
    assert "filterHeadsUpWarnings" in blob


def test_api_helpers_sanitizes_with_prose_guard():
    blob = _read("src/utils/api-helpers.ts")
    assert "sanitizeApiResponse" in blob
    assert "sanitizeProseForUi" in blob
    assert "isUnsafeUserProse" in blob


def test_verdict_strings_present_in_ui_source():
    blob = _read("src/App.tsx")
    for tok in ("APPLY", "SKIP"):
        assert tok in blob
    assert "Evidence overview" in blob or "TrustPresentation" in blob
    helpers = _read("src/utils/api-helpers.ts")
    assert "VERIFY" in helpers
