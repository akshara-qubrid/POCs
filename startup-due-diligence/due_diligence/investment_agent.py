"""
InvestmentLead: top-level orchestrator for the due diligence workflow.
Receives pre-computed specialist analyses and synthesises a final investment memo.
"""
from .agent_executor import AgentExecutor
from .state import SharedState


class InvestmentLead:
    def __init__(self, state: SharedState):
        self.state = state
        self.executor = AgentExecutor(
            name="InvestmentLead",
            description=(
                "You are the investment lead orchestrating market, product, and financial due diligence. "
                "Use registered tools when you need deeper analysis on specific areas. "
                "Aggregate all scores and issue a final investment recommendation with a full investment memo. "
                "Return structured JSON only."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=1500,
        )

    def evaluate(self, startup: str) -> dict:
        print(f"\n[InvestmentLead] Synthesising due diligence report...")
        prompt = (
            "Perform final due diligence synthesis for the startup described below. "
            "Return JSON with fields: market_score (0-10), product_score (0-10), financial_score (0-10), "
            "overall_score (0-10), risk_assessment (string), investment_recommendation (invest/pass/conditional), "
            "report (string with full memo), key_strengths (list), key_risks (list).\n"
            f"startup: {startup}"
        )
        result = self.executor.run(prompt)
        self.state.add_memory({"type": "due_diligence_report", "startup": startup[:120], "result": result})
        return result
