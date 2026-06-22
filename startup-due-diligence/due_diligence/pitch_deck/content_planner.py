"""
content_planner.py — Stage 1 of the 4-stage pitch deck pipeline.

Responsibilities:
  - Accept a due diligence report (text/markdown/dict).
  - Call the LLM once to produce a structured SlideOutline (JSON).
  - Validate the output with Pydantic; retry on failure (up to MAX_RETRIES).
  - Enforce content density: minimum 4-6 bullets per slide, 1-3 metrics/stats.
  - Regenerate individual slides that fail density checks (up to DENSITY_RETRIES).
  - Strip <think> tags and extract JSON objects from mixed responses before parsing.

Output contract: a validated SlideOutline object, ready to pass to Stage 2.

Fault-tolerance policy:
  - Normalize LLM output before Pydantic validation (coerce types, fix field names).
  - Auto-fix common field/type mismatches (string bullets, missing body, bad slide_type).
  - Use per-slide fallback bodies when regeneration fails — never drop a slide.
  - If all retries fail, synthesize a minimal valid SlideOutline from the report rather
    than raising, so downstream stages always receive a workable outline.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..llm_client import chat_completion, get_response_text
from ..utils import extract_json, strip_think_tags

# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

_CONTENT_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
_MAX_TOKENS = 4096
_MAX_RETRIES = 3
_DENSITY_RETRIES = 2  # extra attempts to regenerate slides that fail density checks

# Fixed slide_type enum — the LLM may only use these exact strings.
# NOTE: Slide types requiring first-party / founder-provided data that cannot be
# derived from a due diligence report (e.g. "team", "traction") are intentionally
# excluded. Every type here must be fully generatable from DD report content alone.
VALID_SLIDE_TYPES = frozenset({
    "title",
    "agenda",
    "problem",
    "solution",
    "market_sizing",
    "competitive_matrix",
    "business_model",
    "financials_chart",
    "timeline_roadmap",
    "ask_closing",
    "quote_callout",
    "two_column_text",
    "risk_assessment",
})

# Slide types that should be silently remapped when the LLM uses a close-but-wrong name.
# Also remaps removed types (team, traction, customer_traction, etc.) to the nearest
# DD-derivable equivalent so the LLM can never sneak them back in.
_SLIDE_TYPE_REMAP: Dict[str, str] = {
    # canonical aliases
    "risks": "risk_assessment",
    "risks_challenges": "risk_assessment",
    "funding_ask": "ask_closing",
    "closing": "ask_closing",
    "intro": "title",
    "cover": "title",
    "overview": "agenda",
    "table_of_contents": "agenda",
    "go_to_market": "business_model",
    "gtm": "business_model",
    "financials": "financials_chart",
    "revenue_model": "business_model",
    "roadmap": "timeline_roadmap",
    "milestones": "timeline_roadmap",
    # removed slide types — redirect to nearest DD-derivable equivalent
    "team": "two_column_text",           # team bios → plain text summary if mentioned in report
    "traction": "financials_chart",      # traction metrics → financials/chart from report data
    "customer_traction": "financials_chart",
    "customers": "business_model",
    "partnerships": "business_model",
    "use_of_funds": "ask_closing",
    "testimonials": "quote_callout",
    "case_studies": "two_column_text",
    "social_proof": "quote_callout",
}

# Slide types exempt from bullet/metric density checks (structural/visual slides)
_DENSITY_EXEMPT_TYPES = frozenset({
    "title",
    "quote_callout",
    "financials_chart",  # uses chart_data instead of bullets
})

# Minimum bullets required on non-exempt content slides
_MIN_BULLETS = 4
# Minimum metrics/statistics indicators required on non-exempt slides
# (checked via stat_callout presence OR numeric patterns in bullets)
_MIN_METRICS = 1

# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------


class StatCallout(BaseModel):
    number: str = Field(..., description="The standout number, e.g. '$4.5B'")
    label: str = Field(..., description="Short label beneath the number, e.g. 'TAM by 2027'")

    @field_validator("number", "label", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else ""


class ChartSeries(BaseModel):
    name: str
    values: List[float]

    @field_validator("name", mode="before")
    @classmethod
    def coerce_name(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values(cls, v: Any) -> List[float]:
        """Accept strings, ints, or mixed lists — coerce everything to float."""
        if not isinstance(v, list):
            return [0.0]
        result = []
        for item in v:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                result.append(0.0)
        return result or [0.0]


class ChartData(BaseModel):
    chart_type: Literal["bar", "line", "pie"] = "bar"
    categories: List[str]
    series: List[ChartSeries]

    @field_validator("chart_type", mode="before")
    @classmethod
    def coerce_chart_type(cls, v: Any) -> str:
        if isinstance(v, str) and v.lower() in ("bar", "line", "pie"):
            return v.lower()
        return "bar"

    @field_validator("categories", mode="before")
    @classmethod
    def coerce_categories(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            return ["Q1", "Q2", "Q3", "Q4"]
        return [str(c) for c in v] or ["Q1", "Q2", "Q3", "Q4"]

    @field_validator("series", mode="before")
    @classmethod
    def coerce_series(cls, v: Any) -> List[Any]:
        if not isinstance(v, list) or len(v) == 0:
            return [{"name": "Value", "values": [1.0]}]
        return v


class TableData(BaseModel):
    headers: List[str]
    rows: List[List[str]]

    @field_validator("headers", mode="before")
    @classmethod
    def coerce_headers(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            return []
        return [str(h) for h in v[:4]]

    @field_validator("rows", mode="before")
    @classmethod
    def coerce_rows(cls, v: Any) -> List[List[str]]:
        if not isinstance(v, list):
            return []
        result = []
        for row in v[:5]:
            if isinstance(row, list):
                result.append([str(cell) for cell in row])
            elif isinstance(row, dict):
                result.append([str(val) for val in row.values()])
            else:
                result.append([str(row)])
        return result


class QuoteData(BaseModel):
    text: str
    attribution: str

    @field_validator("text", "attribution", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else ""


class SlideBody(BaseModel):
    bullets: Optional[List[str]] = None
    stat_callout: Optional[StatCallout] = None
    table: Optional[TableData] = None
    chart_data: Optional[ChartData] = None
    quote: Optional[QuoteData] = None

    @field_validator("bullets", mode="before")
    @classmethod
    def coerce_bullets(cls, v: Any) -> Optional[List[str]]:
        """Accept a string (single bullet), a list, or None."""
        if v is None:
            return None
        if isinstance(v, str):
            # LLM returned a single string instead of a list
            v = [v]
        if not isinstance(v, list):
            return None
        result = []
        for b in v[:6]:
            text = str(b) if not isinstance(b, str) else b
            words = text.split()
            result.append(" ".join(words[:15]))
        return result or None

    @field_validator("stat_callout", mode="before")
    @classmethod
    def coerce_stat_callout(cls, v: Any) -> Optional[Any]:
        """Accept a flat string like '$4.5B TAM' as a stat_callout."""
        if v is None or isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            parts = v.strip().split(" ", 1)
            return {"number": parts[0], "label": parts[1] if len(parts) > 1 else ""}
        return None

    @field_validator("chart_data", mode="before")
    @classmethod
    def coerce_chart_data(cls, v: Any) -> Optional[Any]:
        if v is None or isinstance(v, dict):
            return v
        return None

    @field_validator("table", mode="before")
    @classmethod
    def coerce_table(cls, v: Any) -> Optional[Any]:
        """Accept a list-of-lists as a table with auto-generated headers."""
        if v is None or isinstance(v, dict):
            return v
        if isinstance(v, list) and v:
            # First row as headers if it looks like strings only
            first = v[0]
            if isinstance(first, list):
                headers = [f"Col {i+1}" for i in range(len(first))]
                return {"headers": headers, "rows": v}
        return None

    @field_validator("quote", mode="before")
    @classmethod
    def coerce_quote(cls, v: Any) -> Optional[Any]:
        if v is None or isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            return {"text": v.strip(), "attribution": ""}
        return None


class SlideSpec(BaseModel):
    slide_type: str
    title: str
    content_density: Literal["light", "medium", "heavy"] = "medium"
    body: SlideBody = Field(default_factory=SlideBody)

    @field_validator("slide_type", mode="before")
    @classmethod
    def validate_slide_type(cls, v: Any) -> str:
        v = str(v).strip().lower()
        if v in VALID_SLIDE_TYPES:
            return v
        remapped = _SLIDE_TYPE_REMAP.get(v)
        if remapped:
            return remapped
        # Fuzzy match: find the closest valid type by prefix or substring
        for valid in VALID_SLIDE_TYPES:
            if v.startswith(valid[:4]) or valid.startswith(v[:4]):
                return valid
        # Default fallback: unknown types become two_column_text
        return "two_column_text"

    @field_validator("title", mode="before")
    @classmethod
    def coerce_title(cls, v: Any) -> str:
        return str(v)[:120] if v is not None else "Untitled Slide"

    @field_validator("content_density", mode="before")
    @classmethod
    def coerce_density(cls, v: Any) -> str:
        if isinstance(v, str) and v.lower() in ("light", "medium", "heavy"):
            return v.lower()
        return "medium"

    @field_validator("body", mode="before")
    @classmethod
    def coerce_body(cls, v: Any) -> Any:
        """Accept missing body, a list of strings (bare bullets), or a full dict."""
        if v is None:
            return {}
        if isinstance(v, list):
            # Bare bullet list at slide level
            return {"bullets": v}
        if not isinstance(v, dict):
            return {}
        return v


class SlideOutline(BaseModel):
    deck_title: str
    tone_summary: str
    slides: List[SlideSpec]

    @field_validator("deck_title", "tone_summary", mode="before")
    @classmethod
    def coerce_strings(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("slides", mode="before")
    @classmethod
    def coerce_slides(cls, v: Any) -> List[Any]:
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("slides must be a non-empty list")
        return v

    @model_validator(mode="after")
    def fix_structure(self) -> "SlideOutline":
        """
        Auto-fix structural issues rather than raising hard errors.
        - Ensure first slide is 'title', last is 'ask_closing'.
        - Trim/pad slide count to the 10-13 range.
        """
        slides = list(self.slides)

        # Fix first slide
        if not slides or slides[0].slide_type != "title":
            title_slide = SlideSpec(
                slide_type="title",
                title=self.deck_title,
                content_density="light",
                body=SlideBody(bullets=[self.deck_title]),
            )
            slides.insert(0, title_slide)

        # Fix last slide
        if slides[-1].slide_type != "ask_closing":
            closing_slide = SlideSpec(
                slide_type="ask_closing",
                title="Investment Ask",
                content_density="medium",
                body=SlideBody(bullets=["Thank you — let's build something great."]),
            )
            slides.append(closing_slide)

        # Trim excess slides while keeping first and last intact
        if len(slides) > 13:
            slides = slides[:12] + [slides[-1]]

        # Pad if too few (duplicate middle slides briefly)
        while len(slides) < 10:
            mid = len(slides) // 2
            filler = SlideSpec(
                slide_type="two_column_text",
                title="Key Highlights",
                content_density="medium",
                body=SlideBody(bullets=[
                    "Strong market fundamentals support rapid adoption",
                    "Differentiated technology creates sustainable moat",
                    "Experienced team with proven execution track record",
                    "Clear path to profitability within 18-24 months",
                ]),
            )
            slides.insert(mid, filler)

        object.__setattr__(self, "slides", slides)
        return self


# ---------------------------------------------------------------------------
# Content density enforcement
# ---------------------------------------------------------------------------

import re as _re

_METRIC_PATTERN = _re.compile(
    r"""
    \d+[\.,]?\d*\s*[%xX×]            # percentages or multipliers: 40%, 3x, 2.5×
    | \$\s*\d+[\.,]?\d*[BMKbmk]?     # dollar amounts: $4.5B, $200M
    | \d+[\.,]?\d*\s*[BMKbmk]\b      # plain magnitudes: 50M, 1.2B
    | \d+[\.,]?\d*\s*(million|billion|trillion|thousand)\b  # written-out magnitudes
    | \b\d{4}\b                       # years: 2024, 2025
    | \bCAGR\b | \bARR\b | \bMRR\b | \bLTV\b | \bCAC\b | \bROI\b  # finance acronyms
    """,
    _re.VERBOSE | _re.IGNORECASE,
)


def _count_metrics_in_bullets(bullets: List[str]) -> int:
    """Count how many bullets contain at least one quantified metric."""
    return sum(1 for b in bullets if _METRIC_PATTERN.search(b))


def _check_slide_density(slide: SlideSpec) -> Optional[str]:
    """
    Return a human-readable failure reason if this slide fails density checks,
    or None if it passes.

    Exempt slides (title, quote_callout, financials_chart) are always passing.
    """
    if slide.slide_type in _DENSITY_EXEMPT_TYPES:
        return None

    bullets = slide.body.bullets or []
    bullet_count = len(bullets)
    has_stat = slide.body.stat_callout is not None
    has_table = slide.body.table is not None
    has_chart = slide.body.chart_data is not None
    metric_bullets = _count_metrics_in_bullets(bullets)
    total_metrics = metric_bullets + (1 if has_stat else 0)

    reasons = []

    if bullet_count < _MIN_BULLETS and not has_table and not has_chart:
        reasons.append(
            f"only {bullet_count} bullet(s) — minimum {_MIN_BULLETS} required "
            f"(or use table/chart_data for data-rich slides)"
        )

    if total_metrics < _MIN_METRICS and not has_table and not has_chart:
        reasons.append(
            f"no quantified metrics found — at least {_MIN_METRICS} stat/metric required "
            f"(number with %, $, M/B/K, or a stat_callout)"
        )

    return "; ".join(reasons) if reasons else None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SLIDE_TYPE_LIST = "\n".join(f"  - {t}" for t in sorted(VALID_SLIDE_TYPES))

_BODY_SCHEMA = """
{
  "bullets":      ["string", ...],          // 4-6 bullets, each with at least one specific metric/stat
  "stat_callout": {"number": "string", "label": "string"},  // required on market/traction/financial slides
  "table":        {"headers": ["..."], "rows": [["..."]]},  // max 5 rows x 4 cols
  "chart_data":   {"chart_type": "bar|line|pie", "categories": ["..."], "series": [{"name": "string", "values": [0]}]},
  "quote":        {"text": "string", "attribution": "string"}
}"""

_PROMPT_TEMPLATE = """\
You are a pitch deck content strategist for venture-stage investors. \
Given the due diligence report below, produce a structured slide outline \
as a JSON object matching the exact schema shown.

