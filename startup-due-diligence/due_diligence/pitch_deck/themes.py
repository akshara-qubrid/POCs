"""
Static theme registry for pitch deck generation.

Each Theme is a complete, pre-designed token set. The LLM's only design job
is CLASSIFICATION: read the startup idea's tone and pick one theme_id (or
rank top-3). It never invents colors, fonts, or spacing — that's already
been solved here, by us, once, carefully.

These tokens are consumed directly by the layout engine (layout_engine.py)
to compute shape geometry and by the renderer (render_pptx.py) to set
python-pptx properties. Nothing here is decorative-only; every field is
read by code downstream.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ColorTokens:
    primary: str       # dominant, 60-70% visual weight (backgrounds, title slides)
    secondary: str     # supporting tone (cards, secondary backgrounds)
    accent: str        # sharp, sparing use (key stats, highlights, icons)
    bg_light: str       # light content-slide background
    bg_dark: str        # dark content-slide background (title/closing)
    text_on_light: str   # body text on bg_light
    text_on_dark: str    # body text on bg_dark
    text_muted: str       # captions, sources, footnotes
    card_bg: str          # content block / card fill on light bg


@dataclass(frozen=True)
class FontTokens:
    heading: str           # title/section header font (safe-list)
    body: str              # body text font (safe-list)
    heading_weight: Literal["bold", "regular"] = "bold"
    accent_italic: bool = True   # use italics for callout stats/taglines


@dataclass(frozen=True)
class MotifTokens:
    """The ONE repeated visual element across the deck. No accent stripes/bars."""
    name: str                                    # human-readable description
    shape_style: Literal["circle_icon", "rounded_card", "geometric_accent", "soft_frame"]
    corner_radius_in: float                      # for rounded_card / soft_frame, inches
    icon_container: Literal["circle", "rounded_square", "none"]


@dataclass(frozen=True)
class SpacingTokens:
    margin_in: float = 0.5
    gutter_in: float = 0.4          # between content blocks
    card_padding_in: float = 0.25


@dataclass(frozen=True)
class Theme:
    theme_id: str
    label: str
    tone_keywords: list[str]    # what the LLM matches against
    description: str            # shown to LLM as the classification target
    colors: ColorTokens
    fonts: FontTokens
    motif: MotifTokens
    spacing: SpacingTokens = field(default_factory=SpacingTokens)
    contrast_mode: Literal["sandwich", "dark_throughout"] = "sandwich"
    # sandwich = dark title/closing, light content slides (default, safest)
    # dark_throughout = dark bg on every slide, for premium/bold tones


THEMES: dict[str, Theme] = {

    "midnight_executive": Theme(
        theme_id="midnight_executive",
        label="Midnight Executive",
        tone_keywords=["enterprise", "b2b", "fintech", "infra", "serious", "institutional", "trust", "security"],
        description=(
            "Navy and ice-blue. Serious, institutional, built-for-the-boardroom. "
            "Use for B2B SaaS, fintech, infrastructure, security, anything selling to "
            "enterprise buyers or regulators where 'trustworthy' beats 'exciting'."
        ),
        colors=ColorTokens(
            primary="1E2761", secondary="CADCFC", accent="FFFFFF",
            bg_light="FFFFFF", bg_dark="1E2761",
            text_on_light="1E2761", text_on_dark="FFFFFF",
            text_muted="6E7AA8", card_bg="F4F7FE",
        ),
        fonts=FontTokens(heading="Cambria", body="Calibri"),
        motif=MotifTokens(name="rounded icon containers in ice-blue circles",
                           shape_style="circle_icon", corner_radius_in=0.08,
                           icon_container="circle"),
        contrast_mode="sandwich",
    ),

    "coral_energy": Theme(
        theme_id="coral_energy",
        label="Coral Energy",
        tone_keywords=["consumer", "social", "youth", "vibrant", "fun", "lifestyle", "marketplace", "d2c"],
        description=(
            "Coral and gold on navy accent. High energy, consumer-facing, optimistic. "
            "Use for D2C, social apps, marketplaces, lifestyle/wellness brands, anything "
            "targeting younger or consumer audiences where excitement sells."
        ),
        colors=ColorTokens(
            primary="F96167", secondary="F9E795", accent="2F3C7E",
            bg_light="FFFFFF", bg_dark="2F3C7E",
            text_on_light="2F3C7E", text_on_dark="FFFFFF",
            text_muted="C97B7E", card_bg="FFF4F0",
        ),
        fonts=FontTokens(heading="Century Schoolbook", body="Calibri"),
        motif=MotifTokens(name="rounded card blocks with soft drop shadow",
                           shape_style="rounded_card", corner_radius_in=0.12,
                           icon_container="rounded_square"),
        contrast_mode="sandwich",
    ),

    "forest_moss": Theme(
        theme_id="forest_moss",
        label="Forest & Moss",
        tone_keywords=["sustainability", "climate", "agriculture", "health", "wellness", "natural", "esg"],
        description=(
            "Forest green and moss on cream-free light background. Grounded, sustainable, "
            "credible-but-warm. Use for climate tech, agriculture, healthcare/wellness, "
            "ESG-focused or 'mission-driven' startups."
        ),
        colors=ColorTokens(
            primary="2C5F2D", secondary="97BC62", accent="1B3B1C",
            bg_light="FFFFFF", bg_dark="1B3B1C",
            text_on_light="1B3B1C", text_on_dark="FFFFFF",
            text_muted="6E8C5A", card_bg="F1F6EC",
        ),
        fonts=FontTokens(heading="Bookman Old Style", body="Calibri"),
        motif=MotifTokens(name="circle icon containers with soft frame on images",
                           shape_style="soft_frame", corner_radius_in=0.5,
                           icon_container="circle"),
        contrast_mode="sandwich",
    ),

    "charcoal_minimal": Theme(
        theme_id="charcoal_minimal",
        label="Charcoal Minimal",
        tone_keywords=["technical", "developer", "tools", "ai", "minimalist", "design-led", "premium", "deep-tech"],
        description=(
            "Charcoal and off-white, near-monochrome with black accent. Minimalist, "
            "design-led, technical credibility. Use for dev tools, AI/ML infra, "
            "design-led products, or any team whose taste is itself a selling point."
        ),
        colors=ColorTokens(
            primary="36454F", secondary="F2F2F2", accent="111213",
            bg_light="FFFFFF", bg_dark="212121",
            text_on_light="212121", text_on_dark="F2F2F2",
            text_muted="8C949C", card_bg="F7F7F8",
        ),
        fonts=FontTokens(heading="Calibri", body="Calibri", heading_weight="bold"),
        motif=MotifTokens(name="geometric rounded-square accents, no icons-in-circles",
                           shape_style="geometric_accent", corner_radius_in=0.06,
                           icon_container="rounded_square"),
        contrast_mode="dark_throughout",
    ),

    "berry_cream": Theme(
        theme_id="berry_cream",
        label="Berry & Cream",
        tone_keywords=["creative", "beauty", "fashion", "media", "content", "boutique", "premium-consumer"],
        description=(
            "Berry and dusty rose on warm cream-white. Editorial, premium-consumer, "
            "a little indulgent. Use for beauty, fashion, media/content, boutique "
            "hospitality, or premium consumer brands where taste signals quality."
        ),
        colors=ColorTokens(
            primary="6D2E46", secondary="A26769", accent="ECE2D0",
            bg_light="FFFFFF", bg_dark="6D2E46",
            text_on_light="6D2E46", text_on_dark="FFFFFF",
            text_muted="A26769", card_bg="FBF4F1",
        ),
        fonts=FontTokens(heading="Cambria", body="Calibri", accent_italic=True),
        motif=MotifTokens(name="soft rounded image frames, editorial whitespace",
                           shape_style="soft_frame", corner_radius_in=0.35,
                           icon_container="circle"),
        contrast_mode="sandwich",
    ),

    "teal_trust": Theme(
        theme_id="teal_trust",
        label="Teal Trust",
        tone_keywords=["healthtech", "edtech", "civic", "nonprofit", "approachable", "accessible", "public-sector"],
        description=(
            "Teal and seafoam-mint on white. Approachable but credible, calm rather than "
            "flashy. Use for healthtech, edtech, civic/govtech, nonprofit, or anything "
            "where the buyer needs to feel reassured, not excited."
        ),
        colors=ColorTokens(
            primary="028090", secondary="00A896", accent="02C39A",
            bg_light="FFFFFF", bg_dark="023E40",
            text_on_light="023E40", text_on_dark="FFFFFF",
            text_muted="5C9EA3", card_bg="EFFAF9",
        ),
        fonts=FontTokens(heading="Century Schoolbook", body="Calibri"),
        motif=MotifTokens(name="circle icon containers, rounded data cards",
                           shape_style="circle_icon", corner_radius_in=0.1,
                           icon_container="circle"),
        contrast_mode="sandwich",
    ),
}


def get_theme(theme_id: str) -> Theme:
    if theme_id not in THEMES:
        raise KeyError(f"Unknown theme_id '{theme_id}'. Valid: {list(THEMES.keys())}")
    return THEMES[theme_id]


def themes_for_llm_prompt() -> str:
    """Render the theme catalog as a compact block for the theme-selector LLM call."""
    lines = []
    for t in THEMES.values():
        lines.append(
            f"- {t.theme_id}: {t.description} [keywords: {', '.join(t.tone_keywords)}]"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(themes_for_llm_prompt())
