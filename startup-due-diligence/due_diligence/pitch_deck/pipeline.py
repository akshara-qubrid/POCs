"""
pipeline.py — Orchestrates the 4-stage pitch deck generation pipeline.

Stage 1: ContentPlanner  — LLM call → SlideOutline (structured JSON + Pydantic validation)
Stage 2: ThemeSelector   — LLM call (classification only) → theme_id → Theme
Stage 3: LayoutEngine    — pure code → RenderedSlide list (exact geometry)
Stage 4: PptxRenderer    — pure code (python-pptx) → .pptx bytes

Call run_pipeline(report) as the single entry point.
The /pitch-deck and /pitch-deck/download API endpoints in main.py import from here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from .content_planner import plan_content, SlideOutline
from .theme_selector import select_theme
from .layout_engine import compute_layout
from .render_pptx import render_deck


def run_pipeline(
    report: Any,
    output_path: Optional[str] = None,
    startup_name: str = "",
) -> bytes:
    """
    Full 4-stage pitch deck generation pipeline.

    Args:
        report:       Due diligence report — accepts a dict (from the DD pipeline)
                      or a raw text string.
        output_path:  Optional filesystem path to also write the .pptx file to disk.
        startup_name: Short label used in log output only.

    Returns:
        The generated .pptx file as raw bytes.
    """
    label = startup_name or (str(report)[:60] if isinstance(report, str) else "")
    print(f"\n{'='*60}")
    print(f"[Pipeline] 4-Stage Pitch Deck Generator")
    if label:
        print(f"[Pipeline] Startup: {label}")
    print(f"{'='*60}")

    # Stage 1 — Content Planner
    print("\n[Pipeline] ▶ Stage 1: Content Planner")
    outline: SlideOutline = plan_content(report)
    print(f"[Pipeline] ✓ Stage 1 complete: {len(outline.slides)} slides, deck='{outline.deck_title}'")

    # Stage 2 — Theme Selector
    print("\n[Pipeline] ▶ Stage 2: Theme Selector")
    theme = select_theme(tone_summary=outline.tone_summary, deck_title=outline.deck_title)
    print(f"[Pipeline] ✓ Stage 2 complete: theme='{theme.label}' ({theme.theme_id})")

    # Stage 3 — Layout Engine
    print("\n[Pipeline] ▶ Stage 3: Layout Engine")
    rendered_slides = compute_layout(outline, theme)
    print(f"[Pipeline] ✓ Stage 3 complete: {len(rendered_slides)} slides rendered")

    # Stage 4 — PPTX Renderer
    print("\n[Pipeline] ▶ Stage 4: PPTX Renderer")
    pptx_bytes = render_deck(rendered_slides, theme, output_path=output_path)
    print(f"[Pipeline] ✓ Stage 4 complete: {len(pptx_bytes):,} bytes")

    print(f"\n{'='*60}")
    print(f"[Pipeline] Done — deck: '{outline.deck_title}', theme: '{theme.label}'")
    print(f"{'='*60}\n")

    return pptx_bytes


def _safe_filename(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text).strip("_")[:60] or "pitch-deck"


def run_pipeline_from_startup(startup: str, output_dir: str = ".") -> Dict[str, Any]:
    """
    Convenience wrapper: runs the full DD pipeline first to ground the deck
    in real analysis, then runs the 4-stage deck pipeline.

    Returns a dict with:
      - pptx_bytes:     raw .pptx bytes
      - pptx_filename:  suggested filename
      - output_path:    path written to disk (if output_dir given)
    """
    from ..main import run as run_dd

    print("\n[Pipeline] Running due diligence pipeline first...")
    report = run_dd(startup)

    from ..main import slim_report
    filename = _safe_filename(startup) + "_deck.pptx"
    out_path = str(Path(output_dir) / filename)

    pptx_bytes = run_pipeline(slim_report(report), output_path=out_path, startup_name=startup[:60])

    return {
        "pptx_bytes": pptx_bytes,
        "pptx_filename": filename,
        "output_path": out_path,
    }
