"""
Startup Due Diligence Engine — entry point.

Usage (CLI):
    python -m due_diligence.main "Your startup description here"

Usage (API server):
    uvicorn due_diligence.main:app --reload --port 8003

Endpoints:
    POST /evaluate   {"startup": "..."}   →  investment report JSON
    GET  /memory                          →  persisted due diligence reports
"""
import json
import sys
from pathlib import Path

from .investment_agent import InvestmentLead
from .leads import MarketLead, ProductLead, FinancialLead
from .state import SharedState
from .tools import get_tools

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


if __name__ == "__main__":
    startup = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "B2B SaaS platform for automated AP/AR reconciliation targeting mid-market CFOs"
    )
    run(startup)
