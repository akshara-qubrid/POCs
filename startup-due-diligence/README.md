# Startup Due Diligence POC

A standalone proof of concept for AI-driven startup due diligence.
This project demonstrates a hierarchical workflow from specialist leads to an investment lead, with structured scoring, analysis, and final recommendation.

## What this project demonstrates

- Hierarchical lead-based due diligence architecture
- Specialist worker analysis for market, product, competition, and finance
- Final synthesis by an investment lead into a complete recommendation memo
- Live Qubrid REST calls for model inference
- Shared state and tool orchestration for the final summarisation step

## Project layout

- `due_diligence/main.py`: CLI entrypoint and pipeline orchestration
- `due_diligence/investment_agent.py`: investment lead synthesiser
- `due_diligence/leads.py`: MarketLead, ProductLead, FinancialLead
- `due_diligence/workers.py`: specialized worker functions for TAM, competition, product assessment, and finance
- `due_diligence/agent_executor.py`: generic JSON/workflow executor
- `due_diligence/llm_client.py`: raw Qubrid REST chat client
- `due_diligence/state.py`: shared state, tool registry, history, memory persistence
- `due_diligence/tools.py`: structured analysis tools for due diligence
- `due_diligence_memory.json`: persisted reports and summaries

## Requirements

- Python 3.12
- `.env` containing `QUBRID_BASE_URL` and `QUBRID_API_KEY`

## Run

```bash
python -m due_diligence.main "B2B SaaS platform for automated AP/AR reconciliation targeting mid-market CFOs"
```

## Notes

- The core InvestmentLead uses structured JSON output, so downstream tooling can ingest the report cleanly.
- Worker functions currently include fallback heuristics when live model text cannot be parsed.
- The pipeline is intentionally easy to extend with additional leads or specialized tools.
