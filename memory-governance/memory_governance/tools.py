from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .llm_client import chat_completion, get_response_text
from .utils import extract_json


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


def _call_model(prompt: str, model: str, max_tokens: int = 400) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a memory governance analysis tool. Respond only with valid JSON."},
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)


def score_retention(item: str) -> Dict[str, Any]:
    prompt = (
        "Score the retention value of the item below and categorize it. "
        "Return JSON with fields: score, category, reasoning.\n"
        f"item: {item}"
    )
    return _call_model(prompt, "mistralai/Mistral-7B-Instruct-v0.3")


def score_relevance(item_and_context: str) -> Dict[str, Any]:
    prompt = (
        "Evaluate the relevance of the item below to the provided context. "
        "Return JSON with fields: relevance, priority, reasoning.\n"
        f"{item_and_context}"
    )
    return _call_model(prompt, "openai/gpt-oss-120b")


def get_tools() -> List[Tool]:
    return [
        Tool(name="score_retention", description="Score and categorize memory retention.", func=score_retention),
        Tool(name="score_relevance", description="Evaluate memory relevance to a context.", func=score_relevance),
    ]
