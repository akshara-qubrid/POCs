# AI Product Manager POC

A standalone proof of concept for an AI-driven product management workflow.
This project demonstrates a multi-agent architecture that combines business analysis, technical assessment, and product orchestration into a structured Product Requirements Document (PRD).

## What this project demonstrates

- Multi-agent orchestration with separate `BusinessAgent`, `EngineerAgent`, and `PMAgent`
- Live Qubrid REST integration via `llm_client.py` for model calls
- Structured JSON-only outputs and tool-driven agent workflows
- Shared state history, tool registration, and persistent memory storage
- Tool handoff where agents can request `tool` actions and receive results before final output

## Project layout

- `ai_product_manager/main.py`: CLI entrypoint and runner
- `ai_product_manager/agents.py`: agent classes and orchestration
- `ai_product_manager/agent_executor.py`: conversation build + tool loop executor
- `ai_product_manager/llm_client.py`: raw Qubrid REST chat completion client
- `ai_product_manager/state.py`: shared state, tool registry, history, memory persistence
- `ai_product_manager/tools.py`: tool implementations and model helpers
- `ai_product_manager/utils.py`: JSON extraction utilities
- `ai_product_manager_memory.json`: generated memory store for this POC

## Requirements

- Python 3.12
- A `.venv` with dependencies installed (see `requirements.txt`)
- `.env` containing:
  - `QUBRID_BASE_URL`
  - `QUBRID_API_KEY`

## Run

```bash
python -m ai_product_manager.main "New social app for pet owners"
```

## Notes

- The runtime uses only standard Python networking (`urllib.request`) for Qubrid REST calls.
- The model prompt layer enforces valid JSON responses and alternates conversation roles to satisfy Qubrid API constraints.
- Tool outputs are appended as `assistant` messages so the follow-up prompt remains valid.
