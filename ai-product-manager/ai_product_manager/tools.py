import html as _html_module
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .llm_client import chat_completion, get_response_text
from .utils import extract_json

# This POC uses mistralai/Mistral-7B-Instruct-v0.3 as its primary model.
_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


def _execute_model(prompt: str, max_tokens: int = 800) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a structured business analysis tool. Respond with valid JSON only. Do not use markdown code fences."},
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(model=_MODEL, messages=messages, max_tokens=max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)


# ---------------------------------------------------------------------------
# Web search tool — DuckDuckGo HTML (no API key required)
# ---------------------------------------------------------------------------

def _ddg_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Scrape DuckDuckGo HTML search results. Returns list of {title, url, snippet}."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return [{"title": "Search unavailable", "url": "", "snippet": str(exc)}]

    results: List[Dict[str, str]] = []
    # Extract result blocks: <a class="result__a" href="...">title</a> + <a class="result__snippet">...
    title_pattern = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    titles = title_pattern.findall(body)
    snippets = [m.group(1) for m in snippet_pattern.finditer(body)]

    for i, (raw_url, raw_title) in enumerate(titles[:max_results]):
        # DDG wraps URLs — extract the actual 'uddg' param if present
        try:
            parsed = urllib.parse.urlparse(raw_url)
            params = urllib.parse.parse_qs(parsed.query)
            actual_url = params.get("uddg", [raw_url])[0]
        except Exception:
            actual_url = raw_url

        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        title = _html_module.unescape(title)
        snippet_raw = snippets[i] if i < len(snippets) else ""
        snippet = re.sub(r"<[^>]+>", "", snippet_raw).strip()
        snippet = _html_module.unescape(snippet)
        results.append({"title": title, "url": actual_url, "snippet": snippet})

    return results if results else [{"title": "No results found", "url": "", "snippet": ""}]


def web_search(query: str) -> Dict[str, Any]:
    """Search the web for current information about a query. Returns top results with titles, URLs, and snippets."""
    results = _ddg_search(query, max_results=5)
    # Summarise with LLM so the agent gets structured, usable context
    summary_prompt = (
        "You are a research assistant. Given the following web search results, "
        "extract the most relevant facts and insights. "
        "Return JSON with fields: query (string), summary (string, 2-4 sentences of key findings), "
        "key_facts (list of strings), sources (list of {title, url}).\n\n"
        f"Query: {query}\n\n"
        f"Search results:\n{json.dumps(results, indent=2)}"
    )
    messages = [
        {"role": "system", "content": "You are a research tool. Respond with valid JSON only. Do not use markdown code fences."},
        {"role": "user", "content": summary_prompt},
    ]
    try:
        response = chat_completion(model=_MODEL, messages=messages, max_tokens=600, temperature=0.1)
        text = get_response_text(response)
        return extract_json(text)
    except Exception:
        # Fallback: return raw results as-is
        return {"query": query, "summary": "Search completed.", "key_facts": [], "sources": results}


def market_opportunity(idea: str) -> Dict[str, Any]:
    prompt = (
        "Analyze the market opportunity for the product idea below. "
        "Return JSON with fields: market_summary, monetization_strategy, user_personas, opportunity_score.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt)


def technical_assessment(idea: str) -> Dict[str, Any]:
    prompt = (
        "Assess the technical feasibility of the product idea below. "
        "Return JSON with fields: feasibility, architecture_recommendation, complexity_estimate, risks.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt)


def competitive_analysis(idea: str) -> Dict[str, Any]:
    prompt = (
        "Analyze the competitive landscape for the product idea below. "
        "Return JSON with fields: competitors, differentiators, competitive_risks.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt)


def roadmap_planner(idea: str) -> Dict[str, Any]:
    prompt = (
        "Create an MVP roadmap and user stories for the product idea below. "
        "Return JSON with fields: user_stories, mvp_roadmap, release_milestones.\n"
        f"idea: {idea}"
    )
    return _execute_model(prompt)


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
        Tool(
            name="web_search",
            description=(
                "Search the web for current, real-world information about a topic. "
                "Use this to research market size, competitors, industry news, or any "
                "factual data that benefits from live web results. "
                "Input: a plain-text search query string."
            ),
            func=web_search,
        ),
    ]
