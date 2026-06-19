"""
Startup Due Diligence Engine — entry point.

Usage (CLI):
    python -m due_diligence.main "Your startup description here"

Usage (API server):
    uvicorn due_diligence.main:app --reload --port 8003

Endpoints:
    POST /evaluate             {"startup": "..."}  →  investment report JSON
    POST /pitch-deck           {"startup": "..."}  →  pitch deck JSON + base64 .pptx
    POST /pitch-deck/download  {"startup": "..."}  →  direct .pptx file download
    GET  /memory                                   →  persisted reports
"""
import json
import sys
from pathlib import Path

from .investment_agent import InvestmentLead
from .leads import MarketLead, ProductLead, FinancialLead
from .state import SharedState
from .tools import get_tools


def _safe_filename(text: str) -> str:
    """Convert a title string to a safe filename."""
    import re
    return re.sub(r"[^\w\-]", "_", text).strip("_")[:60] or "pitch-deck"


def _normalize_deck(deck: dict) -> dict:
    """
    Ensure the deck dict is well-formed before passing to build_pptx.
    - slides must be a list
    - each slide's 'content' must be a list of strings
    - preserves slide_type, stats, and advantages fields for rich renderers
    """
    if not isinstance(deck, dict):
        return {"title": "Pitch Deck", "tagline": "", "slides": []}

    slides = deck.get("slides", [])
    if not isinstance(slides, list):
        slides = []

    normalized_slides = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        raw_content = s.get("content", [])
        if isinstance(raw_content, str):
            lines = [ln.strip(" -•▸→*") for ln in raw_content.replace(";", "\n").splitlines()]
            content = [ln for ln in lines if ln]
        elif isinstance(raw_content, list):
            content = [str(item) for item in raw_content]
        else:
            content = []

        # Carry through rich layout fields
        normalized = {**s, "content": content}
        if "stats" not in normalized:
            normalized["stats"] = []
        if "advantages" not in normalized:
            normalized["advantages"] = {}
        if "slide_type" not in normalized:
            normalized["slide_type"] = ""
        normalized_slides.append(normalized)

    return {**deck, "slides": normalized_slides}

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel

    app = FastAPI(title="Startup Due Diligence", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Resolve frontend path relative to this file: ../../frontend/index.html
    _FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    def serve_frontend():
        return HTMLResponse(content=_FRONTEND.read_text(encoding="utf-8"))

    class StartupRequest(BaseModel):
        startup: str

    @app.post("/evaluate")
    def api_evaluate(req: StartupRequest):
        return run(req.startup)

    @app.post("/pitch-deck")
    def api_pitch_deck(req: StartupRequest):
        """Generate an investor pitch deck. Returns slide JSON + base64-encoded .pptx."""
        from .pptx_builder import build_pptx
        import base64
        result = run_pitch_deck(req.startup)
        result = _normalize_deck(result)
        try:
            pptx_bytes = build_pptx(result)
            result["pptx_base64"] = base64.b64encode(pptx_bytes).decode("utf-8")
            result["pptx_filename"] = _safe_filename(result.get("title", "pitch-deck")) + ".pptx"
        except Exception as exc:
            result["pptx_error"] = str(exc)
        return result

    @app.post("/pitch-deck/download")
    def api_pitch_deck_download(req: StartupRequest):
        """Generate a pitch deck and return a real .pptx file for download."""
        from fastapi.responses import Response
        from .pptx_builder import build_pptx
        result = _normalize_deck(run_pitch_deck(req.startup))
        pptx_bytes = build_pptx(result)
        filename = _safe_filename(result.get("title", "pitch-deck")) + ".pptx"
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/memory")
    def api_memory():
        state = SharedState()
        return state.memory_store

except ImportError:
    app = None  # type: ignore


def run(startup: str):
    print(f"\n{'='*60}")
    print(f"Startup Due Diligence Engine")
    print(f"Startup: {startup}")
    print(f"{'='*60}")

    state = SharedState()
    for tool in get_tools():
        state.register_tool(tool)
        print(f"  [tools] registered: {tool.name}")

    # Run specialist leads in parallel (sequential here for simplicity; can be parallelised)
    print("\n[Pipeline] Running Market Lead analysis...")
    market_lead = MarketLead()
    market_result = market_lead.analyze(startup)
    state.add_message("assistant", f"MarketLead findings: {json.dumps(market_result)}")
    print(f"  MarketLead: {market_result}")

    print("\n[Pipeline] Running Product Lead analysis...")
    product_lead = ProductLead()
    product_result = product_lead.analyze(startup)
    state.add_message("assistant", f"ProductLead findings: {json.dumps(product_result)}")
    print(f"  ProductLead: {product_result}")

    print("\n[Pipeline] Running Financial Lead analysis...")
    financial_lead = FinancialLead()
    financial_result = financial_lead.analyze(startup)
    state.add_message("assistant", f"FinancialLead findings: {json.dumps(financial_result)}")
    print(f"  FinancialLead: {financial_result}")

    # Investment Lead synthesises all findings
    print("\n[Pipeline] Investment Lead synthesising final report...")
    lead = InvestmentLead(state)
    enriched_prompt = startup + (
        f"\n\nPre-computed specialist analyses:\n"
        f"market: {json.dumps(market_result)}\n"
        f"product: {json.dumps(product_result)}\n"
        f"financial: {json.dumps(financial_result)}"
    )
    result = lead.evaluate(enriched_prompt)

    print(f"\n{'='*60}")
    print("FINAL DUE DILIGENCE REPORT")
    print(f"{'='*60}")
    print(json.dumps(result, indent=2))
    return result


def run_pitch_deck(startup: str) -> dict:
    """
    Generate a pitch deck grounded in real due diligence data.

    Runs the full due diligence pipeline first (market, product, financial
    leads + investment lead synthesis), then passes the structured report
    into generate_pitch_deck so every slide uses real scores, TAM figures,
    competitor names, and risk items rather than LLM-invented content.
    """
    print(f"\n{'='*60}")
    print(f"Pitch Deck Generator")
    print(f"Startup: {startup}")
    print(f"{'='*60}")

    # Step 1 — run the full due diligence pipeline to get the report
    print("\n[PitchDeck] Running due diligence pipeline for grounding data...")
    report = run(startup)

    # Step 2 — generate the deck, passing the real report as context
    print("\n[PitchDeck] Generating slides from due diligence report...")
    from .tools import generate_pitch_deck
    result = generate_pitch_deck(startup, report=report)

    # Unwrap common nesting patterns (LLM sometimes wraps the deck under a key)
    if isinstance(result, dict) and "slides" not in result:
        for key in ("pitch_deck", "deck", "result", "data", "output"):
            if key in result and isinstance(result[key], dict) and "slides" in result[key]:
                result = result[key]
                break

    # Persist a lean copy to memory (no pptx bytes)
    state = SharedState()
    lean = {k: v for k, v in result.items() if k not in ("html", "pptx_base64")} if isinstance(result, dict) else result
    state.add_memory({"type": "pitch_deck", "startup": startup[:120], "result": lean})

    print(f"\n[PitchDeck] Done — {len(result.get('slides', []))} slides generated.")
    return result


if __name__ == "__main__":
    startup = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "B2B SaaS platform for automated AP/AR reconciliation targeting mid-market CFOs"
    )
    run(startup)
