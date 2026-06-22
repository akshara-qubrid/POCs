"""
theme_selector.py — Stage 2 of the 4-stage pitch deck pipeline.

Responsibilities:
  - Accept the tone_summary from Stage 1 (and optionally deck_title).
  - Call the LLM exactly once with the full theme catalog.
  - Parse and validate the returned theme_id against the THEMES registry.
  - Fall back to "midnight_executive" on any failure — never let an invalid
    theme_id reach the Layout Engine.

This is a pure classification call: the LLM picks ONE theme from a fixed list.
It does not invent colors, fonts, or any design values.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..llm_client import chat_completion, get_response_text
from ..utils import strip_think_tags
from .themes import THEMES, Theme, get_theme, themes_for_llm_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

_THEME_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
_MAX_TOKENS = 64       # We only need a single theme_id string back
_TEMPERATURE = 0.1     # Near-deterministic — this is classification, not generation

_DEFAULT_THEME_ID = "midnight_executive"  # safest general-purpose fallback

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are selecting a visual theme for a pitch deck.

Based on the tone summary below, pick EXACTLY ONE theme_id from the list provided \
that best fits the startup's industry, audience, and emotional register.

Tone summary: {tone_summary}

Deck title (hint): {deck_title}

Available themes:
{theme_catalog}

Respond with ONLY the theme_id string — no explanation, no punctuation, nothing else.
Valid theme_ids: {valid_ids}
"""


def _build_prompt(tone_summary: str, deck_title: str) -> str:
    return _PROMPT_TEMPLATE.format(
        tone_summary=tone_summary,
        deck_title=deck_title,
        theme_catalog=themes_for_llm_prompt(),
        valid_ids=", ".join(THEMES.keys()),
    )


def _clean_response(raw: str) -> str:
    """Strip whitespace, quotes, punctuation, and markdown from the LLM response."""
    cleaned = raw.strip().strip('"').strip("'").strip("`").strip().rstrip(".")
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[-1].strip()
    cleaned = cleaned.split()[0] if cleaned.split() else cleaned
    return cleaned.lower()


# ---------------------------------------------------------------------------
# Stage 2 entry point
# ---------------------------------------------------------------------------


def select_theme(tone_summary: str, deck_title: str = "") -> Theme:
    """
    Stage 2 entry point.

    Args:
        tone_summary: 1-2 sentence description produced by Stage 1.
        deck_title:   Optional deck title for additional context.

    Returns:
        A Theme object from the static THEMES registry.
        Falls back to "midnight_executive" on any failure.
    """
    print(f"[ThemeSelector] Stage 2 — classifying tone: '{tone_summary[:80]}...'")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a theme classifier. "
                "Respond with ONLY a single theme_id string from the provided list. "
                "No explanation. No punctuation. No markdown."
            ),
        },
        {"role": "user", "content": _build_prompt(tone_summary, deck_title)},
    ]

    try:
        response = chat_completion(
            model=_THEME_MODEL,
            messages=messages,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            run_name="theme_selector_stage2",
            disable_thinking=True,
        )
        raw_text = get_response_text(response)
        raw_text = strip_think_tags(raw_text)
    except Exception as exc:
        logger.warning("[ThemeSelector] LLM call failed: %s — using default theme.", exc)
        print(f"  [ThemeSelector] LLM error: {exc} — falling back to '{_DEFAULT_THEME_ID}'")
        return get_theme(_DEFAULT_THEME_ID)

    theme_id = _clean_response(raw_text)
    print(f"  [ThemeSelector] LLM returned: '{raw_text.strip()}' → cleaned: '{theme_id}'")

    if theme_id not in THEMES:
        logger.warning(
            "[ThemeSelector] Invalid theme_id '%s' — falling back to '%s'.",
            theme_id, _DEFAULT_THEME_ID,
        )
        print(
            f"  [ThemeSelector] '{theme_id}' not valid. "
            f"Valid: {list(THEMES.keys())}. Using '{_DEFAULT_THEME_ID}'."
        )
        return get_theme(_DEFAULT_THEME_ID)

    theme = get_theme(theme_id)
    print(f"  [ThemeSelector] Selected theme: '{theme.label}' ({theme.theme_id})")
    return theme
