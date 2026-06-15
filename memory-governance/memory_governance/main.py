"""
Memory Governance System — demo entry point.

Runs the MemoryGovernor over a set of sample items and prints governance decisions.
"""
import json
import sys

from .agents import MemoryGovernor
from .state import SharedState
from .tools import get_tools


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