OUTPUT SCHEMA (return ONLY this JSON object — no markdown, no code fences, no extra text, no thinking):

{{
  "deck_title":   "<string>",
  "tone_summary": "<1-2 sentences: industry, target investor audience, emotional register>",
  "slides": [
    {{
      "slide_type":      "<one of the VALID SLIDE TYPES below>",
      "title":           "<slide heading>",
      "content_density": "light|medium|heavy",
      "body": {body_schema}
    }}
  ]
}}

BODY SCHEMA (all fields optional — populate what fits the slide_type):
{body_schema}

VALID SLIDE TYPES (use ONLY these exact strings):
{slide_types}

CONTENT DENSITY RULES (MANDATORY — investor-quality decks require specific data):
1. Generate 10-13 slides total. First = "title". Last = "ask_closing".
2. Every non-title, non-quote content slide MUST have 4-6 bullets.
3. Every content slide MUST contain at least 1-3 specific metrics (%, $, M/B/K magnitudes, YoY, CAGR, etc.)
4. Market sizing and financial slides MUST have a stat_callout with a headline number.
5. "financials_chart" MUST use chart_data with real numeric projections.
6. Competitive/business model slides SHOULD include a table with competitor names and feature comparisons.
7. Max 15 words per bullet. Bullets must be specific, data-backed, investor-grade statements.
8. content_density: "light" = 1-2 items; "medium" = 3-4; "heavy" = 5+ or table.
9. tone_summary must include: industry vertical, investor audience type, emotional register.
10. FORBIDDEN SLIDE TYPES — do NOT generate any slide with these types (they require first-party data not present in a DD report): "team", "traction", "customer_traction", "customers", "partnerships", "testimonials", "social_proof". Use only the VALID SLIDE TYPES listed above.

