# Memory Governance POC

A standalone proof of concept for a memory governance workflow.
This project demonstrates how retention, relevance, and governance decisions can be modelled as separate agent roles and combined into a single store/discard policy.

## What this project demonstrates

- Memory governance decomposition into Retention, Relevance, and Governor agents
- Isolated state per sub-agent to avoid history pollution
- Tool-driven evaluation using live Qubrid REST model calls
- Persistent memory storage only when an item is accepted
- JSON-only structured output from every agent stage

## Project layout

- `memory_governance/main.py`: demo entrypoint and batch runner
- `memory_governance/agents.py`: RetentionAgent, RelevanceAgent, MemoryGovernor orchestration
- `memory_governance/agent_executor.py`: generic executor for JSON + tool workflows
- `memory_governance/llm_client.py`: raw Qubrid REST chat client
- `memory_governance/state.py`: shared state, tool registry, history, memory persistence
- `memory_governance/tools.py`: retention/relevance scoring tools
- `memory_governance/utils.py`: JSON extraction utilities
- `memory_governance_memory.json`: persisted accepted memories

## Requirements

- Python 3.12
- `.env` with `QUBRID_BASE_URL` and `QUBRID_API_KEY`

## Run

```bash
python -m memory_governance.main
```

For a single item decision:

```bash
python -m memory_governance.main "Item text here" "Context text here"
```

## Notes

- The governor only persists memory items when the final decision is `store`.
- Sub-agents use `memory_path=':memory:'` to maintain transient state during their evaluation.
- The workflow is designed to be transparent and auditable through printed debug traces.
