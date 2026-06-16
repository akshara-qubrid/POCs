"""
AI Product Manager — entry point.

Usage (CLI):
    python -m ai_product_manager.main "Your product idea here"

Usage (API server):
    uvicorn ai_product_manager.main:app --reload --port 8001

Endpoints:
    POST /run     {"idea": "..."}   →  PRD JSON
    GET  /memory                   →  persisted PRDs
"""
import json
import sys
from pathlib import Path

from .agents import PMAgent, BusinessAgent, EngineerAgent
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

    app = FastAPI(title="AI Product Manager", version="1.0.0")
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

    class IdeaRequest(BaseModel):
        idea: str

    @app.post("/run")
    def api_run(req: IdeaRequest):
        return run(req.idea)

    @app.get("/memory")
    def api_memory():
        state = SharedState()
        return state.memory_store

except ImportError:
    app = None  # type: ignore


def run(idea: str):
    print(f"\n{'='*60}")
    print(f"AI Product Manager")
    print(f"Idea: {idea}")
    print(f"{'='*60}")

    state = SharedState()
    for tool in get_tools():
        state.register_tool(tool)
        print(f"  [tools] registered: {tool.name}")

    business = BusinessAgent(state)
    engineer = EngineerAgent(state)
    pm = PMAgent(state, business, engineer)

    prd = pm.build_prd(idea)

    print(f"\n{'='*60}")
    print("FINAL PRD OUTPUT")
    print(f"{'='*60}")
    print(json.dumps(prd, indent=2))
    return prd


if __name__ == "__main__":
    idea = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "An AI-powered personal finance tracker for Gen Z"
    run(idea)
