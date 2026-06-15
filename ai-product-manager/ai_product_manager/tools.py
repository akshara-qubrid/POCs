from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .llm_client import chat_completion, get_response_text
from .utils import extract_json


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


def _execute_model(prompt: str, model: str, max_tokens: int = 600) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a structured business analysis tool. Respond with valid JSON only."},
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)


def market_opportunity(idea: str) -> Dict[str, Any]:
    prompt = (
        "Analyze the market opportunity for the product idea below. "
        "Return JSON with fields: market_summary, monetization_strategy, user_personas, opportunity_score.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt, "mistralai/Mistral-7B-Instruct-v0.3")


def technical_assessment(idea: str) -> Dict[str, Any]:
    prompt = (
        "Assess the technical feasibility of the product idea below. "
        "Return JSON with fields: feasibility, architecture_recommendation, complexity_estimate, risks.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt, "openai/gpt-oss-120b")


def competitive_analysis(idea: str) -> Dict[str, Any]:
    prompt = (
        "Analyze the competitive landscape for the product idea below. "
        "Return JSON with fields: competitors, differentiators, competitive_risks.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt, "mistralai/Mistral-7B-Instruct-v0.3")


def roadmap_planner(idea: str) -> Dict[str, Any]:
    prompt = (
        "Create an MVP roadmap and user stories for the product idea below. "
        "Return JSON with fields: user_stories, mvp_roadmap, release_milestones.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt, "openai/gpt-oss-120b")


def get_tools() -> List[Tool]:
    return [
        Tool(
            name="market_opportunity",
            description="Analyze market opportunity, personas and monetization strategy.",
            func=market_opportunity,
        ),
        Tool(
            name="technical_assessment",
            description="Assess technical feasibility, architecture and risks.",
            func=technical_assessment,
        ),
        Tool(
            name="competitive_analysis",
            description="Identify competitors, differentiators, and competitive risks.",
            func=competitive_analysis,
        ),
        Tool(
            name="roadmap_planner",
            description="Generate MVP roadmap, user stories, and milestones.",
            func=roadmap_planner,
        ),
    ]
