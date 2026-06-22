"""
due_diligence.pitch_deck — 4-stage pitch deck generation pipeline.

Public API
----------
    from due_diligence.pitch_deck import run_pipeline
    from due_diligence.pitch_deck import plan_content, select_theme, compute_layout, render_deck
    from due_diligence.pitch_deck.themes import THEMES, get_theme, Theme

Pipeline stages
---------------
    Stage 1  content_planner.plan_content()   LLM → SlideOutline (Pydantic-validated JSON)
    Stage 2  theme_selector.select_theme()    LLM classification → Theme object
    Stage 3  layout_engine.compute_layout()   Pure code → RenderedSlide list (exact geometry)
    Stage 4  render_pptx.render_deck()        Pure python-pptx → .pptx bytes
"""

from .pipeline import run_pipeline, run_pipeline_from_startup
from .content_planner import plan_content, SlideOutline, SlideSpec, SlideBody
from .theme_selector import select_theme
from .layout_engine import compute_layout, RenderedSlide, ShapeSpec
from .render_pptx import render_deck
from .themes import THEMES, get_theme, Theme, themes_for_llm_prompt

__all__ = [
    # Orchestrator
    "run_pipeline",
    "run_pipeline_from_startup",
    # Stage entry points
    "plan_content",
    "select_theme",
    "compute_layout",
    "render_deck",
    # Schema types
    "SlideOutline",
    "SlideSpec",
    "SlideBody",
    "RenderedSlide",
    "ShapeSpec",
    # Theme registry
    "THEMES",
    "get_theme",
    "Theme",
    "themes_for_llm_prompt",
]
