from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .llm_client import chat_completion, get_response_text
from .utils import extract_json

# This POC uses deepseek-ai/deepseek-r1-distill-llama-70b as its primary model.
# Mistral is used for lighter analysis tools to balance cost and speed.
_PRIMARY = "deepseek-ai/deepseek-r1-distill-llama-70b"
_FAST = "mistralai/Mistral-7B-Instruct-v0.3"


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


def _call_model(prompt: str, model: str, max_tokens: int = 600) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a due diligence analysis tool. Respond with valid JSON only. Do not use markdown code fences."},
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)


def tam_analysis(market: str) -> Dict[str, Any]:
    prompt = (
        "Estimate TAM for the market described below. Return JSON with fields: TAM, confidence, rationale.\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def competition_analysis(market: str) -> Dict[str, Any]:
    prompt = (
        "Analyze the competitive landscape for the market below. Return JSON with fields: num_competitors, intensity, key_players.\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def industry_trends(market: str) -> Dict[str, Any]:
    prompt = (
        "Summarize industry trends relevant to the market below. Return JSON with fields: trend_summary, momentum, risks.\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def product_assessment(product: str) -> Dict[str, Any]:
    prompt = (
        "Assess the product below. Return JSON with fields: product_fit, strengths, weaknesses, improvement_opportunities.\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def ux_assessment(product: str) -> Dict[str, Any]:
    prompt = (
        "Evaluate the UX of the product below. Return JSON with fields: ux_score, issues, recommendations.\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def technical_moat(product: str) -> Dict[str, Any]:
    prompt = (
        "Evaluate the technical moat of the product below. Return JSON with fields: moat_strength, moat_drivers, moat_risks.\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def revenue_model(data: str) -> Dict[str, Any]:
    prompt = (
        "Assess the revenue model below. Return JSON with fields: revenue_model_score, revenue_sources, durability_risk.\n"
        f"data: {data}"
    )
    return _call_model(prompt, _PRIMARY)


def unit_economics(data: str) -> Dict[str, Any]:
    prompt = (
        "Analyze unit economics for the startup described below. Return JSON with fields: unit_economics_rating, payback_period, margin_risk.\n"
        f"data: {data}"
    )
    return _call_model(prompt, _PRIMARY)


def funding_risk(data: str) -> Dict[str, Any]:
    prompt = (
        "Assess funding risks for the startup below. Return JSON with fields: funding_risk_score, key_risks, mitigation.\n"
        f"data: {data}"
    )
    return _call_model(prompt, _FAST)


def get_tools() -> List[Tool]:
    return [
        Tool(name="tam_analysis", description="TAM estimate and confidence.", func=tam_analysis),
        Tool(name="competition_analysis", description="Competitive landscape assessment.", func=competition_analysis),
        Tool(name="industry_trends", description="Industry trend summary.", func=industry_trends),
        Tool(name="product_assessment", description="Product assessment for fit and risks.", func=product_assessment),
        Tool(name="ux_assessment", description="UX evaluation and issues.", func=ux_assessment),
        Tool(name="technical_moat", description="Technical moat assessment.", func=technical_moat),
        Tool(name="revenue_model", description="Revenue model assessment.", func=revenue_model),
        Tool(name="unit_economics", description="Unit economics evaluation.", func=unit_economics),
        Tool(name="funding_risk", description="Funding risk analysis.", func=funding_risk),
    ]