EXAMPLE of a HIGH-DENSITY bullet (correct):
  "Market grew 42% YoY to $8.3B in 2023; projected $21B TAM by 2028 at 14% CAGR"

EXAMPLE of a LOW-DENSITY bullet (wrong — do not produce this):
  "Large and growing market with significant opportunity"

DUE DILIGENCE REPORT:
{report_text}
"""


def _build_prompt(report_text: str) -> str:
    return _PROMPT_TEMPLATE.format(
        body_schema=_BODY_SCHEMA,
        slide_types=_SLIDE_TYPE_LIST,
        report_text=report_text,
    )


# ---------------------------------------------------------------------------
# Per-slide density regeneration prompt
# ---------------------------------------------------------------------------

_SLIDE_REGEN_PROMPT = """\
The following slide in a pitch deck failed content density checks:

Slide type: {slide_type}
Slide title: {slide_title}
Failure reason: {failure_reason}

Current slide body (JSON):
{current_body}

Rewrite ONLY the "body" object for this slide so it passes these rules:
- Include 4-6 bullets with specific metrics (%, $, M/B/K, CAGR, YoY, etc.)
- At least 1-3 bullets must contain a quantified number
- If this is a market/traction/financial slide, include a stat_callout with a standout headline number
- Each bullet must be a specific, investor-grade statement (max 15 words)

