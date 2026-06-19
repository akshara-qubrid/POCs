"""
Memory Governance agents:
  - RetentionAgent   → decides if an item should be stored and assigns a retention score
  - RelevanceAgent   → evaluates future usefulness and retrieval priority
  - MemoryGovernor   → arbitrates between sub-agents (run in parallel) and manages the
                       memory lifecycle using deterministic rule-based logic (no LLM call)

Each sub-agent uses an isolated state so their conversation histories don't
interfere with each other or break the API's alternating user/assistant constraint.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .agent_executor import AgentExecutor
from .state import SharedState
from .tools import get_tools as _get_tools

# ── Governance thresholds (deterministic governor) ──────────────────────────
_RETENTION_STORE_THRESHOLD = 0.4   # minimum retention_score to consider storing
_RELEVANCE_STORE_THRESHOLD = 0.3   # minimum relevance_score to consider storing
_HIGH_PRIORITY_THRESHOLD   = 0.7   # combined score above which priority is "high"
_MEDIUM_PRIORITY_THRESHOLD = 0.4   # combined score above which priority is "medium"


def _make_isolated_state() -> SharedState:
    """Create a fresh, tool-equipped state for a single sub-agent call."""
    s = SharedState(memory_path=":memory:")  # use a no-op path — sub-agents don't persist
    for tool in _get_tools():
        s.register_tool(tool)
    return s


class RetentionAgent:
    """Determines whether information should be stored and categorises it."""

    def evaluate(self, item: str) -> dict:
        state = _make_isolated_state()
        executor = AgentExecutor(
            name="RetentionAgent",
            description=(
                "You are the retention specialist. Evaluate whether the item below should be stored in long-term memory. "
                "Assign a retention score (0-1), choose a category, detect any duplicates already in context, "
                "and return structured JSON. Use the score_retention tool if helpful."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=600,
        )
        prompt = (
            "Evaluate the retention value of the item below. "
            "Return JSON with fields: should_store (bool), retention_score (0-1), "
            "category (string), is_duplicate (bool), reasoning (string).\n"
            f"item: {item}"
        )
        return executor.run(prompt)


class RelevanceAgent:
    """Scores contextual relevance and determines retrieval priority."""

    def evaluate(self, item: str, context: str) -> dict:
        state = _make_isolated_state()
        executor = AgentExecutor(
            name="RelevanceAgent",
            description=(
                "You are the relevance specialist. Given an item and its context, evaluate future usefulness, "
                "contextual relevance, retrieval priority, and identify relationships with existing memory. "
                "Use the score_relevance tool if helpful. Return structured JSON."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=600,
        )
        prompt = (
            "Evaluate the relevance of the item to the given context. "
            "Return JSON with fields: relevance_score (0-1), retrieval_priority (high/medium/low), "
            "future_usefulness (string), memory_relationships (list of strings), reasoning (string).\n"
            f"item: {item}\ncontext: {context}"
        )
        return executor.run(prompt)


def _governor_decide(retention: dict, relevance: dict) -> dict:
    """
    Pure, deterministic governance logic — no LLM involved.

    Rules (applied in order):
    1. If the retention agent explicitly flagged should_store=False, discard immediately.
    2. If retention_score < _RETENTION_STORE_THRESHOLD, discard.
    3. If relevance_score < _RELEVANCE_STORE_THRESHOLD, discard.
    4. Otherwise store; derive importance_score and retrieval_priority from scores.
    """
    retention_score: float = float(retention.get("retention_score", 0.0))
    relevance_score: float = float(relevance.get("relevance_score", 0.0))
    should_store: bool = bool(retention.get("should_store", True))
    is_duplicate: bool = bool(retention.get("is_duplicate", False))
    category: str = str(retention.get("category", "general"))

    # ── Rule 1: explicit discard flag ──
    if not should_store:
        return {
            "decision": "discard",
            "importance_score": retention_score,
            "retention_category": category,
            "retrieval_priority": "low",
            "explanation": (
                f"RetentionAgent flagged should_store=False. "
                f"retention_score={retention_score:.2f}, relevance_score={relevance_score:.2f}"
            ),
        }

    # ── Rule 2: retention below threshold ──
    if retention_score < _RETENTION_STORE_THRESHOLD:
        return {
            "decision": "discard",
            "importance_score": retention_score,
            "retention_category": category,
            "retrieval_priority": "low",
            "explanation": (
                f"retention_score={retention_score:.2f} is below threshold {_RETENTION_STORE_THRESHOLD}."
            ),
        }

    # ── Rule 3: relevance below threshold ──
    if relevance_score < _RELEVANCE_STORE_THRESHOLD:
        return {
            "decision": "discard",
            "importance_score": relevance_score,
            "retention_category": category,
            "retrieval_priority": "low",
            "explanation": (
                f"relevance_score={relevance_score:.2f} is below threshold {_RELEVANCE_STORE_THRESHOLD}."
            ),
        }

    # ── Rule 4: store — compute derived fields ──
    # Weighted average: retention counts slightly more than relevance
    importance_score = round(0.55 * retention_score + 0.45 * relevance_score, 4)

    # Duplicate items get deprioritised one level
    if importance_score >= _HIGH_PRIORITY_THRESHOLD and not is_duplicate:
        priority = "high"
    elif importance_score >= _MEDIUM_PRIORITY_THRESHOLD:
        priority = "medium"
    else:
        priority = "low"

    return {
        "decision": "store",
        "importance_score": importance_score,
        "retention_category": category,
        "retrieval_priority": priority,
        "explanation": (
            f"Passed all thresholds. "
            f"retention_score={retention_score:.2f}, relevance_score={relevance_score:.2f}, "
            f"importance_score={importance_score:.4f}, is_duplicate={is_duplicate}."
        ),
    }


class MemoryGovernor:
    """
    Orchestrates RetentionAgent and RelevanceAgent in parallel;
    makes the final store/discard decision using deterministic rules (no LLM).
    """

    def __init__(self, shared_state: SharedState):
        self.shared_state = shared_state
        self.retention_agent = RetentionAgent()
        self.relevance_agent = RelevanceAgent()

    def consider(self, item: str, context: str) -> dict:
        print(f"\n[MemoryGovernor] Evaluating item: {item!r}")
        print("[MemoryGovernor] → running RetentionAgent and RelevanceAgent in parallel...")

        # ── Parallel execution of the two sub-agents ──────────────────────
        retention: Any = None
        relevance: Any = None
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_retention = pool.submit(self.retention_agent.evaluate, item)
            future_relevance = pool.submit(self.relevance_agent.evaluate, item, context)

            for future in as_completed({future_retention, future_relevance}):
                if future is future_retention:
                    try:
                        retention = future.result()
                        print(f"[MemoryGovernor] RetentionAgent result: {retention}")
                    except Exception as exc:
                        errors.append(f"RetentionAgent failed: {exc}")
                        retention = {"retention_score": 0.0, "should_store": False,
                                     "category": "error", "is_duplicate": False}
                else:
                    try:
                        relevance = future.result()
                        print(f"[MemoryGovernor] RelevanceAgent result: {relevance}")
                    except Exception as exc:
                        errors.append(f"RelevanceAgent failed: {exc}")
                        relevance = {"relevance_score": 0.0, "retrieval_priority": "low"}

        # ── Deterministic governance decision ─────────────────────────────
        result = _governor_decide(retention, relevance)
        if errors:
            result["warnings"] = errors

        if result.get("decision") == "store":
            self.shared_state.add_memory({
                "item": item,
                "context": context,
                "retention": retention,
                "relevance": relevance,
                "governance": result,
            })
            print(f"[MemoryGovernor] ✓ Stored — importance={result.get('importance_score')}  "
                  f"priority={result.get('retrieval_priority')}")
        else:
            print(f"[MemoryGovernor] ✗ Discarded — {result.get('explanation', '')[:80]}")

        return result
