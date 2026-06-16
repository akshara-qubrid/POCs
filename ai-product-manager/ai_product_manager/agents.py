"""
AI Product Manager agents:
  - BusinessAgent  → market analysis, monetization, personas, competitive positioning
  - EngineerAgent  → technical feasibility, architecture, complexity, risk
  - PMAgent        → orchestrator; synthesises both analyses into a full PRD

Each specialist agent uses an isolated state per call so their conversation
histories never bleed into each other or break the alternating role constraint.
"""
from .agent_executor import AgentExecutor
from .state import SharedState
from .tools import get_tools as _get_tools


def _make_isolated_state(shared: SharedState) -> SharedState:
    """Fresh state with all tools registered but no conversation history."""
    s = SharedState(memory_path=":memory:")
    for tool in _get_tools():
        s.register_tool(tool)
    return s


class BusinessAgent:
    def __init__(self, shared_state: SharedState):
        self.shared_state = shared_state

    def analyze_market(self, idea: str) -> dict:
        print(f"\n[BusinessAgent] Analysing market for: {idea[:60]!r}")
        state = _make_isolated_state(self.shared_state)
        executor = AgentExecutor(
            name="BusinessAgent",
            description=(
                "You are the business analyst. Evaluate market opportunity, define monetization "
                "strategy, identify user personas, and analyse the competitive landscape. "
                "Use registered tools when helpful. Always return structured JSON with key 'final'."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=1200,
        )
        prompt = (
            f"Analyse the product idea: {idea}\n"
            "Return JSON (inside a 'final' key) with fields: market_summary, monetization_strategy, "
            "user_personas (list), competitive_considerations, opportunity_score (0-10).\n"
            "You may call the market_opportunity or competitive_analysis tool first if helpful."
        )
        result = executor.run(prompt)
        print("[BusinessAgent] Done.")
        return result


class EngineerAgent:
    def __init__(self, shared_state: SharedState):
        self.shared_state = shared_state

    def assess_tech(self, idea: str) -> dict:
        print(f"\n[EngineerAgent] Assessing technical feasibility for: {idea[:60]!r}")
        state = _make_isolated_state(self.shared_state)
        executor = AgentExecutor(
            name="EngineerAgent",
            description=(
                "You are the engineering analyst. Assess technical feasibility, recommend an "
                "architecture, estimate complexity, and identify technical risks. "
                "Use registered tools when helpful. Always return structured JSON with key 'final'."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=1200,
        )
        prompt = (
            f"Analyse the product idea: {idea}\n"
            "Return JSON (inside a 'final' key) with fields: feasibility (high/medium/low), "
            "architecture_recommendation (string summary), complexity_estimate, "
            "risks (list), suggested_stack (list).\n"
            "You may call the technical_assessment tool first if helpful."
        )
        result = executor.run(prompt)
        print("[EngineerAgent] Done.")
        return result


class PMAgent:
    def __init__(self, shared_state: SharedState, business: BusinessAgent, engineer: EngineerAgent):
        self.shared_state = shared_state
        self.business = business
        self.engineer = engineer

    def build_prd(self, idea: str) -> dict:
        print(f"\n[PMAgent] Building PRD for: {idea[:60]!r}")

        business_analysis = self.business.analyze_market(idea)
        technical_analysis = self.engineer.assess_tech(idea)

        state = _make_isolated_state(self.shared_state)
        executor = AgentExecutor(
            name="PMAgent",
            description=(
                "You are the product manager orchestrator. Synthesise business and engineering "
                "analyses into a complete Product Requirements Document (PRD). "
                "Use the roadmap_planner tool for milestone generation. "
                "Return structured JSON with key 'final'."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=2048,
        )
        prompt = (
            "Build a complete PRD for the product idea. "
            "Return JSON (inside a 'final' key) with fields: summary, user_stories (list), "
            "technical_recommendations (string), business_recommendations (string), "
            "mvp_roadmap (list of milestone strings), risks (list).\n"
            "You may call the roadmap_planner tool first.\n\n"
            f"Business analysis: {business_analysis}\n"
            f"Technical analysis: {technical_analysis}\n"
            f"Product idea: {idea}"
        )
        result = executor.run(prompt)
        self.shared_state.add_memory({"type": "prd", "idea": idea, "result": result})
        print("[PMAgent] PRD complete.")
        return result