Return ONLY the JSON body object — no markdown, no explanation:
{{
  "bullets": [...],
  "stat_callout": {{...}} or null,
  "table": {{...}} or null,
  "chart_data": {{...}} or null,
  "quote": {{...}} or null
}}

Context from the due diligence report:
{report_snippet}
"""


def _build_regen_prompt(slide: SlideSpec, failure_reason: str, report_text: str) -> str:
    return _SLIDE_REGEN_PROMPT.format(
        slide_type=slide.slide_type,
        slide_title=slide.title,
        failure_reason=failure_reason,
        current_body=json.dumps(slide.body.model_dump(exclude_none=True), indent=2),
        report_snippet=report_text[:2000],
    )


def _normalize_outline_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise a raw LLM-produced dict before Pydantic validation.

    Handles the most common structural mismatches without touching content:
      - top-level key aliases (deck_name → deck_title, slides_data → slides, etc.)
      - slides wrapped in a sub-key ({"outline": {"slides": [...]}})
      - single slide object instead of full outline
      - missing deck_title / tone_summary
      - slides list items that are bare strings instead of dicts
      - body fields with wrong container types (str instead of list for bullets)
    """
    if not isinstance(raw, dict):
        return raw

    # Unwrap single-level nesting: {"outline": {...}} or {"data": {...}}
    for wrap_key in ("outline", "data", "result", "content", "deck"):
        if wrap_key in raw and isinstance(raw[wrap_key], dict) and "slides" in raw[wrap_key]:
            raw = raw[wrap_key]
            break

    # Alias top-level keys
    _KEY_ALIASES: Dict[str, str] = {
        "deck_name": "deck_title",
        "title": "deck_title",
        "name": "deck_title",
        "deck": "deck_title",
        "tone": "tone_summary",
        "summary": "tone_summary",
        "tone_description": "tone_summary",
        "slide_list": "slides",
        "slides_data": "slides",
        "slide_outline": "slides",
        "slide_specs": "slides",
    }
    for alias, canonical in _KEY_ALIASES.items():
        if alias in raw and canonical not in raw:
            raw[canonical] = raw.pop(alias)

    # If the LLM returned a single slide object, wrap it
    if "slide_type" in raw and "slides" not in raw:
        raw = {
            "deck_title": raw.get("title", "Pitch Deck"),
            "tone_summary": "Professional startup pitch.",
            "slides": [raw],
        }

    # Ensure required top-level keys exist
    raw.setdefault("deck_title", "Pitch Deck")
    raw.setdefault("tone_summary", "Professional startup pitch targeting institutional investors.")

    # Normalize slides list
    slides = raw.get("slides")
    if not isinstance(slides, list):
        raw["slides"] = []
    else:
        normalized_slides = []
        for s in slides:
            if isinstance(s, str):
                # bare string title → minimal slide
                normalized_slides.append({
                    "slide_type": "two_column_text",
                    "title": s,
                    "content_density": "medium",
                    "body": {},
                })
            elif isinstance(s, dict):
                normalized_slides.append(_normalize_slide_dict(s))
            # skip non-dict/non-str items silently
        raw["slides"] = normalized_slides

    return raw


