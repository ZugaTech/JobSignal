"""Static frontend smoke checks (no Playwright required)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_frontend_files_exist():
    for rel in ("frontend/index.html", "frontend/app.js", "frontend/styles.css", "frontend/labels.js"):
        assert (ROOT / rel).is_file(), f"missing {rel}"


@pytest.mark.parametrize(
    "token",
    ("idle", "loading", "success", "warning", "error", "jobImage", "ingestionNote", "recRecommendations", "recSection"),
)
def test_frontend_documents_ui_phases(token: str):
    html = _read("frontend/index.html")
    js = _read("frontend/app.js")
    labels = _read("frontend/labels.js")
    blob = html + js + labels
    assert token in blob


def test_frontend_includes_client_validation():
    js = _read("frontend/app.js")
    assert "validateClientInputs" in js


def test_app_contains_uncertainty_copy():
    html = _read("frontend/index.html")
    js = _read("frontend/app.js")
    blob = html + js
    assert "VERIFY" in blob
    assert "Limited certainty" in blob or "uncertainty" in blob.lower()
