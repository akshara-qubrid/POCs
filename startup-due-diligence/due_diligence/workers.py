from typing import Dict
from .llm_client import chat_completion


def tam_worker(market: str) -> Dict:
    # Use an LLM to expand a TAM estimate (mock by default)
    model = "openai/gpt-oss-120b"
    messages = [{"role": "user", "content": f"Estimate TAM for market: {market}. Provide a numeric estimate and confidence."}]
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    # naive parse: if mock, fall back to default
    if text.startswith("[mock]"):
        return {"TAM": 1000000, "confidence": 0.7}
    # otherwise try to extract a number
    import re
    m = re.search(r"(\d[\d,_]*)", text.replace(',', ''))
    if m:
        try:
            val = int(m.group(1))
            return {"TAM": val, "confidence": 0.6}
        except Exception:
            pass
    return {"TAM": 1000000, "confidence": 0.6}


def competition_worker(market: str) -> Dict:
    model = "mistralai/Mistral-7B-Instruct-v0.3"
    messages = [{"role": "user", "content": f"List competitive landscape features for market: {market}"}]
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    if text.startswith("[mock]"):
        return {"num_competitors": 5, "intensity": "medium"}
    # fallback
    return {"num_competitors": 5, "intensity": "medium"}


def product_assessment_worker(product: str) -> Dict:
    model = "mistralai/Mistral-7B-Instruct-v0.3"
    messages = [{"role": "user", "content": f"Assess product fit for: {product}. Return product_fit 0-1 and UX issues."}]
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    if text.startswith("[mock]"):
        return {"product_fit": 0.8, "ux_issues": ["onboarding"]}
    return {"product_fit": 0.75, "ux_issues": []}


def financial_worker(data: str) -> Dict:
    model = "deepseek-ai/deepseek-r1-distill-llama-70b"
    messages = [{"role": "user", "content": f"Evaluate revenue model and unit economics for: {data}"}]
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    if text.startswith("[mock]"):
        return {"revenue_model_score": 0.6, "unit_economics": "OK"}
    return {"revenue_model_score": 0.6, "unit_economics": "OK"}
