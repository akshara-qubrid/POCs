"""
AI Product Manager agents:
  - BusinessAgent  → market analysis, monetization, personas, competitive positioning
  - EngineerAgent  → technical feasibility, architecture, complexity, risk
  - PMAgent        → orchestrator; synthesises both analyses into a full PRD
"""
from .agent_executor import AgentExecutor
from .state import SharedState


class BusinessAgent:
    """Handles market opportunity, monetization strategy, user personas, and competitive analysis."""

    def __init__(self, state: SharedState):
        self.state = state
        self.executor = AgentExecutor(
            name="BusinessAgent",
            description=(
                "You are the business analyst. Your role is to evaluate market opportunity, define monetization "
                "strategy, identify user personas, and analyse the competitive landscape. "
                "Use registered tools when helpful. Always return structured JSON."
            ),
            state=state,
            model="openai/gpt-oss-120b",
            max_tokens=1024,
        )

    def analyze_market(self, idea: str) -> dict:
        print(f"\n[BusinessAgent] Analysing market for: {idea[:60]!r}")
        prompt = (
            f"Analyse the product idea: {idea}\n"
            "Return JSON with fields: market_summary, monetization_strategy, user_personas (list), "
            "competitive_considerations, opportunity_score (0-10).\n"
            "You may use the market_opportunity or competitive_analysis tools first if helpful."
        )
        result = self.executor.run(prompt)
        print(f"[BusinessAgent] Done.")
        return result


class EngineerAgent:
    """Handles technical feasibility, architecture recommendations, complexity estimation, and risks."""

    def __init__(self, state: SharedState):
        self.state = state
        self.executor = AgentExecutor(
            name="EngineerAgent",
            description=(
                "You are the engineering analyst. Your role is to assess technical feasibility, recommend "
                "an architecture, estimate complexity, and identify technical risks. "
                "Use registered tools when helpful. Always return structured JSON."
            ),
            state=state,
            model="openai/gpt-oss-120b",
            max_tokens=1024,
        )

    def assess_tech(self, idea: str) -> dict:
        print(f"\n[EngineerAgent] Assessing technical feasibility for: {idea[:60]!r}")
        prompt = (
            f"Analyse the product idea: {idea}\n"
            "Return JSON with fields: feasibility (high/medium/low), architecture_recommendation, "
            "complexity_estimate (story points or T-shirt size), risks (list), suggested_stack (list).\n"
            "You may use the technical_assessment tool first if helpful."
        )
        result = self.executor.run(prompt)
        print(f"[EngineerAgent] Done.")
        return result


class PMAgent:
    """Orchestrates BusinessAgent and EngineerAgent; synthesises outputs into a complete PRD."""

    def __init__(self, state: SharedState, business: BusinessAgent, engineer: EngineerAgent):
        self.state = state
        self.business = business
        self.engineer = engineer
        self.executor = AgentExecutor(
            name="PMAgent",
            description=(
                "You are the product manager orchestrator. You synthesise business and engineering analyses "
                "into a complete Product Requirements Document (PRD). "
                "Use registered tools for roadmap and story generation. Return structured JSON."
            ),
            state=state,
            model="openai/gpt-oss-120b",
            max_tokens=2048,
        )

    def build_prd(self, idea: str) -> dict:
        print(f"\n[PMAgent] Building PRD for: {idea[:60]!r}")

        business_analysis = self.business.analyze_market(idea)
        technical_analysis = self.engineer.assess_tech(idea)

        prompt = (
            "Build a complete Product Requirements Document for the product idea. "
            "Return JSON with fields: summary, user_stories (list), technical_recommendations, "
            "business_recommendations, mvp_roadmap (list of milestones), risks (list).\n"
            "You may use the roadmap_planner tool for structured milestone generation.\n\n"
            f"Business analysis: {business_analysis}\n"
            f"Technical analysis: {technical_analysis}\n"
            f"Product idea: {idea}"
        )
        result = self.executor.run(prompt)
        self.state.add_memory({"type": "prd", "idea": idea, "result": result})
        print(f"[PMAgent] PRD complete.")
        return result
