"""
Memory Governance agents:
  - RetentionAgent   → decides if an item should be stored and assigns a retention score
  - RelevanceAgent   → evaluates future usefulness and retrieval priority
  - MemoryGovernor   → arbitrates between sub-agents and manages the memory lifecycle

Each sub-agent uses an isolated state so their conversation histories don't
interfere with each other or break the API's alternating user/assistant constraint.
"""
from .agent_executor import AgentExecutor
from .state import SharedState
from .tools import get_tools as _get_tools


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


class MemoryGovernor:
    """Orchestrates RetentionAgent and RelevanceAgent; manages the full memory lifecycle."""

    def __init__(self, shared_state: SharedState):
        self.shared_state = shared_state
        self.retention_agent = RetentionAgent()
        self.relevance_agent = RelevanceAgent()

    def _make_governor_executor(self) -> AgentExecutor:
        """Governor also uses an isolated state per call to avoid history contamination."""
        state = _make_isolated_state()
        return AgentExecutor(
            name="MemoryGovernor",
            description=(
                "You are the memory governor. You receive retention and relevance analyses and make the final "
                "store/discard decision, assign an overall importance score, and produce a governance explanation. "
                "Return structured JSON only."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=700,
        )

    def consider(self, item: str, context: str) -> dict:
        print(f"\n[MemoryGovernor] Evaluating item: {item!r}")
        print("[MemoryGovernor] → delegating to RetentionAgent...")
        retention = self.retention_agent.evaluate(item)
        print(f"[MemoryGovernor] RetentionAgent result: {retention}")

        print("[MemoryGovernor] → delegating to RelevanceAgent...")
        relevance = self.relevance_agent.evaluate(item, context)
        print(f"[MemoryGovernor] RelevanceAgent result: {relevance}")

        governor_executor = self._make_governor_executor()
        prompt = (
            "Based on the retention and relevance analyses below, make a final governance decision. "
            "Return JSON with fields: decision (store/discard), importance_score (0-1), "
            "retention_category (string), retrieval_priority (high/medium/low), explanation (string).\n"
            f"retention_analysis: {retention}\n"
            f"relevance_analysis: {relevance}\n"
            f"item: {item}\ncontext: {context}"
        )
        result = governor_executor.run(prompt)

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
