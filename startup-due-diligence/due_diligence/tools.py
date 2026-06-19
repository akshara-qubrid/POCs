import html as _html_module
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .llm_client import chat_completion, get_response_text
from .utils import extract_json

# ---------------------------------------------------------------------------
# Available models — swap _PRIMARY / _FAST / _STRUCTURED below to test each
# ---------------------------------------------------------------------------

# Text / reasoning models
_MISTRAL_7B          = "mistralai/Mistral-7B-Instruct-v0.3"
_DEEPSEEK_R1_70B     = "deepseek-ai/deepseek-r1-distill-llama-70b"
_QWEN3_VL_30B        = "Qwen/Qwen3-VL-30B-A3B-Instruct"
_QWEN3_VL_8B         = "Qwen/Qwen3-VL-8B-Instruct"
_GPT_OSS_120B        = "openai/gpt-oss-120b"
_NVIDIA_ORCH_8B      = "nvidia/Orchestrator-8B"
_FARA_7B             = "microsoft/Fara-7B"

# Specialised / multimodal models (added for manual testing)
_HUNYUAN_OCR         = "tencent/HunyuanOCR"       # OCR / document understanding
_WHISPER_LARGE_V3    = "openai/whisper-large-v3"  # Speech-to-text (audio input)

# ---------------------------------------------------------------------------
# Active role assignments — change these to test a different model
# ---------------------------------------------------------------------------

# Primary: used for financial / revenue analysis (needs strong reasoning)
_PRIMARY    = _DEEPSEEK_R1_70B

# Fast: used for lighter analysis tools (TAM, competition, trends, UX …)
_FAST       = _MISTRAL_7B

# Structured: used for slide-deck generation (needs rich instruction following)
_STRUCTURED = _FARA_7B


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


# ---------------------------------------------------------------------------
# Web search — DuckDuckGo HTML (no API key required)
# Defined early so _search_context and all analysis tools can use it.
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
    title_pattern = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    titles = title_pattern.findall(body)
    snippets = [m.group(1) for m in snippet_pattern.finditer(body)]

    for i, (raw_url, raw_title) in enumerate(titles[:max_results]):
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


# ---------------------------------------------------------------------------

def _call_model(prompt: str, model: str, max_tokens: int = 600) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a due diligence analysis tool. Respond with valid JSON only. Do not use markdown code fences."},
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2)
    text = get_response_text(response)
    try:
        return extract_json(text)
    except ValueError as exc:
        # Log the raw response for debugging, then re-raise
        print(f"[ERROR] extract_json failed: {exc}")
        print(f"[DEBUG] Raw LLM response (first 500 chars): {text[:500]}")
        raise


def _search_context(query: str) -> str:
    """Run a web search and return a compact context string to inject into prompts."""
    print(f"[web_search] {query}")
    results = _ddg_search(query, max_results=5)
    lines = []
    for r in results:
        if r.get("snippet"):
            lines.append(f"- {r['title']}: {r['snippet']}")
    return "\n".join(lines) if lines else "No web results available."


# ---------------------------------------------------------------------------
# Existing analysis tools (each grounded with a live web search)
# ---------------------------------------------------------------------------

