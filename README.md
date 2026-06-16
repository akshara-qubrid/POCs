# Qubrid AI POCs

A collection of three agentic AI proof-of-concept systems built on the [Qubrid](https://platform.qubrid.com) LLM platform. All three share the same architectural DNA — isolated `SharedState`, an `AgentExecutor` with strict role-alternation enforcement, JSON-only LLM contracts, and tool-call loops — while solving distinct real-world problems.

Tracing, observability, and token-consumption monitoring are provided by **LangSmith** across all three systems.

---

## Table of Contents

1. [Workspace Structure](#workspace-structure)
2. [Shared Architecture](#shared-architecture)
3. [Project 1 — AI Product Manager](#project-1--ai-product-manager)
4. [Project 2 — Memory Governance](#project-2--memory-governance)
5. [Project 3 — Startup Due Diligence](#project-3--startup-due-diligence)
6. [LangSmith Tracing & Observability](#langsmith-tracing--observability)
7. [Static Frontends](#static-frontends)
8. [Setup & Environment](#setup--environment)
9. [Running the Projects](#running-the-projects)
10. [Running All Tests](#running-all-tests)

---

## Workspace Structure

```
POCs - Qubrid/
├── .env                          # Shared API keys (Qubrid + LangSmith)
├── .gitignore
├── test_all.py                   # Smoke-test runner for all three POCs
│
├── ai-product-manager/
│   ├── frontend/
│   │   └── index.html            # Static frontend UI
│   ├── ai_product_manager/
│   │   ├── agents.py             # BusinessAgent, EngineerAgent, PMAgent
│   │   ├── agent_executor.py     # LLM loop + tool dispatch
│   │   ├── llm_client.py         # Qubrid REST client + LangSmith tracing
│   │   ├── main.py               # CLI entry point + FastAPI app
│   │   ├── memory.py             # SimpleMemory (JSON persistence)
│   │   ├── state.py              # SharedState dataclass
│   │   ├── tools.py              # market_opportunity, technical_assessment, …
│   │   └── utils.py              # JSON extraction helpers
│   └── requirements.txt
│
├── memory-governance/
│   ├── frontend/
│   │   └── index.html            # Static frontend UI
│   ├── memory_governance/
│   │   ├── agents.py             # RetentionAgent, RelevanceAgent, MemoryGovernor
│   │   ├── agent_executor.py     # LLM loop + tool dispatch
│   │   ├── llm_client.py         # Qubrid REST client + LangSmith tracing
│   │   ├── main.py               # CLI entry point + FastAPI app
│   │   ├── state.py              # SharedState dataclass
│   │   ├── tools.py              # score_retention, score_relevance
│   │   └── utils.py              # JSON extraction helpers
│   └── requirements.txt
│
└── startup-due-diligence/
    ├── frontend/
    │   └── index.html            # Static frontend UI
    ├── due_diligence/
    │   ├── agent_executor.py     # LLM loop + tool dispatch
    │   ├── investment_agent.py   # InvestmentLead orchestrator
    │   ├── leads.py              # MarketLead, ProductLead, FinancialLead
    │   ├── llm_client.py         # Qubrid REST client + LangSmith tracing
    │   ├── main.py               # CLI entry point + FastAPI app
    │   ├── state.py              # SharedState dataclass
    │   ├── tools.py              # tam_analysis, competition_analysis, …
    │   ├── utils.py              # JSON extraction helpers
    │   └── workers.py            # Domain-specific LLM worker functions
    └── requirements.txt
```

---

## Shared Architecture

All three projects follow the same layered design:

```
main.py
  └── Agents (specialist roles)
        └── AgentExecutor
              ├── llm_client.chat_completion()  →  Qubrid API
              │         └── LangSmith trace wrapper
              ├── utils.extract_json()
              └── SharedState
                    ├── history (alternating user/assistant)
                    ├── tools registry
                    ├── tool_log
                    └── memory_store → persisted JSON file
```

### Key design decisions

| Concern | Decision |
|---|---|
| LLM transport | stdlib `urllib` — zero third-party HTTP deps |
| Role alternation | Enforced in `AgentExecutor._build_messages()` |
| Tool protocol | JSON `{"tool": "name", "input": "..."}` / `{"final": ...}` |
| Memory | Simple JSON files; sub-agents use `":memory:"` |
| Tracing | LangSmith via `langsmith` SDK wrapping every `chat_completion` call |

---

## Project 1 — AI Product Manager

**Path:** `ai-product-manager/`  
**Purpose:** Transforms a raw product idea into a structured Product Requirements Document (PRD) using a three-agent pipeline.

### Agents

| Agent | Model | Role |
|---|---|---|
| `BusinessAgent` | `mistralai/Mistral-7B-Instruct-v0.3` | Market opportunity, monetization strategy, user personas, competitive landscape |
| `EngineerAgent` | `mistralai/Mistral-7B-Instruct-v0.3` | Technical feasibility, architecture recommendation, complexity estimate, risk list |
| `PMAgent` | `mistralai/Mistral-7B-Instruct-v0.3` | Synthesises both analyses into a full PRD with MVP roadmap and user stories |

### Tools

| Tool | Description |
|---|---|
| `market_opportunity` | Analyse market opportunity, personas, monetization |
| `technical_assessment` | Assess technical feasibility and architecture |
| `competitive_analysis` | Identify competitors, differentiators, and risks |
| `roadmap_planner` | Generate MVP roadmap, user stories, and milestones |

### Data Flow

```
idea (string)
  → BusinessAgent.analyze_market()   →  business_analysis (JSON)
  → EngineerAgent.assess_tech()      →  technical_analysis (JSON)
  → PMAgent.build_prd()              →  final PRD (JSON)
        └── persisted to ai_product_manager_memory.json
```

### PRD Output Fields

```json
{
  "summary": "...",
  "user_stories": ["..."],
  "technical_recommendations": "...",
  "business_recommendations": "...",
  "mvp_roadmap": ["milestone 1", "milestone 2"],
  "risks": ["..."]
}
```

### CLI Usage

```bash
cd ai-product-manager
python -m ai_product_manager.main "An AI-powered personal finance tracker for Gen Z"
```

### API Server

```bash
cd ai-product-manager
uvicorn ai_product_manager.main:app --reload --port 8001
# POST /run   body: {"idea": "your product idea"}
# GET  /memory
```

---

## Project 2 — Memory Governance

**Path:** `memory-governance/`  
**Purpose:** A three-stage governance pipeline that decides whether information should be committed to long-term memory. Models a policy-enforcement pattern for agentic systems.

### Agents

| Agent | Model | Role |
|---|---|---|
| `RetentionAgent` | `mistralai/Mistral-7B-Instruct-v0.3` | Scores retention value, assigns a category, detects duplicates |
| `RelevanceAgent` | `openai/gpt-oss-120b` (via `score_relevance` tool) | Scores future usefulness and retrieval priority |
| `MemoryGovernor` | `mistralai/Mistral-7B-Instruct-v0.3` | Arbitrates sub-agent outputs; issues final `store` / `discard` decision |

### Tools

| Tool | Model | Description |
|---|---|---|
| `score_retention` | `mistralai/Mistral-7B-Instruct-v0.3` | Score and categorise retention value |
| `score_relevance` | `openai/gpt-oss-120b` | Evaluate relevance to a given context |

### Data Flow

```
(item, context)
  → RetentionAgent.evaluate(item)         →  retention analysis (JSON)
  → RelevanceAgent.evaluate(item, ctx)    →  relevance analysis (JSON)
  → MemoryGovernor.arbitrate()            →  governance decision (JSON)
        └── if decision == "store":
              persisted to memory_governance_memory.json
```

### Governance Decision Output

```json
{
  "decision": "store | discard",
  "importance_score": 0.85,
  "retention_category": "user_preference",
  "retrieval_priority": "high",
  "explanation": "..."
}
```

### Sub-agent Isolation

Each sub-agent call creates a fresh `SharedState(memory_path=":memory:")` so conversation histories never bleed across calls or break the alternating-role constraint.

### CLI Usage

```bash
cd memory-governance

# Batch demo (4 built-in items)
python -m memory_governance.main

# Single item
python -m memory_governance.main "User prefers dark mode" "UI personalisation"
```

### API Server

```bash
cd memory-governance
uvicorn memory_governance.main:app --reload --port 8002
# POST /consider   body: {"item": "...", "context": "..."}
# GET  /memory
```

---

## Project 3 — Startup Due Diligence

**Path:** `startup-due-diligence/`  
**Purpose:** A hierarchical analysis pipeline that evaluates a startup description and produces a structured investment recommendation. Mirrors a real VC due-diligence workflow.

### Agents

| Agent | Model | Role |
|---|---|---|
| `MarketLead` | `mistralai/Mistral-7B-Instruct-v0.3` (workers) | TAM estimation and competitive landscape |
| `ProductLead` | `mistralai/Mistral-7B-Instruct-v0.3` (workers) | Product fit and UX assessment |
| `FinancialLead` | `deepseek-ai/deepseek-r1-distill-llama-70b` (workers) | Revenue model and unit economics |
| `InvestmentLead` | `deepseek-ai/deepseek-r1-distill-llama-70b` | Synthesises all specialist analyses into a final investment memo |

### Tools (available to InvestmentLead)

| Tool | Description |
|---|---|
| `tam_analysis` | TAM estimate with confidence and rationale |
| `competition_analysis` | Competitive landscape and key players |
| `industry_trends` | Trend summary, momentum, and risks |
| `product_assessment` | Product fit, strengths, and weaknesses |
| `ux_assessment` | UX score, issues, and recommendations |
| `technical_moat` | Moat strength, drivers, and risks |
| `revenue_model` | Revenue model score and durability |
| `unit_economics` | Unit economics rating and margin risk |
| `funding_risk` | Funding risk score and mitigation |

### Data Flow

```
startup description (string)
  → MarketLead.analyze()         →  {tam, competition}
  → ProductLead.analyze()        →  {product}
  → FinancialLead.analyze()      →  {financial}
  → InvestmentLead.evaluate()    →  final investment memo (JSON)
        └── persisted to due_diligence_memory.json
```

### Investment Report Output

```json
{
  "market_score": 8,
  "product_score": 7,
  "financial_score": 6,
  "overall_score": 7,
  "risk_assessment": "...",
  "investment_recommendation": "invest | pass | conditional",
  "report": "Full investment memo...",
  "key_strengths": ["..."],
  "key_risks": ["..."]
}
```

### CLI Usage

```bash
cd startup-due-diligence
python -m due_diligence.main "B2B SaaS for automated AP/AR reconciliation targeting mid-market CFOs"
```

### API Server

```bash
cd startup-due-diligence
uvicorn due_diligence.main:app --reload --port 8003
# POST /evaluate   body: {"startup": "your startup description"}
# GET  /memory
```

---

## LangSmith Tracing & Observability

Every `chat_completion` call in all three projects is wrapped with a LangSmith run trace. This gives you:

- **Full trace trees** — see every LLM call, tool invocation, and agent step in LangSmith UI
- **Token consumption** — prompt tokens, completion tokens, and total tokens per call and per run
- **Latency breakdown** — wall-clock time per agent, per tool, per iteration
- **Input/output inspection** — full message payloads and model responses stored in LangSmith

### Setup

1. Sign up at [smith.langchain.com](https://smith.langchain.com) and create a project for each POC.
2. Generate an API key from Settings → API Keys.
3. Add the following to your `.env` file:

```env
# Qubrid
QUBRID_BASE_URL=https://platform.qubrid.com/v1
QUBRID_API_KEY=your_qubrid_api_key

# LangSmith
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# LangSmith project names (one per POC)
LANGCHAIN_PROJECT_APM=ai-product-manager
LANGCHAIN_PROJECT_MG=memory-governance
LANGCHAIN_PROJECT_DD=startup-due-diligence
```

4. Install the LangSmith SDK (already added to each `requirements.txt`):

```bash
pip install langsmith==0.1.147
```

### What Gets Traced

Each trace captures:

| Field | Description |
|---|---|
| `run_name` | Agent name + iteration number |
| `inputs` | Full `messages` array sent to the model |
| `outputs` | Full model response dict |
| `metadata.model` | Model identifier |
| `metadata.max_tokens` | Token budget for the call |
| `metadata.project` | LangSmith project name |
| `usage_metadata` | `prompt_tokens`, `completion_tokens`, `total_tokens` |

### Viewing Traces

Open [smith.langchain.com](https://smith.langchain.com), select your project, and navigate to **Runs**. Each agent execution appears as a parent run containing child runs for every LLM call and tool invocation.

---

## Static Frontends

Each project ships a zero-dependency static HTML frontend at `<project>/frontend/index.html`. Open the file directly in a browser — no build step required.

The frontends communicate with the FastAPI servers defined in each project's `main.py`. Start the relevant API server first, then open the HTML file.

| Project | API Port | Frontend |
|---|---|---|
| AI Product Manager | 8001 | `ai-product-manager/frontend/index.html` |
| Memory Governance | 8002 | `memory-governance/frontend/index.html` |
| Startup Due Diligence | 8003 | `startup-due-diligence/frontend/index.html` |

---

## Setup & Environment

### Prerequisites

- Python 3.11+
- pip
- A Qubrid API key
- A LangSmith API key

### Install dependencies

```bash
# From the root — install for all three projects
pip install -r ai-product-manager/requirements.txt
pip install -r memory-governance/requirements.txt
pip install -r startup-due-diligence/requirements.txt
```

### Configure `.env`

Copy or edit `.env` in the workspace root:

```env
QUBRID_BASE_URL=https://platform.qubrid.com/v1
QUBRID_API_KEY=your_qubrid_api_key

LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT_APM=ai-product-manager
LANGCHAIN_PROJECT_MG=memory-governance
LANGCHAIN_PROJECT_DD=startup-due-diligence
```

---

## Running the Projects

### AI Product Manager

```bash
# CLI
cd ai-product-manager
python -m ai_product_manager.main "Idea here"

# API server
uvicorn ai_product_manager.main:app --reload --port 8001
```

### Memory Governance

```bash
# CLI — batch demo
cd memory-governance
python -m memory_governance.main

# CLI — single item
python -m memory_governance.main "item text" "context text"

# API server
uvicorn memory_governance.main:app --reload --port 8002
```

### Startup Due Diligence

```bash
# CLI
cd startup-due-diligence
python -m due_diligence.main "Startup description here"

# API server
uvicorn due_diligence.main:app --reload --port 8003
```

---

## Running All Tests

```bash
# From the workspace root
python test_all.py              # run all three smoke tests
python test_all.py apm          # AI Product Manager only
python test_all.py memory       # Memory Governance only
python test_all.py diligence    # Startup Due Diligence only
```

Each test makes a live API call and asserts the pipeline returns a valid dict result.
