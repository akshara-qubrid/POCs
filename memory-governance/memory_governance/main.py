"""
Memory Governance System — entry point.

Usage (CLI):
    python -m memory_governance.main                           # batch demo
    python -m memory_governance.main "item text" "context"    # single item

Usage (API server):
    uvicorn memory_governance.main:app --reload --port 8002

Endpoints:
    POST /consider   {"item": "...", "context": "..."}  →  governance decision
    GET  /memory                                        →  persisted memory store
"""
import json
import sys
from pathlib import Path

from .agents import MemoryGovernor
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

    app = FastAPI(title="Memory Governance", version="1.0.0")
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

    class ConsiderRequest(BaseModel):
        item: str
        context: str = ""

    @app.post("/consider")
    def api_consider(req: ConsiderRequest):
        return run_demo(items=req.item, context=req.context)

    @app.get("/memory")
    def api_memory():
        state = SharedState()
        return state.memory_store

except ImportError:
    app = None  # type: ignore


DEMO_ITEMS = [
    {
        "item": "The user prefers dark mode and wants all dashboards to use a compact layout.",
        "context": "UI personalisation preferences for SaaS product dashboard",
    },
    {
        "item": "Error: connection timeout at 2026-06-15 03:12:44 UTC on worker-7.",
        "context": "System reliability and incident tracking",
    },
    {
        "item": "Meeting notes: Q3 roadmap discussion with engineering team about product X features.",
        "context": "product X roadmap and user personas",
    },
    {
        "item": "Random log line: DEBUG heartbeat ok.",
        "context": "product X roadmap and user personas",
    },
]


def run_demo(items=None, context=None):
    state = SharedState()
    for tool in get_tools():
        state.register_tool(tool)

    governor = MemoryGovernor(state)

    if items and context:
        # Single item mode (called from CLI)
        result = governor.consider(items, context)
        print("\n--- Governance Decision ---")
        print(json.dumps(result, indent=2))
        return result

    # Batch demo mode
    results = []
    for entry in DEMO_ITEMS:
        result = governor.consider(entry["item"], entry["context"])
        results.append({"item": entry["item"], "decision": result})
        print()

    print("\n=== Summary ===")
    for r in results:
        decision = r["decision"].get("decision", "?")
        score = r["decision"].get("importance_score", "?")
        print(f"  [{decision.upper():7}] score={score}  {r['item'][:60]!r}")

    return results


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        run_demo(items=sys.argv[1], context=sys.argv[2])
    else:
        run_demo()
