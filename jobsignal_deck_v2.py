#!/usr/bin/env python3
"""Build ``JobSignal_Final.pdf`` from the v2 template with embedded UI screenshots.

Layout and copy on all slides (except the four image slots and the two footers) are
taken unchanged from ``JobSignal_Deck_v2.pdf``.

Image regions use the same point geometry you would use with ReportLab
``canvas.drawImage(path, x, y, width=w, height=h)`` on A4, with the origin at the
**lower-left** corner (see ``_RL_*`` constants). The actual embedding is done with
PyMuPDF ``Page.insert_image`` so the rest of the deck is bit-identical to the
template.

Optional assets (PNG or JPEG) under ``deck_assets/``:

* ``slide01_hero.png`` — Slide 1 right-hand hero box
* ``slide09_panel1_verify.png`` — Slide 9, column 1
* ``slide09_panel2_skip.png`` — Slide 9, column 2
* ``slide09_panel3_twopanel.png`` — Slide 9, column 3

If a file is missing, that box is filled with the template OFF_WHITE tone and
centered text ``[ See video walkthrough ]`` (per deck prompt).
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

# --- Meta (Task 2 & 3) ------------------------------------------------------

REPO_URL = "https://github.com/ZugaTech/JobSignal"
# Live demo (Railway); fallback to repo if redeployed elsewhere.
DEMO_URL = "https://jobsignal.up.railway.app"

AUTHOR_LINE = "Moyosore Ogunde  |  AMD x LabLab AI Hackathon  |  2025"
FOOTER_LINKS = f"{REPO_URL}   |   {DEMO_URL}"

# -----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "JobSignal_Deck_v2.pdf"
OUTPUT = ROOT / "JobSignal_Final.pdf"
ASSET_DIR = ROOT / "deck_assets"

ASSETS = {
    "slide01": ASSET_DIR / "slide01_hero.png",
    "s9p1": ASSET_DIR / "slide09_panel1_verify.png",
    "s9p2": ASSET_DIR / "slide09_panel2_skip.png",
    "s9p3": ASSET_DIR / "slide09_panel3_twopanel.png",
}

# A4 (points) — must match the template
PAGE_W, PAGE_H = 595.2756, 841.8898

# Measured from ``JobSignal_Deck_v2.pdf`` (top-left origin, PyMuPDF / PDF space):
HERO_FITZ = fitz.Rect(368.50390625, 311.81109619140625, 549.9213256835938, 544.251953125)
PANELS_FITZ = [
    fitz.Rect(45.35432815551758, 153.07086181640625, 205.9842987060547, 325.9842529296875),
    fitz.Rect(217.3227996826172, 153.07086181640625, 377.9527893066406, 325.9842529296875),
    fitz.Rect(389.2912902832031, 153.07086181640625, 549.9213256835938, 325.9842529296875),
]

# ReportLab-style box (origin **bottom-left**), for reference / audits:
#   from reportlab.lib.pagesizes import A4
#   canvas.drawImage(..., x, y, width=w, height=h, preserveAspectRatio=True, anchor="c")
def _to_rl_box(r: fitz.Rect) -> tuple[float, float, float, float]:
    w, h = r.width, r.height
    x = r.x0
    y = PAGE_H - r.y1
    return (x, y, w, h)


RL_HERO = _to_rl_box(HERO_FITZ)
RL_PANELS = [_to_rl_box(p) for p in PANELS_FITZ]

# Placeholder face color (matches template box fill ≈ rgb 247, 249, 252)
OFF_WHITE = (0.969, 0.976, 0.988)
BORDER = (0.796, 0.835, 0.882)
PLACEHOLDER = "[ See video walkthrough ]"


def _embed_or_placeholder(page: fitz.Page, rect: fitz.Rect, path: Path) -> None:
    """Paint over the template placeholder (including its text layer), then add image or label."""

    if path.is_file():
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()
        # Equivalent ReportLab call (see module docstring), e.g. for HERO:
        #   canvas.drawImage(str(path), *RL_HERO, preserveAspectRatio=True, mask="auto")
        page.insert_image(rect, filename=str(path), keep_proportion=True, overlay=True)
        return

    page.add_redact_annot(rect, fill=OFF_WHITE)
    page.apply_redactions()
    inner = fitz.Rect(rect.x0 + 3, rect.y0 + 3, rect.x1 - 3, rect.y1 - 3)
    page.draw_rect(rect, color=BORDER, width=0.4)
    page.insert_textbox(
        inner,
        PLACEHOLDER,
        fontsize=7,
        fontname="helv",
        color=(0.35, 0.35, 0.4),
        align=fitz.TEXT_ALIGN_CENTER,
    )


def _footer_cover_slide1(page: fitz.Page) -> None:
    page.add_redact_annot(fitz.Rect(38, 572, 558, 628), fill=(1, 1, 1))
    page.apply_redactions()
    page.insert_textbox(
        fitz.Rect(45, 576, 550, 622),
        f"{AUTHOR_LINE}\n{FOOTER_LINKS}",
        fontsize=8,
        fontname="helv",
        color=(0.12, 0.12, 0.16),
        align=0,
    )


def _footer_cover_slide11(page: fitz.Page) -> None:
    page.add_redact_annot(fitz.Rect(38, 302, 558, 338), fill=(1, 1, 1))
    page.apply_redactions()
    page.insert_textbox(
        fitz.Rect(45, 306, 550, 334),
        f"{AUTHOR_LINE}\n{FOOTER_LINKS}",
        fontsize=8,
        fontname="helv",
        color=(0.12, 0.12, 0.16),
        align=0,
    )


def _print_rl_reference() -> None:
    """Helpful for judges / designers cross-checking ReportLab geometry."""
    x, y, w, h = RL_HERO
    print(
        "# Slide 1 hero — canvas.drawImage(slide01_hero, "
        f"{x:.4f}, {y:.4f}, width={w:.4f}, height={h:.4f}, preserveAspectRatio=True)",
        file=sys.stderr,
    )
    for i, box in enumerate(RL_PANELS, start=1):
        x, y, w, h = box
        print(
            f"# Slide 9 panel {i} — canvas.drawImage(panel{i}, "
            f"{x:.4f}, {y:.4f}, width={w:.4f}, height={h:.4f}, preserveAspectRatio=True)",
            file=sys.stderr,
        )


def main() -> int:
    if "--show-reportlab-boxes" in sys.argv:
        _print_rl_reference()
        return 0

    if not TEMPLATE.is_file():
        print(f"Missing template: {TEMPLATE}", file=sys.stderr)
        return 1

    doc = fitz.open(TEMPLATE)
    if len(doc) != 11:
        print(f"Expected 11 pages in template, got {len(doc)}", file=sys.stderr)
        doc.close()
        return 1

    # Slide 1
    p1 = doc[0]
    _embed_or_placeholder(p1, HERO_FITZ, ASSETS["slide01"])
    _footer_cover_slide1(p1)

    # Slide 9
    p9 = doc[8]
    for rect, key in zip(PANELS_FITZ, ["s9p1", "s9p2", "s9p3"]):
        _embed_or_placeholder(p9, rect, ASSETS[key])

    # Slide 11
    p11 = doc[10]
    _footer_cover_slide11(p11)

    doc.save(OUTPUT, deflate=True, garbage=4, clean=True)
    doc.close()

    with fitz.open(OUTPUT) as check:
        n = len(check)
    if n != 11:
        print(f"Output page count {n} != 11", file=sys.stderr)
        return 1

    print(f"Wrote {OUTPUT} ({n} pages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
