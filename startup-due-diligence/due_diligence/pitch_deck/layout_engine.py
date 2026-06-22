"""
layout_engine.py — Stage 3 of the 4-stage pitch deck pipeline.

Pure Python, zero LLM calls. Deterministic, fully unit-testable.

Responsibilities:
  - Accept a SlideOutline (from Stage 1) and a Theme (from Stage 2).
  - For each slide, select a layout variant (preventing every slide of the
    same type from looking identical).
  - Compute EXACT shape geometry (x, y, w, h in inches) for every element.
  - Handle overflow: step font size down before truncating content.
  - Enforce all hard design rules (no accent stripes, min margins, contrast
    guard, at least one non-text element per content slide).
  - Return a list of RenderedSlide objects consumed by Stage 4.

The LLM never touches geometry, colors, or font sizes — those decisions live here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol

from .themes import Theme
from .content_planner import SlideOutline, SlideSpec

# ---------------------------------------------------------------------------
# Slide canvas constants (16:9 widescreen, inches)
# ---------------------------------------------------------------------------

SLIDE_W = 13.333
SLIDE_H = 7.5


# ---------------------------------------------------------------------------
# Typography constants (from AGENT_PROMPT spec)
# ---------------------------------------------------------------------------

FONT_TITLE_MIN = 36
FONT_TITLE_MAX = 44
FONT_BODY_DEFAULT = 16
FONT_BODY_MIN = 11
FONT_CAPTION = 11

# Avg characters that fit per inch at a given font size (rough heuristic).
# Calibrated for Calibri/Cambria at standard metrics.
CHARS_PER_INCH_AT_16PT = 8.5


# ---------------------------------------------------------------------------
# Output dataclasses (consumed by Stage 4)
# ---------------------------------------------------------------------------


@dataclass
class ShapeSpec:
    shape_kind: Literal["textbox", "table", "chart", "image_placeholder", "rounded_rect"]
    x_in: float
    y_in: float
    w_in: float
    h_in: float
    content: Dict[str, Any]
    font_size_pt: Optional[int] = None
    fill_color: Optional[str] = None
    text_color: Optional[str] = None
    z_order: int = 0


@dataclass
class RenderedSlide:
    slide_type: str
    background_color: str
    shapes: List[ShapeSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _fit_font(text: str, box_w: float, box_h: float,
              start_pt: int = FONT_BODY_DEFAULT,
              min_pt: int = FONT_BODY_MIN) -> int:
    """
    Step font size down in 1pt increments until the text fits the box,
    or clamp at min_pt. Returns the chosen font size.
    """
    chars_per_line_at_start = max(1, box_w * CHARS_PER_INCH_AT_16PT * (16 / start_pt))
    lines_available = max(1, box_h / (start_pt / 72 * 1.4 * 96 / 72))  # rough line height

    for pt in range(start_pt, min_pt - 1, -1):
        cpl = max(1, box_w * CHARS_PER_INCH_AT_16PT * (16 / pt))
        lh = pt / 72 * 1.4  # inches, 1.4 line-height multiplier
        lines_avail = max(1, box_h / lh)
        total_chars_fit = cpl * lines_avail
        if len(text) <= total_chars_fit:
            return pt
    return min_pt


def _fit_bullets(bullets: List[str], box_w: float, box_h: float,
                 start_pt: int = FONT_BODY_DEFAULT,
                 min_pt: int = FONT_BODY_MIN) -> tuple[int, List[str]]:
    """
    Returns (font_size, trimmed_bullets) so the list fits the box.
    Tries stepping font down first; if still overflowing at min_pt, truncates bullets.
    """
    for pt in range(start_pt, min_pt - 1, -1):
        lh_in = pt / 72 * 1.4
        max_lines = max(1, int(box_h / lh_in))
        # estimate lines per bullet (average 65 chars per line at 16pt, scaled)
        cpl = max(1, int(box_w * CHARS_PER_INCH_AT_16PT * (16 / pt)))
        total_lines = sum(math.ceil(len(b) / cpl) for b in bullets)
        if total_lines <= max_lines:
            return pt, bullets

    # At floor font, truncate bullets to fit
    pt = min_pt
    lh_in = pt / 72 * 1.4
    max_lines = max(1, int(box_h / lh_in))
    cpl = max(1, int(box_w * CHARS_PER_INCH_AT_16PT * (16 / pt)))
    kept: List[str] = []
    used_lines = 0
    for b in bullets:
        needed = math.ceil(len(b) / cpl)
        if used_lines + needed > max_lines:
            break
        kept.append(b)
        used_lines += needed
    return pt, kept


def _is_dark_slide(slide_type: str, theme: Theme) -> bool:
    """True when this slide should use bg_dark (title and closing slides for sandwich mode)."""
    dark_types = {"title", "ask_closing"}
    if theme.contrast_mode == "dark_throughout":
        return True
    return slide_type in dark_types


def _bg_color(slide_type: str, theme: Theme) -> str:
    return theme.colors.bg_dark if _is_dark_slide(slide_type, theme) else theme.colors.bg_light


def _text_color(slide_type: str, theme: Theme) -> str:
    return theme.colors.text_on_dark if _is_dark_slide(slide_type, theme) else theme.colors.text_on_light


def _card_fill(theme: Theme, on_dark: bool) -> str:
    """
    Contrast guard: never return a near-white fill to be used on a light background
    as a large standalone block. Safe small-element colors only on dark backgrounds.
    """
    if on_dark:
        # A semi-dark card on bg_dark: use primary with ~25% lightening effect by
        # returning card_bg (which is always a light tone, safe on dark as text bg)
        return theme.colors.card_bg
    return theme.colors.card_bg


def _motif_shape(theme: Theme, x: float, y: float,
                 size: float = 0.45, color: Optional[str] = None) -> ShapeSpec:
    """
    Emit the theme's motif element (icon container) — never a stripe.
    Used as the 'at least one non-text visual' guarantee for content slides.
    """
    fill = color or theme.colors.primary
    return ShapeSpec(
        shape_kind="rounded_rect",
        x_in=x, y_in=y,
        w_in=size, h_in=size,
        content={"motif": theme.motif.shape_style, "icon_container": theme.motif.icon_container},
        fill_color=fill,
        z_order=1,
    )


def _title_shape(title: str, theme: Theme, x: float, y: float,
                 w: float, h: float = 0.7, on_dark: bool = False,
                 font_size: int = 38) -> ShapeSpec:
    tc = theme.colors.text_on_dark if on_dark else theme.colors.text_on_light
    return ShapeSpec(
        shape_kind="textbox",
        x_in=x, y_in=y, w_in=w, h_in=h,
        content={"text": title, "bold": True, "align": "left"},
        font_size_pt=font_size,
        text_color=tc,
        z_order=10,
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class SlideLayout(Protocol):
    def variants(self) -> List[str]: ...
    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str: ...
    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide: ...


# ---------------------------------------------------------------------------
# Helper: standard content-slide header block (title + decorative motif)
# ---------------------------------------------------------------------------


def _standard_header(slide_data: SlideSpec, theme: Theme, on_dark: bool) -> List[ShapeSpec]:
    """
    Returns title textbox + a small motif accent shape.
    No accent stripe/color-bar — the motif element is always a small shape.
    """
    M = theme.spacing.margin_in
    shapes: List[ShapeSpec] = []

    title_font = FONT_TITLE_MIN + 2  # 38pt default for content slides
    shapes.append(_title_shape(
        slide_data.title, theme,
        x=M, y=0.3,
        w=SLIDE_W - 2 * M - 0.6,
        h=0.65, on_dark=on_dark,
        font_size=title_font,
    ))
    # Small motif shape top-right (non-text visual anchor)
    shapes.append(_motif_shape(theme, x=SLIDE_W - M - 0.5, y=0.3, size=0.45,
                               color=theme.colors.primary))
    return shapes


# ---------------------------------------------------------------------------
# SLIDE TYPE: title
# ---------------------------------------------------------------------------


class TitleLayout:
    def variants(self) -> List[str]:
        return ["centered_hero", "left_aligned_hero", "split_bg"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        return "left_aligned_hero"  # title is always position 0

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        bg = theme.colors.bg_dark
        M = theme.spacing.margin_in
        on_dark = True
        shapes: List[ShapeSpec] = []

        # Large background fill (whole slide)
        shapes.append(ShapeSpec(
            shape_kind="rounded_rect",
            x_in=0, y_in=0, w_in=SLIDE_W, h_in=SLIDE_H,
            content={"motif": "background"},
            fill_color=bg, z_order=0,
        ))

        # Hero title
        title_text = slide_data.body.bullets[0] if slide_data.body.bullets else slide_data.title
        shapes.append(ShapeSpec(
            shape_kind="textbox",
            x_in=M, y_in=1.8, w_in=SLIDE_W - 2 * M, h_in=1.6,
            content={"text": title_text, "bold": True, "align": "left"},
            font_size_pt=FONT_TITLE_MAX,
            text_color=theme.colors.text_on_dark,
            z_order=10,
        ))

        # Tagline / subtitle
        if slide_data.body.bullets and len(slide_data.body.bullets) > 1:
            tagline = slide_data.body.bullets[1]
        else:
            tagline = slide_data.title
        shapes.append(ShapeSpec(
            shape_kind="textbox",
            x_in=M, y_in=3.55, w_in=SLIDE_W - 2 * M, h_in=0.65,
            content={"text": tagline, "bold": False, "align": "left"},
            font_size_pt=22,
            text_color=theme.colors.accent if theme.colors.accent != "FFFFFF" else theme.colors.secondary,
            z_order=11,
        ))

        # Motif accent — small icon container bottom-right
        shapes.append(_motif_shape(theme, x=SLIDE_W - M - 0.6, y=SLIDE_H - 1.1, size=0.5,
                                   color=theme.colors.secondary))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: agenda
# ---------------------------------------------------------------------------


class AgendaLayout:
    def variants(self) -> List[str]:
        return ["numbered_list", "card_grid"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        return "card_grid" if len(slide_data.body.bullets or []) >= 4 else "numbered_list"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        bullets = slide_data.body.bullets or []
        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M
        tc = _text_color(slide_data.slide_type, theme)

        if variant == "card_grid" and bullets:
            n = len(bullets)
            cols = min(3, n)
            rows = math.ceil(n / cols)
            card_w = (avail_w - G * (cols - 1)) / cols
            card_h = (avail_h - G * (rows - 1)) / rows
            for i, b in enumerate(bullets):
                col = i % cols
                row = i // cols
                cx = M + col * (card_w + G)
                cy = start_y + row * (card_h + G)
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=cx, y_in=cy, w_in=card_w, h_in=card_h,
                    content={"motif": "card"},
                    fill_color=theme.colors.card_bg, z_order=2,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.2, y_in=cy + 0.15, w_in=card_w - 0.35, h_in=card_h - 0.25,
                    content={"text": f"{i+1}. {b}", "bold": False, "align": "left"},
                    font_size_pt=FONT_BODY_DEFAULT,
                    text_color=tc, z_order=3,
                ))
        else:
            # numbered_list variant
            pt, trimmed = _fit_bullets(bullets, avail_w - 0.5, avail_h)
            for i, b in enumerate(trimmed):
                item_y = start_y + i * (pt / 72 * 1.6 + 0.08)
                # Number accent
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=M, y_in=item_y, w_in=0.32, h_in=0.32,
                    content={"motif": "number_badge"},
                    fill_color=theme.colors.primary, z_order=2,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M, y_in=item_y, w_in=0.32, h_in=0.32,
                    content={"text": str(i + 1), "bold": True, "align": "center"},
                    font_size_pt=12, text_color=theme.colors.text_on_dark, z_order=3,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.45, y_in=item_y, w_in=avail_w - 0.5, h_in=0.38,
                    content={"text": b, "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=3,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: problem
# ---------------------------------------------------------------------------


class ProblemLayout:
    def variants(self) -> List[str]:
        return ["single_pain_callout", "two_column", "pain_with_stat"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.stat_callout:
            return "pain_with_stat"
        if density == "heavy" or len(slide_data.body.bullets or []) >= 4:
            return "two_column"
        return "single_pain_callout"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        bullets = slide_data.body.bullets or []
        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        if variant == "pain_with_stat" and slide_data.body.stat_callout:
            sc = slide_data.body.stat_callout
            # Left: big stat
            stat_w = 3.5
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=start_y, w_in=stat_w, h_in=avail_h,
                content={"motif": "stat_card"},
                fill_color=theme.colors.primary, z_order=2,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.2, y_in=start_y + 0.6, w_in=stat_w - 0.4, h_in=1.2,
                content={"text": sc.number, "bold": True, "align": "center"},
                font_size_pt=54, text_color=theme.colors.text_on_dark, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.2, y_in=start_y + 1.9, w_in=stat_w - 0.4, h_in=0.5,
                content={"text": sc.label, "bold": False, "align": "center"},
                font_size_pt=14, text_color=theme.colors.text_on_dark, z_order=10,
            ))
            # Right: bullets
            right_x = M + stat_w + G
            right_w = SLIDE_W - right_x - M
            pt, trimmed = _fit_bullets(bullets, right_w, avail_h)
            for i, b in enumerate(trimmed):
                by = start_y + i * (avail_h / max(len(trimmed), 1))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=right_x, y_in=by, w_in=right_w, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                    content={"text": f"• {b}", "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        elif variant == "two_column" and bullets:
            half = math.ceil(len(bullets) / 2)
            left_bullets = bullets[:half]
            right_bullets = bullets[half:]
            col_w = (avail_w - G) / 2
            for col_idx, col_bullets in enumerate([left_bullets, right_bullets]):
                cx = M + col_idx * (col_w + G)
                pt, trimmed = _fit_bullets(col_bullets, col_w - 0.1, avail_h)
                for i, b in enumerate(trimmed):
                    by = start_y + i * (avail_h / max(len(trimmed), 1))
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx, y_in=by, w_in=col_w - 0.1, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                        content={"text": f"• {b}", "bold": False, "align": "left"},
                        font_size_pt=pt, text_color=tc, z_order=10,
                    ))
            # Motif decoration
            shapes.append(_motif_shape(theme, x=SLIDE_W / 2 - 0.22, y=start_y + avail_h / 2 - 0.22,
                                       size=0.44, color=theme.colors.primary))

        else:
            # single_pain_callout
            pt, trimmed = _fit_bullets(bullets, avail_w, avail_h)
            for i, b in enumerate(trimmed):
                by = start_y + i * (avail_h / max(len(trimmed), 1))
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=M, y_in=by, w_in=avail_w, h_in=avail_h / max(len(trimmed), 1) - 0.08,
                    content={"motif": "card"},
                    fill_color=theme.colors.card_bg, z_order=2,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.2, y_in=by + 0.1, w_in=avail_w - 0.35, h_in=avail_h / max(len(trimmed), 1) - 0.25,
                    content={"text": b, "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: solution
# ---------------------------------------------------------------------------


class SolutionLayout:
    def variants(self) -> List[str]:
        return ["feature_cards_3col", "feature_cards_2col", "hero_plus_list"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        n = len(slide_data.body.bullets or [])
        if n >= 4:
            return "feature_cards_3col"
        if n >= 2:
            return "feature_cards_2col"
        return "hero_plus_list"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        bullets = slide_data.body.bullets or []
        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        cols = 3 if variant == "feature_cards_3col" else (2 if variant == "feature_cards_2col" else 1)
        n = len(bullets)
        if n == 0:
            shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, SLIDE_H / 2 - 0.22, 0.5))
            return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)

        rows = math.ceil(n / cols)
        card_w = (avail_w - G * (cols - 1)) / cols
        card_h = (avail_h - G * (rows - 1)) / rows

        for i, b in enumerate(bullets):
            col = i % cols
            row = i // cols
            cx = M + col * (card_w + G)
            cy = start_y + row * (card_h + G)

            # Parse "Title: body" or "Title — body" from bullets
            if ": " in b:
                card_title, card_body = b.split(": ", 1)
            elif " — " in b or " - " in b:
                sep = " — " if " — " in b else " - "
                card_title, card_body = b.split(sep, 1)
            else:
                card_title = b[:40]
                card_body = b[40:] if len(b) > 40 else ""

            # Card background
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=cx, y_in=cy, w_in=card_w, h_in=card_h,
                content={"motif": "card"},
                fill_color=theme.colors.card_bg, z_order=2,
            ))
            # Motif element (icon container) in top-left of card
            shapes.append(_motif_shape(theme, cx + 0.15, cy + 0.12, 0.32,
                                       color=theme.colors.primary))
            # Card title
            title_pt = min(15, max(11, int(card_h * 10)))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=cx + 0.55, y_in=cy + 0.12, w_in=card_w - 0.65, h_in=0.38,
                content={"text": card_title, "bold": True, "align": "left"},
                font_size_pt=title_pt, text_color=tc, z_order=10,
            ))
            # Card body
            body_y = cy + 0.55
            body_h = card_h - 0.6
            pt = _fit_font(card_body, card_w - 0.3, body_h, start_pt=13)
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=cx + 0.15, y_in=body_y, w_in=card_w - 0.3, h_in=body_h,
                content={"text": card_body, "bold": False, "align": "left"},
                font_size_pt=pt, text_color=theme.colors.text_muted, z_order=10,
            ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: market_sizing
# ---------------------------------------------------------------------------


class MarketSizingLayout:
    def variants(self) -> List[str]:
        return ["stat_callout_bullets", "tam_sam_som_bars", "chart_view"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.chart_data:
            return "chart_view"
        if slide_data.body.stat_callout:
            return "stat_callout_bullets"
        return "tam_sam_som_bars"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        if variant == "chart_view" and slide_data.body.chart_data:
            shapes.append(ShapeSpec(
                shape_kind="chart",
                x_in=M, y_in=start_y, w_in=avail_w * 0.65, h_in=avail_h,
                content={"chart_data": slide_data.body.chart_data.model_dump()},
                z_order=5,
            ))
            bullets = slide_data.body.bullets or []
            if bullets:
                right_x = M + avail_w * 0.65 + G
                right_w = SLIDE_W - right_x - M
                pt, trimmed = _fit_bullets(bullets, right_w, avail_h)
                for i, b in enumerate(trimmed):
                    by = start_y + i * (avail_h / max(len(trimmed), 1))
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=right_x, y_in=by, w_in=right_w, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                        content={"text": f"• {b}", "bold": False, "align": "left"},
                        font_size_pt=pt, text_color=tc, z_order=10,
                    ))

        elif variant == "stat_callout_bullets" and slide_data.body.stat_callout:
            sc = slide_data.body.stat_callout
            # Giant stat on left
            stat_w = 4.0
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=start_y, w_in=stat_w, h_in=avail_h,
                content={"motif": "stat_card"},
                fill_color=theme.colors.primary, z_order=2,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.2, y_in=start_y + 0.8, w_in=stat_w - 0.4, h_in=1.4,
                content={"text": sc.number, "bold": True, "align": "center"},
                font_size_pt=60, text_color=theme.colors.text_on_dark, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.2, y_in=start_y + 2.3, w_in=stat_w - 0.4, h_in=0.5,
                content={"text": sc.label, "bold": False, "align": "center"},
                font_size_pt=14, text_color=theme.colors.text_on_dark, z_order=10,
            ))
            bullets = slide_data.body.bullets or []
            right_x = M + stat_w + G
            right_w = SLIDE_W - right_x - M
            pt, trimmed = _fit_bullets(bullets, right_w, avail_h)
            for i, b in enumerate(trimmed):
                by = start_y + i * (avail_h / max(len(trimmed), 1))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=right_x, y_in=by, w_in=right_w, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                    content={"text": f"• {b}", "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        else:
            # tam_sam_som_bars: three stacked colored bars with labels
            labels = ["TAM", "SAM", "SOM"]
            bullets = slide_data.body.bullets or []
            bar_colors = [theme.colors.primary, theme.colors.secondary, theme.colors.card_bg]
            bar_h = min(avail_h / 3 - G * 0.5, 1.4)
            bar_widths = [avail_w * 0.8, avail_w * 0.55, avail_w * 0.35]
            for i in range(3):
                by = start_y + i * (bar_h + G * 0.5)
                label_text = labels[i]
                body_text = bullets[i] if i < len(bullets) else ""
                # Contrast guard: only use primary (dark) as fill when on light bg
                fill = theme.colors.primary if i == 0 else (theme.colors.card_bg if i >= 1 else theme.colors.secondary)
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=M, y_in=by, w_in=bar_widths[i], h_in=bar_h,
                    content={"motif": "market_bar"},
                    fill_color=fill, z_order=2,
                ))
                bar_tc = theme.colors.text_on_dark if i == 0 else tc
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.2, y_in=by + 0.1, w_in=bar_widths[i] - 0.3, h_in=bar_h - 0.15,
                    content={"text": f"{label_text}  {body_text}", "bold": i == 0, "align": "left"},
                    font_size_pt=FONT_BODY_DEFAULT if i == 0 else 14,
                    text_color=bar_tc, z_order=10,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: competitive_matrix
# ---------------------------------------------------------------------------


class CompetitiveMatrixLayout:
    def variants(self) -> List[str]:
        return ["comparison_table", "positioning_grid", "feature_checklist"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.table:
            return "comparison_table"
        if density == "light":
            return "positioning_grid"
        return "feature_checklist"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        if variant == "comparison_table" and slide_data.body.table:
            shapes.append(ShapeSpec(
                shape_kind="table",
                x_in=M, y_in=start_y, w_in=avail_w, h_in=avail_h,
                content={"table": slide_data.body.table.model_dump()},
                font_size_pt=13,
                text_color=tc,
                fill_color=theme.colors.card_bg,
                z_order=5,
            ))

        elif variant == "positioning_grid":
            # 2x2 quadrant grid
            center_x = M + avail_w / 2
            center_y = start_y + avail_h / 2
            quad_w = avail_w / 2 - G / 2
            quad_h = avail_h / 2 - G / 2
            quadrant_labels = ["Low Value\nLow Cost", "High Value\nLow Cost",
                               "Low Value\nHigh Cost", "High Value\nHigh Cost (Us)"]
            fills = [theme.colors.card_bg, theme.colors.card_bg,
                     theme.colors.card_bg, theme.colors.primary]
            for i, (qlabel, qfill) in enumerate(zip(quadrant_labels, fills)):
                col = i % 2
                row = i // 2
                qx = M + col * (quad_w + G)
                qy = start_y + row * (quad_h + G)
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=qx, y_in=qy, w_in=quad_w, h_in=quad_h,
                    content={"motif": "quadrant"},
                    fill_color=qfill, z_order=2,
                ))
                quad_tc = theme.colors.text_on_dark if i == 3 else tc
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=qx + 0.15, y_in=qy + 0.15, w_in=quad_w - 0.3, h_in=quad_h - 0.3,
                    content={"text": qlabel, "bold": i == 3, "align": "center"},
                    font_size_pt=13, text_color=quad_tc, z_order=10,
                ))

        else:
            # feature_checklist: two columns — competitors (✗) vs us (✓)
            bullets = slide_data.body.bullets or []
            col_w = (avail_w - G) / 2
            col_headers = ["Competitors", "Our Approach"]
            col_fills = [theme.colors.card_bg, theme.colors.primary]
            col_tcs = [tc, theme.colors.text_on_dark]
            for col_i, (header, fill, col_tc) in enumerate(zip(col_headers, col_fills, col_tcs)):
                cx = M + col_i * (col_w + G)
                # Header row
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=cx, y_in=start_y, w_in=col_w, h_in=0.45,
                    content={"motif": "column_header"},
                    fill_color=fill, z_order=2,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.1, y_in=start_y + 0.05, w_in=col_w - 0.2, h_in=0.35,
                    content={"text": header, "bold": True, "align": "center"},
                    font_size_pt=14, text_color=col_tc, z_order=10,
                ))
                row_h = (avail_h - 0.55) / max(len(bullets), 1)
                for j, b in enumerate(bullets):
                    ry = start_y + 0.55 + j * row_h
                    icon = "✗" if col_i == 0 else "✓"
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx + 0.1, y_in=ry, w_in=col_w - 0.2, h_in=row_h - 0.05,
                        content={"text": f"{icon}  {b}", "bold": False, "align": "left"},
                        font_size_pt=13, text_color=tc, z_order=10,
                    ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: business_model
# ---------------------------------------------------------------------------


class BusinessModelLayout:
    def variants(self) -> List[str]:
        return ["revenue_stream_cards", "two_column_text", "table_view"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.table:
            return "table_view"
        if density == "heavy":
            return "two_column_text"
        return "revenue_stream_cards"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M
        bullets = slide_data.body.bullets or []

        if variant == "table_view" and slide_data.body.table:
            shapes.append(ShapeSpec(
                shape_kind="table",
                x_in=M, y_in=start_y, w_in=avail_w, h_in=avail_h,
                content={"table": slide_data.body.table.model_dump()},
                font_size_pt=13, text_color=tc, fill_color=theme.colors.card_bg, z_order=5,
            ))

        elif variant == "two_column_text" and bullets:
            half = math.ceil(len(bullets) / 2)
            col_w = (avail_w - G) / 2
            for col_i, col_bulls in enumerate([bullets[:half], bullets[half:]]):
                cx = M + col_i * (col_w + G)
                pt, trimmed = _fit_bullets(col_bulls, col_w, avail_h)
                for j, b in enumerate(trimmed):
                    by = start_y + j * (avail_h / max(len(trimmed), 1))
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx, y_in=by, w_in=col_w, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                        content={"text": f"• {b}", "bold": False, "align": "left"},
                        font_size_pt=pt, text_color=tc, z_order=10,
                    ))
            shapes.append(_motif_shape(theme, SLIDE_W - M - 0.5, SLIDE_H - M - 0.5))

        else:
            # revenue_stream_cards
            n = len(bullets)
            if n == 0:
                shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, SLIDE_H / 2 - 0.22))
                return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)
            cols = min(3, n)
            rows = math.ceil(n / cols)
            card_w = (avail_w - G * (cols - 1)) / cols
            card_h = (avail_h - G * (rows - 1)) / rows
            for i, b in enumerate(bullets):
                col = i % cols
                row = i // cols
                cx = M + col * (card_w + G)
                cy = start_y + row * (card_h + G)
                if ": " in b:
                    ctitle, cbody = b.split(": ", 1)
                else:
                    ctitle, cbody = b[:35], b[35:]
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=cx, y_in=cy, w_in=card_w, h_in=card_h,
                    content={"motif": "revenue_card"},
                    fill_color=theme.colors.card_bg, z_order=2,
                ))
                shapes.append(_motif_shape(theme, cx + 0.15, cy + 0.1, 0.3, theme.colors.primary))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.55, y_in=cy + 0.1, w_in=card_w - 0.65, h_in=0.35,
                    content={"text": ctitle, "bold": True, "align": "left"},
                    font_size_pt=14, text_color=tc, z_order=10,
                ))
                pt = _fit_font(cbody, card_w - 0.3, card_h - 0.5, start_pt=13)
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.15, y_in=cy + 0.5, w_in=card_w - 0.3, h_in=card_h - 0.6,
                    content={"text": cbody, "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=theme.colors.text_muted, z_order=10,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: traction
# ---------------------------------------------------------------------------


class TractionLayout:
    def variants(self) -> List[str]:
        return ["kpi_grid", "chart_with_bullets", "milestone_timeline"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.chart_data:
            return "chart_with_bullets"
        if slide_data.body.stat_callout:
            return "kpi_grid"
        return "milestone_timeline"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        if variant == "chart_with_bullets" and slide_data.body.chart_data:
            chart_w = avail_w * 0.6
            shapes.append(ShapeSpec(
                shape_kind="chart",
                x_in=M, y_in=start_y, w_in=chart_w, h_in=avail_h,
                content={"chart_data": slide_data.body.chart_data.model_dump()}, z_order=5,
            ))
            bullets = slide_data.body.bullets or []
            right_x = M + chart_w + G
            right_w = SLIDE_W - right_x - M
            pt, trimmed = _fit_bullets(bullets, right_w, avail_h)
            for i, b in enumerate(trimmed):
                by = start_y + i * (avail_h / max(len(trimmed), 1))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=right_x, y_in=by, w_in=right_w, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                    content={"text": f"• {b}", "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        elif variant == "kpi_grid" and slide_data.body.stat_callout:
            sc = slide_data.body.stat_callout
            stat_cards = [{"number": sc.number, "label": sc.label}]
            bullets = slide_data.body.bullets or []
            for b in bullets[:3]:
                parts = b.split(":", 1) if ":" in b else (b.split(" ", 1) if " " in b else [b, ""])
                stat_cards.append({"number": parts[0].strip(), "label": parts[-1].strip()[:40]})
            n_cards = min(len(stat_cards), 4)
            card_w = (avail_w - G * (n_cards - 1)) / n_cards
            for i, card in enumerate(stat_cards[:n_cards]):
                cx = M + i * (card_w + G)
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=cx, y_in=start_y, w_in=card_w, h_in=avail_h * 0.55,
                    content={"motif": "kpi_card"},
                    fill_color=theme.colors.primary if i == 0 else theme.colors.card_bg, z_order=2,
                ))
                card_tc = theme.colors.text_on_dark if i == 0 else tc
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.1, y_in=start_y + 0.3, w_in=card_w - 0.2, h_in=0.9,
                    content={"text": card["number"], "bold": True, "align": "center"},
                    font_size_pt=36, text_color=card_tc, z_order=10,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.1, y_in=start_y + 1.3, w_in=card_w - 0.2, h_in=0.4,
                    content={"text": card["label"], "bold": False, "align": "center"},
                    font_size_pt=12, text_color=card_tc, z_order=10,
                ))

        else:
            # milestone_timeline
            bullets = slide_data.body.bullets or []
            n = len(bullets)
            if n == 0:
                shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, SLIDE_H / 2 - 0.22))
                return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)
            step_w = avail_w / n
            track_y = start_y + avail_h * 0.35
            # Horizontal track line
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=track_y, w_in=avail_w, h_in=0.04,
                content={"motif": "timeline_track"},
                fill_color=theme.colors.secondary, z_order=1,
            ))
            for i, b in enumerate(bullets):
                dot_x = M + i * step_w + step_w / 2 - 0.15
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=dot_x, y_in=track_y - 0.15, w_in=0.3, h_in=0.3,
                    content={"motif": "timeline_dot"},
                    fill_color=theme.colors.primary, z_order=3,
                ))
                box_y = start_y if i % 2 == 0 else track_y + 0.35
                box_h = min(track_y - start_y - 0.1, 1.2) if i % 2 == 0 else avail_h - (track_y - start_y) - 0.45
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + i * step_w, y_in=box_y, w_in=step_w - 0.1, h_in=box_h,
                    content={"text": b, "bold": False, "align": "center"},
                    font_size_pt=13, text_color=tc, z_order=10,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: financials_chart
# ---------------------------------------------------------------------------


class FinancialsChartLayout:
    def variants(self) -> List[str]:
        return ["full_chart", "chart_plus_table", "chart_plus_callout"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.table:
            return "chart_plus_table"
        if slide_data.body.stat_callout:
            return "chart_plus_callout"
        return "full_chart"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M

        chart_data = slide_data.body.chart_data
        if chart_data is None:
            # Fallback: placeholder
            shapes.append(ShapeSpec(
                shape_kind="image_placeholder",
                x_in=M, y_in=start_y, w_in=avail_w, h_in=avail_h,
                content={"label": "Financial chart — data not provided"},
                z_order=5,
            ))
            return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)

        if variant == "chart_plus_table" and slide_data.body.table:
            chart_h = avail_h * 0.6
            shapes.append(ShapeSpec(
                shape_kind="chart",
                x_in=M, y_in=start_y, w_in=avail_w, h_in=chart_h,
                content={"chart_data": chart_data.model_dump()}, z_order=5,
            ))
            shapes.append(ShapeSpec(
                shape_kind="table",
                x_in=M, y_in=start_y + chart_h + G, w_in=avail_w, h_in=avail_h - chart_h - G,
                content={"table": slide_data.body.table.model_dump()},
                font_size_pt=12, fill_color=theme.colors.card_bg, z_order=5,
            ))

        elif variant == "chart_plus_callout" and slide_data.body.stat_callout:
            sc = slide_data.body.stat_callout
            chart_w = avail_w * 0.7
            shapes.append(ShapeSpec(
                shape_kind="chart",
                x_in=M, y_in=start_y, w_in=chart_w, h_in=avail_h,
                content={"chart_data": chart_data.model_dump()}, z_order=5,
            ))
            cbox_x = M + chart_w + G
            cbox_w = SLIDE_W - cbox_x - M
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=cbox_x, y_in=start_y + avail_h * 0.2,
                w_in=cbox_w, h_in=avail_h * 0.5,
                content={"motif": "callout_card"},
                fill_color=theme.colors.primary, z_order=2,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=cbox_x + 0.1, y_in=start_y + avail_h * 0.2 + 0.25,
                w_in=cbox_w - 0.2, h_in=1.0,
                content={"text": sc.number, "bold": True, "align": "center"},
                font_size_pt=44, text_color=theme.colors.text_on_dark, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=cbox_x + 0.1, y_in=start_y + avail_h * 0.2 + 1.35,
                w_in=cbox_w - 0.2, h_in=0.45,
                content={"text": sc.label, "bold": False, "align": "center"},
                font_size_pt=13, text_color=theme.colors.text_on_dark, z_order=10,
            ))

        else:
            shapes.append(ShapeSpec(
                shape_kind="chart",
                x_in=M, y_in=start_y, w_in=avail_w, h_in=avail_h,
                content={"chart_data": chart_data.model_dump()}, z_order=5,
            ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: team
# ---------------------------------------------------------------------------


class TeamLayout:
    def variants(self) -> List[str]:
        return ["photo_grid", "horizontal_row", "text_cards"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        n = len(slide_data.body.bullets or [])
        if n >= 4:
            return "photo_grid"
        if n >= 2:
            return "horizontal_row"
        return "text_cards"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M
        bullets = slide_data.body.bullets or []
        n = len(bullets)

        if n == 0:
            shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, SLIDE_H / 2 - 0.22))
            return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)

        if variant == "photo_grid":
            cols = min(4, n)
            rows = math.ceil(n / cols)
            card_w = (avail_w - G * (cols - 1)) / cols
            card_h = (avail_h - G * (rows - 1)) / rows
            for i, b in enumerate(bullets):
                col = i % cols
                row = i // cols
                cx = M + col * (card_w + G)
                cy = start_y + row * (card_h + G)
                # Circle image placeholder
                circle_size = min(card_w * 0.55, card_h * 0.55)
                circle_x = cx + (card_w - circle_size) / 2
                shapes.append(ShapeSpec(
                    shape_kind="image_placeholder",
                    x_in=circle_x, y_in=cy, w_in=circle_size, h_in=circle_size,
                    content={"label": b.split(":")[0] if ":" in b else b[:20], "shape": "circle"},
                    fill_color=theme.colors.primary, z_order=5,
                ))
                # Name/role below
                name_part = b.split(":")[0] if ":" in b else b[:30]
                role_part = b.split(":", 1)[1].strip() if ":" in b else ""
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx, y_in=cy + circle_size + 0.05, w_in=card_w, h_in=0.3,
                    content={"text": name_part, "bold": True, "align": "center"},
                    font_size_pt=13, text_color=tc, z_order=10,
                ))
                if role_part:
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx, y_in=cy + circle_size + 0.37, w_in=card_w, h_in=0.25,
                        content={"text": role_part, "bold": False, "align": "center"},
                        font_size_pt=11, text_color=theme.colors.text_muted, z_order=10,
                    ))

        else:
            # horizontal_row and text_cards
            card_w = (avail_w - G * (n - 1)) / n
            for i, b in enumerate(bullets):
                cx = M + i * (card_w + G)
                circle_size = min(card_w * 0.45, 1.1)
                circle_x = cx + (card_w - circle_size) / 2
                shapes.append(ShapeSpec(
                    shape_kind="image_placeholder",
                    x_in=circle_x, y_in=start_y + 0.1, w_in=circle_size, h_in=circle_size,
                    content={"label": b.split(":")[0] if ":" in b else b[:20], "shape": "circle"},
                    fill_color=theme.colors.primary, z_order=5,
                ))
                name_part = b.split(":")[0] if ":" in b else b[:30]
                role_part = b.split(":", 1)[1].strip() if ":" in b else ""
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx, y_in=start_y + circle_size + 0.25, w_in=card_w, h_in=0.35,
                    content={"text": name_part, "bold": True, "align": "center"},
                    font_size_pt=14, text_color=tc, z_order=10,
                ))
                if role_part:
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx, y_in=start_y + circle_size + 0.62, w_in=card_w, h_in=avail_h - circle_size - 0.7,
                        content={"text": role_part, "bold": False, "align": "center"},
                        font_size_pt=12, text_color=theme.colors.text_muted, z_order=10,
                    ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: timeline_roadmap
# ---------------------------------------------------------------------------


class TimelineRoadmapLayout:
    def variants(self) -> List[str]:
        return ["horizontal_timeline", "vertical_phases", "quarter_grid"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        n = len(slide_data.body.bullets or [])
        if n >= 5:
            return "quarter_grid"
        if density == "heavy":
            return "vertical_phases"
        return "horizontal_timeline"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M
        bullets = slide_data.body.bullets or []
        n = max(len(bullets), 1)

        if variant == "quarter_grid":
            # Grid of phase cards
            cols = min(3, n)
            rows = math.ceil(n / cols)
            card_w = (avail_w - G * (cols - 1)) / cols
            card_h = (avail_h - G * (rows - 1)) / rows
            for i, b in enumerate(bullets):
                col = i % cols
                row = i // cols
                cx = M + col * (card_w + G)
                cy = start_y + row * (card_h + G)
                is_current = i == 0
                fill = theme.colors.primary if is_current else theme.colors.card_bg
                card_tc = theme.colors.text_on_dark if is_current else tc
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=cx, y_in=cy, w_in=card_w, h_in=card_h,
                    content={"motif": "phase_card"},
                    fill_color=fill, z_order=2,
                ))
                shapes.append(_motif_shape(theme, cx + 0.12, cy + 0.12, 0.28, theme.colors.secondary))
                pt = _fit_font(b, card_w - 0.3, card_h - 0.25, start_pt=14)
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx + 0.15, y_in=cy + 0.45, w_in=card_w - 0.3, h_in=card_h - 0.55,
                    content={"text": b, "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=card_tc, z_order=10,
                ))

        elif variant == "vertical_phases":
            phase_h = (avail_h - G * (n - 1)) / n
            for i, b in enumerate(bullets):
                by = start_y + i * (phase_h + G)
                # Connector dot
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=M, y_in=by + phase_h / 2 - 0.15, w_in=0.3, h_in=0.3,
                    content={"motif": "phase_dot"},
                    fill_color=theme.colors.primary, z_order=3,
                ))
                # Connector line (not a stripe — it's a thin vertical connector)
                if i < n - 1:
                    shapes.append(ShapeSpec(
                        shape_kind="rounded_rect",
                        x_in=M + 0.13, y_in=by + phase_h, w_in=0.04, h_in=G,
                        content={"motif": "phase_connector"},
                        fill_color=theme.colors.secondary, z_order=1,
                    ))
                pt = _fit_font(b, avail_w - 0.5, phase_h - 0.1, start_pt=FONT_BODY_DEFAULT)
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.45, y_in=by, w_in=avail_w - 0.5, h_in=phase_h - 0.05,
                    content={"text": b, "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        else:
            # horizontal_timeline
            track_y = start_y + avail_h * 0.45
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=track_y, w_in=avail_w, h_in=0.04,
                content={"motif": "timeline_track"},
                fill_color=theme.colors.secondary, z_order=1,
            ))
            step_w = avail_w / n
            for i, b in enumerate(bullets):
                dot_x = M + i * step_w + step_w / 2 - 0.15
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=dot_x, y_in=track_y - 0.14, w_in=0.3, h_in=0.3,
                    content={"motif": "timeline_dot"},
                    fill_color=theme.colors.primary, z_order=3,
                ))
                box_y = start_y if i % 2 == 0 else track_y + 0.35
                box_h = track_y - start_y - 0.12
                pt = _fit_font(b, step_w - 0.12, box_h, start_pt=13)
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + i * step_w + 0.05, y_in=box_y, w_in=step_w - 0.1, h_in=box_h,
                    content={"text": b, "bold": False, "align": "center"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: ask_closing
# ---------------------------------------------------------------------------


class AskClosingLayout:
    def variants(self) -> List[str]:
        return ["centered_ask", "split_ask_contact", "ask_with_milestones"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        bullets = slide_data.body.bullets or []
        if len(bullets) >= 3:
            return "ask_with_milestones"
        if len(bullets) == 2:
            return "split_ask_contact"
        return "centered_ask"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        bg = theme.colors.bg_dark
        on_dark = True
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = theme.colors.text_on_dark
        shapes: List[ShapeSpec] = []

        # Full dark background
        shapes.append(ShapeSpec(
            shape_kind="rounded_rect",
            x_in=0, y_in=0, w_in=SLIDE_W, h_in=SLIDE_H,
            content={"motif": "background"},
            fill_color=bg, z_order=0,
        ))

        title_text = slide_data.title
        bullets = slide_data.body.bullets or []

        if variant == "centered_ask":
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M, y_in=1.8, w_in=SLIDE_W - 2 * M, h_in=1.4,
                content={"text": title_text, "bold": True, "align": "center"},
                font_size_pt=FONT_TITLE_MAX, text_color=tc, z_order=10,
            ))
            if bullets:
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M, y_in=3.4, w_in=SLIDE_W - 2 * M, h_in=0.6,
                    content={"text": bullets[0], "bold": False, "align": "center"},
                    font_size_pt=20, text_color=theme.colors.secondary, z_order=10,
                ))
            shapes.append(_motif_shape(theme, SLIDE_W - M - 0.6, SLIDE_H - M - 0.6, 0.5,
                                       theme.colors.secondary))

        elif variant == "split_ask_contact":
            col_w = (SLIDE_W - 2 * M - G) / 2
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M, y_in=1.5, w_in=col_w, h_in=1.4,
                content={"text": title_text, "bold": True, "align": "left"},
                font_size_pt=FONT_TITLE_MIN, text_color=tc, z_order=10,
            ))
            if len(bullets) >= 1:
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M, y_in=3.1, w_in=col_w, h_in=0.55,
                    content={"text": bullets[0], "bold": False, "align": "left"},
                    font_size_pt=18, text_color=theme.colors.secondary, z_order=10,
                ))
            if len(bullets) >= 2:
                right_x = M + col_w + G
                shapes.append(ShapeSpec(
                    shape_kind="rounded_rect",
                    x_in=right_x, y_in=1.5, w_in=col_w, h_in=2.5,
                    content={"motif": "contact_card"},
                    fill_color=theme.colors.card_bg, z_order=2,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=right_x + 0.2, y_in=1.7, w_in=col_w - 0.35, h_in=2.1,
                    content={"text": bullets[1], "bold": False, "align": "left"},
                    font_size_pt=15, text_color=theme.colors.text_on_light, z_order=10,
                ))

        else:
            # ask_with_milestones
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M, y_in=1.2, w_in=SLIDE_W - 2 * M, h_in=1.0,
                content={"text": title_text, "bold": True, "align": "left"},
                font_size_pt=FONT_TITLE_MIN, text_color=tc, z_order=10,
            ))
            milestone_y = 2.4
            avail_h = SLIDE_H - milestone_y - M
            n = len(bullets)
            if n > 0:
                card_w = (SLIDE_W - 2 * M - G * (n - 1)) / n
                for i, b in enumerate(bullets):
                    cx = M + i * (card_w + G)
                    shapes.append(ShapeSpec(
                        shape_kind="rounded_rect",
                        x_in=cx, y_in=milestone_y, w_in=card_w, h_in=avail_h,
                        content={"motif": "milestone_card"},
                        fill_color=theme.colors.card_bg, z_order=2,
                    ))
                    shapes.append(_motif_shape(theme, cx + 0.12, milestone_y + 0.12, 0.3,
                                               theme.colors.primary))
                    pt = _fit_font(b, card_w - 0.3, avail_h - 0.25, start_pt=14)
                    shapes.append(ShapeSpec(
                        shape_kind="textbox",
                        x_in=cx + 0.15, y_in=milestone_y + 0.48, w_in=card_w - 0.3, h_in=avail_h - 0.55,
                        content={"text": b, "bold": False, "align": "left"},
                        font_size_pt=pt, text_color=theme.colors.text_on_light, z_order=10,
                    ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: quote_callout
# ---------------------------------------------------------------------------


class QuoteCalloutLayout:
    def variants(self) -> List[str]:
        return ["centered_quote", "side_accent_quote", "quote_with_stat"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        if slide_data.body.stat_callout:
            return "quote_with_stat"
        if position_in_deck % 2 == 0:
            return "side_accent_quote"
        return "centered_quote"

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        quote = slide_data.body.quote
        if not quote:
            shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, SLIDE_H / 2 - 0.22))
            return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)

        avail_w = SLIDE_W - 2 * M

        if variant == "centered_quote":
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.5, y_in=2.0, w_in=avail_w - 1.0, h_in=2.2,
                content={"text": f'\u201c{quote.text}\u201d', "bold": False, "align": "center", "italic": True},
                font_size_pt=22, text_color=tc, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.5, y_in=4.3, w_in=avail_w - 1.0, h_in=0.45,
                content={"text": f"\u2014 {quote.attribution}", "bold": False, "align": "center"},
                font_size_pt=14, text_color=theme.colors.text_muted, z_order=10,
            ))
            shapes.append(_motif_shape(theme, SLIDE_W / 2 - 0.22, 1.4, 0.45))

        elif variant == "side_accent_quote":
            # Left accent block
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=1.5, w_in=0.08, h_in=3.0,
                content={"motif": "quote_accent_bar"},
                fill_color=theme.colors.primary, z_order=2,
            ))
            pt = _fit_font(quote.text, avail_w - 0.3, 2.5, start_pt=20)
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.25, y_in=1.6, w_in=avail_w - 0.3, h_in=2.5,
                content={"text": f'\u201c{quote.text}\u201d', "bold": False, "align": "left", "italic": True},
                font_size_pt=pt, text_color=tc, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=M + 0.25, y_in=4.2, w_in=avail_w - 0.3, h_in=0.4,
                content={"text": f"\u2014 {quote.attribution}", "bold": False, "align": "left"},
                font_size_pt=13, text_color=theme.colors.text_muted, z_order=10,
            ))

        else:
            # quote_with_stat
            sc = slide_data.body.stat_callout
            stat_w = 3.0
            shapes.append(ShapeSpec(
                shape_kind="rounded_rect",
                x_in=M, y_in=1.5, w_in=stat_w, h_in=3.2,
                content={"motif": "stat_card"},
                fill_color=theme.colors.primary, z_order=2,
            ))
            if sc:
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.1, y_in=1.9, w_in=stat_w - 0.2, h_in=1.0,
                    content={"text": sc.number, "bold": True, "align": "center"},
                    font_size_pt=44, text_color=theme.colors.text_on_dark, z_order=10,
                ))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=M + 0.1, y_in=3.0, w_in=stat_w - 0.2, h_in=0.5,
                    content={"text": sc.label, "bold": False, "align": "center"},
                    font_size_pt=13, text_color=theme.colors.text_on_dark, z_order=10,
                ))
            right_x = M + stat_w + 0.4
            right_w = SLIDE_W - right_x - M
            pt = _fit_font(quote.text, right_w, 2.5, start_pt=18)
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=right_x, y_in=1.6, w_in=right_w, h_in=2.5,
                content={"text": f'\u201c{quote.text}\u201d', "bold": False, "align": "left", "italic": True},
                font_size_pt=pt, text_color=tc, z_order=10,
            ))
            shapes.append(ShapeSpec(
                shape_kind="textbox",
                x_in=right_x, y_in=4.2, w_in=right_w, h_in=0.4,
                content={"text": f"\u2014 {quote.attribution}", "bold": False, "align": "left"},
                font_size_pt=13, text_color=theme.colors.text_muted, z_order=10,
            ))

        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE: two_column_text
# ---------------------------------------------------------------------------


class TwoColumnTextLayout:
    def variants(self) -> List[str]:
        return ["equal_columns", "wide_left", "wide_right"]

    def choose_variant(self, slide_data: SlideSpec, density: str, position_in_deck: int) -> str:
        return ["equal_columns", "wide_left", "wide_right"][position_in_deck % 3]

    def compute_geometry(self, slide_data: SlideSpec, theme: Theme, variant: str) -> RenderedSlide:
        on_dark = _is_dark_slide(slide_data.slide_type, theme)
        bg = _bg_color(slide_data.slide_type, theme)
        M = theme.spacing.margin_in
        G = theme.spacing.gutter_in
        tc = _text_color(slide_data.slide_type, theme)
        shapes: List[ShapeSpec] = []
        shapes.extend(_standard_header(slide_data, theme, on_dark))

        start_y = 1.3
        avail_h = SLIDE_H - start_y - M
        avail_w = SLIDE_W - 2 * M
        bullets = slide_data.body.bullets or []
        half = math.ceil(len(bullets) / 2)
        left_bullets = bullets[:half]
        right_bullets = bullets[half:]

        if variant == "wide_left":
            col_ratios = (0.6, 0.4)
        elif variant == "wide_right":
            col_ratios = (0.4, 0.6)
        else:
            col_ratios = (0.5, 0.5)

        col_widths = [(avail_w - G) * r for r in col_ratios]
        col_x = [M, M + col_widths[0] + G]

        for col_i, (cx, cw, col_bulls) in enumerate(zip(col_x, col_widths, [left_bullets, right_bullets])):
            pt, trimmed = _fit_bullets(col_bulls, cw, avail_h)
            for j, b in enumerate(trimmed):
                by = start_y + j * (avail_h / max(len(trimmed), 1))
                shapes.append(ShapeSpec(
                    shape_kind="textbox",
                    x_in=cx, y_in=by, w_in=cw, h_in=avail_h / max(len(trimmed), 1) - 0.05,
                    content={"text": f"• {b}", "bold": False, "align": "left"},
                    font_size_pt=pt, text_color=tc, z_order=10,
                ))

        shapes.append(_motif_shape(theme, M + col_widths[0] + G / 2 - 0.22, start_y, 0.44))
        return RenderedSlide(slide_type=slide_data.slide_type, background_color=bg, shapes=shapes)


# ---------------------------------------------------------------------------
# SLIDE TYPE REGISTRY
# ---------------------------------------------------------------------------

_LAYOUT_REGISTRY: Dict[str, SlideLayout] = {
    "title":               TitleLayout(),
    "agenda":              AgendaLayout(),
    "problem":             ProblemLayout(),
    "solution":            SolutionLayout(),
    "market_sizing":       MarketSizingLayout(),
    "competitive_matrix":  CompetitiveMatrixLayout(),
    "business_model":      BusinessModelLayout(),
    "traction":            TractionLayout(),
    "financials_chart":    FinancialsChartLayout(),
    "team":                TeamLayout(),
    "timeline_roadmap":    TimelineRoadmapLayout(),
    "ask_closing":         AskClosingLayout(),
    "quote_callout":       QuoteCalloutLayout(),
    "two_column_text":     TwoColumnTextLayout(),
    "risk_assessment":     TwoColumnTextLayout(),
}


# ---------------------------------------------------------------------------
# Stage 3 entry point
# ---------------------------------------------------------------------------


def compute_layout(outline: SlideOutline, theme: Theme) -> List[RenderedSlide]:
    """
    Stage 3 entry point.

    Converts a validated SlideOutline + Theme into a list of RenderedSlide
    objects with exact, overflow-safe geometry. No LLM calls.

    Args:
        outline: Validated SlideOutline from Stage 1.
        theme:   Theme object from Stage 2.

    Returns:
        List of RenderedSlide objects ready for Stage 4.
    """
    print(f"[LayoutEngine] Stage 3 — computing geometry for {len(outline.slides)} slides, "
          f"theme: '{theme.theme_id}'")

    # Track variant usage per slide_type so consecutive same-type slides alternate
    type_counters: Dict[str, int] = {}
    rendered: List[RenderedSlide] = []

    for position, slide_data in enumerate(outline.slides):
        st = slide_data.slide_type
        layout = _LAYOUT_REGISTRY.get(st)

        if layout is None:
            # Unknown type — fall back to standard header + bullet list
            print(f"  [LayoutEngine] Unknown slide_type '{st}' at position {position} — using standard header fallback")
            layout = TwoColumnTextLayout()


        count = type_counters.get(st, 0)
        type_counters[st] = count + 1

        # choose_variant uses position_in_deck to allow alternation
        variant = layout.choose_variant(slide_data, slide_data.content_density, count)
        print(f"  [LayoutEngine] Slide {position+1:02d}: {st} → variant '{variant}'")

        rendered_slide = layout.compute_geometry(slide_data, theme, variant)
        rendered.append(rendered_slide)

    return rendered
