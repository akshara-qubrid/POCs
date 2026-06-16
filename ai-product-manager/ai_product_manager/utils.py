import json
import re
from typing import Any, Dict


def _normalize_text(text: str) -> str:
    """Replace common non-standard unicode punctuation with ASCII equivalents."""
    replacements = {
        "\u2011": "-",   # non-breaking hyphen
        "\u2012": "-",   # figure dash
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _sanitize_json_snippet(snippet: str) -> str:
    """
    Walk the snippet character-by-character to fix common LLM JSON issues:
    - Literal newlines/tabs inside string values → escaped equivalents
    - Trailing commas before } or ]
    """
    result = []
    in_string = False
    escape = False
    for ch in snippet:
        if in_string:
            if escape:
                result.append(ch)
                escape = False
            elif ch == "\\":
                result.append(ch)
                escape = True
            elif ch == '"':
                result.append(ch)
                in_string = False
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            if ch == '"':
                result.append(ch)
                in_string = True
            else:
                result.append(ch)
    joined = "".join(result)
    # Remove trailing commas before closing braces/brackets
    joined = re.sub(r",\s*([}\]])", r"\1", joined)
    return joined


def extract_json(text: str) -> Dict[str, Any]:
    text = _normalize_text(text.strip())
    if not text:
        raise ValueError("Empty LLM response")

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    decoder = json.JSONDecoder()

    # Try each '{' as a potential start of a JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")

    for idx in range(start, len(text)):
        if text[idx] != "{":
            continue
        snippet = text[idx:]

        # Attempt 1: parse as-is
        try:
            candidate, _ = decoder.raw_decode(snippet)
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            pass

        # Attempt 2: sanitize then parse
        try:
            sanitized = _sanitize_json_snippet(snippet)
            candidate, _ = decoder.raw_decode(sanitized)
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            pass

        # Attempt 3: find matching closing brace and truncate
        try:
            depth = 0
            end_idx = None
            in_str = False
            esc = False
            for i, ch in enumerate(snippet):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i + 1
                        break
            if end_idx:
                truncated = snippet[:end_idx]
                sanitized = _sanitize_json_snippet(truncated)
                candidate, _ = decoder.raw_decode(sanitized)
                if isinstance(candidate, dict):
                    return candidate
        except (json.JSONDecodeError, Exception):
            continue

    raise ValueError(f"Could not extract valid JSON from response: {text[:300]}")
