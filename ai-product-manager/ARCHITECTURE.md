# AI Product Manager - ARCHITECTURE

## Overview

The AI Product Manager POC implements a layered agent architecture for product discovery and planning.
The system splits work across:

- `BusinessAgent`: market opportunity, monetization, personas, competitive analysis
- `EngineerAgent`: technical feasibility, architecture, complexity, risk
- `PMAgent`: synthesises downstream outputs into a final PRD

All agents use a shared `SharedState` for history, tool registration, and memory persistence.

## Core components

### SharedState

Located in `ai_product_manager/state.py`.

Responsibilities:

- store `history` of conversation turns
- register and lookup tools
- append tool execution results to history as `assistant` responses
- save/load structured memories to `ai_product_manager_memory.json`
- support memory queries via simple text filtering

### AgentExecutor

Located in `ai_product_manager/agent_executor.py`.

Responsibilities:

- build Qubrid-compatible `messages` with system, user, and assistant turns
- enforce alternate user/assistant role ordering
- make live model calls via `llm_client.chat_completion`
- parse model output with `utils.extract_json`
- handle tool request loops until a final JSON result is returned

### Tools

Located in `ai_product_manager/tools.py`.

This module exposes tool functions that agents can call during a workflow:

- `market_opportunity`
- `technical_assessment`
- `competitive_analysis`
- `roadmap_planner`

Each tool is a small structured LLM workflow that returns JSON via direct Qubrid calls.

### LLM Client

Located in `ai_product_manager/llm_client.py`.

Responsibilities:

- load `.env` if available
- read `QUBRID_BASE_URL` and `QUBRID_API_KEY`
- send raw JSON POSTs to `https://platform.qubrid.com/v1/chat/completions`
- return the parsed response dictionary

### JSON extraction

Located in `ai_product_manager/utils.py`.

Responsibilities:

- extract valid JSON from noisy LLM text responses
- support robust parsing of assistant outputs

## Execution flow

1. `main.py` creates a `SharedState` and registers available tools.
2. `BusinessAgent` and `EngineerAgent` are constructed with the same shared state.
3. `PMAgent.build_prd()` requests business and technical analyses, then synthesises them into a PRD.
4. `AgentExecutor.run()` builds the conversation history, invokes the model, and parses tool requests.
5. If the model returns a tool request, the executor calls `state.run_tool()`, appends the tool result as an `assistant` message, and continues.
6. When the model returns final structured JSON, the workflow completes and the result is persisted as memory.

## Design notes

- The system is intentionally lightweight and package-based: each POC is isolated in its own folder.
- Role alternation is enforced to avoid Qubrid API `invalid role alternation` errors.
- Tool outputs are inserted as assistant messages rather than a custom `tool` role.
- The project is built for experimentation and rapid iteration, not production-grade orchestration.
