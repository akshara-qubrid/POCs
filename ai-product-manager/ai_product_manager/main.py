"""
AI Product Manager — entry point.

Usage:
    python -m ai_product_manager.main "Your product idea here"

Example:
    python -m ai_product_manager.main "An AI-powered personal finance tracker for Gen Z"
"""
import json
import sys

from .agents import PMAgent, BusinessAgent, EngineerAgent
from .state import SharedState
from .tools import get_tools


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