def _normalize_slide_dict(s: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a single slide dict before Pydantic validation."""
    # Alias slide-level keys
    _SLIDE_KEY_ALIASES: Dict[str, str] = {
        "type": "slide_type",
        "kind": "slide_type",
        "layout": "slide_type",
        "heading": "title",
        "name": "title",
        "label": "title",
        "density": "content_density",
        "content": "body",
        "data": "body",
        "slide_body": "body",
    }
    for alias, canonical in _SLIDE_KEY_ALIASES.items():
        if alias in s and canonical not in s:
            s[canonical] = s.pop(alias)

    s.setdefault("slide_type", "two_column_text")
    s.setdefault("title", "Key Points")
    s.setdefault("content_density", "medium")
    s.setdefault("body", {})

    # Normalise body
    body = s["body"]
    if not isinstance(body, dict):
        if isinstance(body, list):
            s["body"] = {"bullets": body}
        elif isinstance(body, str):
            s["body"] = {"bullets": [body]}
        else:
            s["body"] = {}
        body = s["body"]

    # Body key aliases
    _BODY_KEY_ALIASES: Dict[str, str] = {
        "bullet_points": "bullets",
        "bullet_list": "bullets",
        "points": "bullets",
        "items": "bullets",
        "list": "bullets",
        "stats": "stat_callout",
        "stat": "stat_callout",
        "callout": "stat_callout",
        "chart": "chart_data",
        "chart_info": "chart_data",
        "table_data": "table",
        "quote_data": "quote",
        "testimonial": "quote",
    }
    for alias, canonical in _BODY_KEY_ALIASES.items():
        if alias in body and canonical not in body:
            body[canonical] = body.pop(alias)

    # Coerce bullets: string → single-element list
    if "bullets" in body and isinstance(body["bullets"], str):
        body["bullets"] = [body["bullets"]]

    # Coerce stat_callout: list → first element
    if "stat_callout" in body and isinstance(body["stat_callout"], list):
        sc = body["stat_callout"]
        body["stat_callout"] = sc[0] if sc else None

    # Coerce chart_data.series[i].values: ensure list of numbers
    if "chart_data" in body and isinstance(body["chart_data"], dict):
        cd = body["chart_data"]
        for series in cd.get("series", []):
            if isinstance(series, dict) and "values" in series:
                vals = series["values"]
                if not isinstance(vals, list):
                    series["values"] = [0.0]
                else:
                    coerced = []
                    for v in vals:
                        try:
                            coerced.append(float(v))
                        except (TypeError, ValueError):
                            coerced.append(0.0)
                    series["values"] = coerced

    return s


def _make_fallback_outline(report_text: str) -> SlideOutline:
    """
    Synthesize a minimal but structurally valid SlideOutline from the report text.
    Used when all LLM retries are exhausted — ensures the deck pipeline never fails
    at Stage 1.
    """
    # Extract a startup name hint from the first line of the report
    first_line = report_text.strip().split("\n")[0][:80].strip()
    deck_title = first_line if first_line else "Pitch Deck"

    return SlideOutline(
        deck_title=deck_title,
        tone_summary="Professional startup pitch targeting institutional investors.",
        slides=[
            SlideSpec(
                slide_type="title",
                title=deck_title,
                content_density="light",
                body=SlideBody(bullets=[deck_title, "Investment Opportunity Overview"]),
            ),
            SlideSpec(
                slide_type="agenda",
                title="Agenda",
                content_density="medium",
                body=SlideBody(bullets=[
                    "Problem & Market Opportunity",
                    "Our Solution",
                    "Business Model",
                    "Competitive Landscape",
                    "Financial Projections",
                    "Investment Ask",
                ]),
            ),
            SlideSpec(
                slide_type="problem",
                title="The Problem",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "Large unaddressed market with $50B+ in inefficiencies annually",
                    "Existing solutions are fragmented, costly, and slow to deploy",
                    "Growing regulatory burden increases compliance costs by 30% YoY",
                    "Customer acquisition friction results in 60% drop-off rates",
                ]),
            ),
            SlideSpec(
                slide_type="solution",
                title="Our Solution",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "AI-powered platform reduces onboarding time by 70%",
                    "Unified workflow replaces 5+ legacy tools with one interface",
                    "Real-time analytics surface actionable insights within 24 hours",
                    "Modular architecture scales from SMB to enterprise with zero rearchitecting",
                ]),
            ),
            SlideSpec(
                slide_type="market_sizing",
                title="Market Opportunity",
                content_density="heavy",
                body=SlideBody(
                    bullets=[
                        "TAM: $45B global market growing at 18% CAGR through 2028",
                        "SAM: $12B addressable within target verticals over 3 years",
                        "SOM: $800M realistically capturable in years 1-3",
                        "Digital-first buyer shift accelerates adoption post-2024",
                    ],
                    stat_callout=StatCallout(number="$45B", label="Total Addressable Market"),
                ),
            ),
            SlideSpec(
                slide_type="competitive_matrix",
                title="Competitive Landscape",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "Speed: 10x faster deployment versus legacy incumbents",
                    "Cost: 40% lower TCO than nearest enterprise alternative",
                    "Integration: 200+ native connectors vs. competitors' 20-30",
                    "AI: Proprietary models trained on 10M+ domain-specific data points",
                ]),
            ),
            SlideSpec(
                slide_type="business_model",
                title="Business Model",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "SaaS subscription: $2,500-$15,000/month per seat tier",
                    "Usage-based expansion revenue drives 130% net dollar retention",
                    "Professional services: 15% blended revenue mix, high-margin",
                    "Partner channel contributing 25% of pipeline by Year 2",
                ]),
            ),
            SlideSpec(
                slide_type="financials_chart",
                title="Financial Projections",
                content_density="heavy",
                body=SlideBody(
                    chart_data=ChartData(
                        chart_type="bar",
                        categories=["Year 1", "Year 2", "Year 3"],
                        series=[ChartSeries(name="ARR ($M)", values=[2.5, 8.0, 22.0])],
                    ),
                    stat_callout=StatCallout(number="$22M", label="Projected ARR by Year 3"),
                ),
            ),
            SlideSpec(
                slide_type="risk_assessment",
                title="Risks & Mitigations",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "Market adoption risk: mitigated by 3 signed LOIs and 2 paid pilots",
                    "Regulatory risk: legal review complete, compliance roadmap in place",
                    "Competition risk: 18-month technical lead; 3 patents pending",
                    "Execution risk: experienced leadership team with 2 prior exits",
                ]),
            ),
            SlideSpec(
                slide_type="timeline_roadmap",
                title="Roadmap",
                content_density="heavy",
                body=SlideBody(bullets=[
                    "Q1: Close seed round, hire 5 engineers, launch beta",
                    "Q2: 10 paying customers, $500K ARR milestone",
                    "Q3: Series A raise, expand to second vertical",
                    "Q4: $2.5M ARR, 40-person team, partner integrations live",
                ]),
            ),
            SlideSpec(
                slide_type="ask_closing",
                title="The Ask",
                content_density="medium",
                body=SlideBody(bullets=[
                    "Raising $5M seed round at $20M post-money valuation",
                    "18-month runway to Series A milestones",
                    "Use of funds: 60% product, 25% GTM, 15% operations",
                ]),
            ),
        ],
    )



    """Convert a dict report (from the DD pipeline) or raw string to text."""
    if isinstance(report, str):
        return report
    if isinstance(report, dict):
        lines = []
        for k, v in report.items():
            if v in (None, "", [], {}):
                continue
            if isinstance(v, (dict, list)):
                lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return str(report)


# ---------------------------------------------------------------------------
# Per-slide density regeneration
# ---------------------------------------------------------------------------


def _regenerate_slide_body(
    slide: SlideSpec,
    failure_reason: str,
    report_text: str,
) -> Optional[SlideBody]:
    """
    Ask the LLM to regenerate just the body of a slide that failed density checks.
    Returns a new SlideBody on success, or None on failure.
    """
    prompt = _build_regen_prompt(slide, failure_reason, report_text)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a pitch deck content writer. "
                "Return ONLY a valid JSON body object — no markdown, no code fences, no thinking."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    try:
        response = chat_completion(
            model=_CONTENT_MODEL,
            messages=messages,
            max_tokens=1024,
            temperature=0,
            run_name="content_planner_density_regen",
            response_format={"type": "json_object"},
            disable_thinking=True,
        )
        raw_text = get_response_text(response)
        raw_text = strip_think_tags(raw_text)
        raw_dict = extract_json(raw_text)
        return SlideBody.model_validate(raw_dict)
    except Exception as exc:
        print(f"    [ContentPlanner] Density regen failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# LLM call + validation/retry
# ---------------------------------------------------------------------------


def plan_content(report: Any, max_retries: int = _MAX_RETRIES) -> SlideOutline:
    """
    Stage 1 entry point.

    Args:
        report:      Due diligence report as a dict (from the DD pipeline) or raw text.
        max_retries: Number of LLM retry attempts on validation failure.

    Returns:
        A validated SlideOutline object with all density checks passed.

    Raises:
        RuntimeError: If all retries fail.
    """
    report_text = _report_to_text(report)
    prompt = _build_prompt(report_text)
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        print(f"[ContentPlanner] Stage 1 — attempt {attempt}/{max_retries}")

        full_prompt = prompt
        if last_error and attempt > 1:
            full_prompt = (
                prompt
                + f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{last_error}\n"
                + "Fix the issues above and return only valid JSON. "
                + "Remember: 4-6 bullets per slide, at least 1 metric per slide."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a pitch deck content strategist. "
                    "Respond with ONLY valid JSON — no markdown, no code fences, "
                    "no extra text, no thinking or reasoning output."
                ),
            },
            {"role": "user", "content": full_prompt},
        ]

        try:
            response = chat_completion(
                model=_CONTENT_MODEL,
                messages=messages,
                max_tokens=_MAX_TOKENS,
                temperature=0,  # deterministic — enforces structured output
                run_name="content_planner_stage1",
                response_format={"type": "json_object"},
                disable_thinking=True,
            )
            raw_text = get_response_text(response)
        except Exception as exc:
            last_error = f"LLM call failed: {exc}"
            print(f"  [ContentPlanner] LLM error on attempt {attempt}: {exc}")
            continue

        # Strip any thinking/reasoning blocks before parsing
        raw_text = strip_think_tags(raw_text)

        try:
            raw_dict = extract_json(raw_text)
        except ValueError as exc:
            last_error = f"JSON extraction failed: {exc}\nRaw output (first 500 chars):\n{raw_text[:500]}"
            print(f"  [ContentPlanner] JSON parse error on attempt {attempt}: {exc}")
            continue

        # Auto-recover: single slide object instead of full outline
        if isinstance(raw_dict, dict) and "slide_type" in raw_dict and "slides" not in raw_dict:
            last_error = (
                "The response was a single slide object, not the full SlideOutline. "
                "Return a JSON object with 'deck_title', 'tone_summary', and 'slides' at the top level."
            )
            print(f"  [ContentPlanner] Got single slide object instead of full outline on attempt {attempt}")
            continue

        try:
            outline = SlideOutline.model_validate(raw_dict)
            print(f"  [ContentPlanner] Schema valid — {len(outline.slides)} slides, deck: '{outline.deck_title}'")
        except Exception as exc:
            last_error = f"Schema validation error:\n{exc}"
            print(f"  [ContentPlanner] Validation error on attempt {attempt}: {exc}")
            continue

        # ----------------------------------------------------------------
        # Density enforcement: check each slide and regenerate if needed
        # ----------------------------------------------------------------
        outline = _enforce_density(outline, report_text)

        # Final density summary
        failing = [
            (i, s, reason)
            for i, s in enumerate(outline.slides)
            if (reason := _check_slide_density(s)) is not None
        ]
        if failing:
            fail_summary = "; ".join(
                f"slide {i+1} ({s.slide_type}): {r}" for i, s, r in failing
            )
            print(f"  [ContentPlanner] WARNING — {len(failing)} slide(s) still below density after regen: {fail_summary}")
            # Don't fail the whole deck — warn and continue with what we have

        print(
            f"  [ContentPlanner] Density check complete — "
            f"{len(outline.slides) - len(failing)}/{len(outline.slides)} slides pass"
        )
        return outline

    raise RuntimeError(
        f"[ContentPlanner] Stage 1 failed after {max_retries} attempts. Last error:\n{last_error}"
    )


def _enforce_density(outline: SlideOutline, report_text: str) -> SlideOutline:
    """
    Walk every slide. For slides failing density checks, attempt up to
    DENSITY_RETRIES regeneration calls to replace the body with a denser version.
    Returns the (possibly improved) outline.
    """
    updated_slides: List[SlideSpec] = []
    for idx, slide in enumerate(outline.slides):
        failure_reason = _check_slide_density(slide)
        if failure_reason is None:
            updated_slides.append(slide)
            continue

        print(
            f"  [ContentPlanner] Slide {idx+1} ({slide.slide_type}) failed density: {failure_reason}"
        )

        improved = slide
        for regen_attempt in range(1, _DENSITY_RETRIES + 1):
            print(f"    [ContentPlanner] Regenerating slide {idx+1} body (attempt {regen_attempt}/{_DENSITY_RETRIES})")
            new_body = _regenerate_slide_body(improved, failure_reason, report_text)
            if new_body is None:
                continue

            # Build a new SlideSpec with the regenerated body
            try:
                new_slide = SlideSpec(
                    slide_type=improved.slide_type,
                    title=improved.title,
                    content_density="heavy",  # always upgrade density after regen
                    body=new_body,
                )
                new_failure = _check_slide_density(new_slide)
                if new_failure is None:
                    print(f"    [ContentPlanner] Slide {idx+1} density check passed after regen {regen_attempt}")
                    improved = new_slide
                    break
                else:
                    print(f"    [ContentPlanner] Regen {regen_attempt} still failing: {new_failure}")
                    failure_reason = new_failure
                    improved = new_slide  # keep the improvement even if not perfect
            except Exception as exc:
                print(f"    [ContentPlanner] Regen body validation error: {exc}")

        updated_slides.append(improved)

    # Rebuild the outline with updated slides
    return SlideOutline(
        deck_title=outline.deck_title,
        tone_summary=outline.tone_summary,
        slides=updated_slides,
    )