def tam_analysis(market: str) -> Dict[str, Any]:
    context = _search_context(f"{market} total addressable market size estimate")
    prompt = (
        "Estimate TAM for the market described below. Return JSON with fields: TAM, confidence, rationale.\n\n"
        f"Live web research:\n{context}\n\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def competition_analysis(market: str) -> Dict[str, Any]:
    context = _search_context(f"{market} competitors landscape key players")
    prompt = (
        "Analyze the competitive landscape for the market below. Return JSON with fields: num_competitors, intensity, key_players.\n\n"
        f"Live web research:\n{context}\n\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def industry_trends(market: str) -> Dict[str, Any]:
    context = _search_context(f"{market} industry trends 2024 2025")
    prompt = (
        "Summarize industry trends relevant to the market below. Return JSON with fields: trend_summary, momentum, risks.\n\n"
        f"Live web research:\n{context}\n\n"
        f"market: {market}"
    )
    return _call_model(prompt, _FAST)


def product_assessment(product: str) -> Dict[str, Any]:
    context = _search_context(f"{product} product reviews strengths weaknesses")
    prompt = (
        "Assess the product below. Return JSON with fields: product_fit, strengths, weaknesses, improvement_opportunities.\n\n"
        f"Live web research:\n{context}\n\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def ux_assessment(product: str) -> Dict[str, Any]:
    context = _search_context(f"{product} user experience UX feedback usability")
    prompt = (
        "Evaluate the UX of the product below. Return JSON with fields: ux_score, issues, recommendations.\n\n"
        f"Live web research:\n{context}\n\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def technical_moat(product: str) -> Dict[str, Any]:
    context = _search_context(f"{product} technical differentiation patents technology moat")
    prompt = (
        "Evaluate the technical moat of the product below. Return JSON with fields: moat_strength, moat_drivers, moat_risks.\n\n"
        f"Live web research:\n{context}\n\n"
        f"product: {product}"
    )
    return _call_model(prompt, _FAST)


def revenue_model(data: str) -> Dict[str, Any]:
    context = _search_context(f"{data} revenue model pricing monetization strategy")
    prompt = (
        "Assess the revenue model below. Return JSON with fields: revenue_model_score, revenue_sources, durability_risk.\n\n"
        f"Live web research:\n{context}\n\n"
        f"data: {data}"
    )
    return _call_model(prompt, _PRIMARY)


def unit_economics(data: str) -> Dict[str, Any]:
    context = _search_context(f"{data} unit economics CAC LTV payback period benchmarks")
    prompt = (
        "Analyze unit economics for the startup described below. Return JSON with fields: unit_economics_rating, payback_period, margin_risk.\n\n"
        f"Live web research:\n{context}\n\n"
        f"data: {data}"
    )
    return _call_model(prompt, _PRIMARY)


def funding_risk(data: str) -> Dict[str, Any]:
    context = _search_context(f"{data} startup funding risk venture capital market conditions")
    prompt = (
        "Assess funding risks for the startup below. Return JSON with fields: funding_risk_score, key_risks, mitigation.\n\n"
        f"Live web research:\n{context}\n\n"
        f"data: {data}"
    )
    return _call_model(prompt, _FAST)



# ---------------------------------------------------------------------------
# web_search public tool
# ---------------------------------------------------------------------------

def web_search(query: str) -> Dict[str, Any]:
    """Search the web for current information. Returns a structured summary with key facts and sources."""
    results = _ddg_search(query, max_results=5)
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
        response = chat_completion(model=_FAST, messages=messages, max_tokens=600, temperature=0.1)
        text = get_response_text(response)
        return extract_json(text)
    except Exception:
        return {"query": query, "summary": "Search completed.", "key_facts": [], "sources": results}


# ---------------------------------------------------------------------------
# Pitch deck / slide generator tool
# ---------------------------------------------------------------------------

def generate_pitch_deck(startup: str, report: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generate a structured investor pitch deck for a startup.

    When a due diligence `report` dict is supplied (from the full pipeline),
    the LLM is grounded with real analysis data — TAM, competitors, moat,
    risks, scores, etc. — rather than inventing its own figures.

    Returns JSON with 'title', 'tagline', and a 'slides' list.
    Each slide has: slide_number, slide_type, title, content (list of strings,
    max 6), stats (optional KPI cards), advantages (optional comparison dict),
    speaker_notes.

    The caller converts this to a premium .pptx via pptx_builder.build_pptx().
    """
    # Build a concise, structured summary of the due diligence findings so the
    # LLM has concrete numbers and facts to pull into every slide.
    if report and isinstance(report, dict):
        def _fmt(v: Any) -> str:
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False)
            return str(v)

        dd_lines = ["=== Due Diligence Report (use these facts in the slides) ==="]

        field_labels = {
            "market_score":               "Market score (0-10)",
            "product_score":              "Product score (0-10)",
            "financial_score":            "Financial score (0-10)",
            "overall_score":              "Overall investment score (0-10)",
            "investment_recommendation":  "Investment recommendation",
            "risk_assessment":            "Risk assessment",
            "key_strengths":              "Key strengths",
            "key_risks":                  "Key risks",
            "report":                     "Full memo",
            # specialist fields that may exist if leads stored their output
            "TAM":                        "TAM",
            "confidence":                 "TAM confidence",
            "rationale":                  "TAM rationale",
            "num_competitors":            "Number of competitors",
            "intensity":                  "Competitive intensity",
            "key_players":                "Key competitors",
            "trend_summary":              "Industry trend summary",
            "momentum":                   "Market momentum",
            "risks":                      "Market risks",
            "moat_strength":              "Technical moat strength",
            "moat_drivers":               "Moat drivers",
            "moat_risks":                 "Moat risks",
            "revenue_model_score":        "Revenue model score",
            "revenue_sources":            "Revenue sources",
            "durability_risk":            "Revenue durability risk",
            "unit_economics_rating":      "Unit economics rating",
            "payback_period":             "Payback period",
            "margin_risk":                "Margin risk",
            "funding_risk_score":         "Funding risk score",
        }

        for key, label in field_labels.items():
            val = report.get(key)
            if val is not None and val != "" and val != [] and val != {}:
                dd_lines.append(f"  {label}: {_fmt(val)}")

        # Also capture any extra top-level keys not in our label map
        known = set(field_labels.keys())
        for key, val in report.items():
            if key not in known and val not in (None, "", [], {}):
                dd_lines.append(f"  {key}: {_fmt(val)}")

        dd_context = "\n".join(dd_lines)
        print(f"[generate_pitch_deck] Grounding with due diligence report ({len(dd_lines)-1} fields)")
    else:
        dd_context = "(No due diligence report provided — use your best judgment based on the startup description.)"
        print("[generate_pitch_deck] No report supplied — falling back to LLM-only generation")

    prompt = (
        "You are a world-class startup pitch consultant and product storyteller. "
        "Create a visually compelling investor pitch deck for the startup described below. "
        "You MUST use the facts, scores, and figures from the due diligence report wherever relevant "
        "(TAM, competitor names, moat drivers, risk items, scores, etc.). "
        "Do NOT invent numbers that contradict the report. "
        "Return ONLY a valid JSON object — no markdown, no code fences, no extra text.\n\n"
        "JSON root fields:\n"
        "  title (string): startup/deck name\n"
        "  tagline (string): punchy one-line value proposition (max 12 words)\n"
        "  slides (array of slide objects)\n\n"
        "Each slide object has these fields:\n"
        "  slide_number (int)\n"
        "  slide_type (string): MUST be one of: cover, problem, solution, product, architecture, usecases, comparison, roadmap, closing\n"
        "  title (string): slide title\n"
        "  content (array of strings): max 6 items, max 18 words each.\n"
        "    - For solution slide: format as 'Feature Name: brief description'\n"
        "    - For architecture slide: format as 'Step Label: what happens here'\n"
        "    - For usecases slide: format as 'Use Case Name: who benefits and how'\n"
        "    - For comparison slide: list the PROBLEMS/LIMITATIONS of alternatives (we show our advantage separately)\n"
        "    - For roadmap slide: one milestone per item, max 15 words\n"
        "  stats (array, optional): for usecases and product slides, include up to 3 objects:\n"
        "    {\"metric\": \"TAM\", \"value\": \"$12B\", \"subtitle\": \"by 2027\"} — use report figures if available\n"
        "  advantages (object, optional): for comparison slide only, keyed by content index '0','1',...\n"
        "    value = how YOUR product solves that problem (max 15 words)\n"
        "  speaker_notes (string): 2-3 sentences for the presenter\n\n"
        "Generate EXACTLY these 8 slides in this order:\n"
        "  1. cover — company intro\n"
        "  2. problem — 1 big pain + 3-4 supporting problems (draw from report key_risks / risk_assessment)\n"
        "  3. solution — 4-6 feature cards with titles and descriptions (draw from report key_strengths / moat_drivers)\n"
        "  4. product — 2 stat cards (use report scores/metrics as values) + 4-6 capability bullets\n"
        "  5. architecture — 4-5 step pipeline (how the system works end-to-end)\n"
        "  6. usecases — 2-3 market stat cards (use TAM, scores from report) + 3-4 use case cards\n"
        "  7. comparison — 4-5 competitor limitations (draw from key_players / competitive intensity) + our advantages dict\n"
        "  8. roadmap — 4-5 milestone phases on a timeline\n\n"
        "Do NOT include Traction, Financials, or Fundraising slides.\n\n"
        f"{dd_context}\n\n"
        f"Startup: {startup}"
    )
    return _call_model(prompt, _STRUCTURED, max_tokens=4000)


def get_tools() -> List[Tool]:
    return [
        Tool(name="tam_analysis",        description="TAM estimate and confidence.",                      func=tam_analysis),
        Tool(name="competition_analysis", description="Competitive landscape assessment.",                 func=competition_analysis),
        Tool(name="industry_trends",      description="Industry trend summary.",                          func=industry_trends),
        Tool(name="product_assessment",   description="Product assessment for fit and risks.",             func=product_assessment),
        Tool(name="ux_assessment",        description="UX evaluation and issues.",                        func=ux_assessment),
        Tool(name="technical_moat",       description="Technical moat assessment.",                       func=technical_moat),
        Tool(name="revenue_model",        description="Revenue model assessment.",                        func=revenue_model),
        Tool(name="unit_economics",       description="Unit economics evaluation.",                       func=unit_economics),
        Tool(name="funding_risk",         description="Funding risk analysis.",                           func=funding_risk),
        Tool(
            name="web_search",
            description=(
                "Search the web for current, real-world information. Use this to research "
                "market size, recent funding rounds, competitor news, regulatory landscape, "
                "or any factual data that benefits from live results. "
                "Input: a plain-text search query string."
            ),
            func=web_search,
        ),
        Tool(
            name="generate_pitch_deck",
            description=(
                "Generate a premium investor pitch deck (8 slides) for a startup. "
                "Slides: Cover, Problem, Solution, Product Overview, Architecture, "
                "Use Cases & Market Opportunity, Competitive Advantages, Roadmap. "
                "Returns structured slide data with slide_type, content, stats, and advantages fields. "
                "The API converts this to a downloadable PowerPoint .pptx file. "
                "Best called after due diligence analysis is complete so slides are grounded in real data. "
                "Input: startup description string."
            ),
            func=lambda startup: generate_pitch_deck(startup, report=None),
        ),
    ]
