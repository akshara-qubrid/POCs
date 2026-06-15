import json
from typing import Any, Dict


def _sanitize_json_snippet(snippet: str) -> str:
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
            elif ch in "\r\n":
                result.append("\\n")
            else:
                result.append(ch)
        else:
            if ch == '"':
                result.append(ch)
                in_string = True
            else:
                result.append(ch)
    return ''.join(result)


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Empty LLM response")

    decoder = json.JSONDecoder()
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text}")

    for idx in range(start, len(text)):
        if text[idx] != "{":
            continue
        snippet = text[idx:]
        try:
            candidate, end = decoder.raw_decode(snippet)
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            pass
        try:
            sanitized = _sanitize_json_snippet(snippet)
            candidate, end = decoder.raw_decode(sanitized)
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            continue
    raise ValueError(f"Could not extract valid JSON from response: {text}")
