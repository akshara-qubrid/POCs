# Startup Due Diligence - ARCHITECTURE

## Overview

The Startup Due Diligence POC implements a hierarchical analysis pipeline for evaluating new businesses.
It uses specialist lead roles to generate domain reports, then synthesizes those reports with a top-level investment recommendation.

## Components

### Main pipeline (`main.py`)

- Builds a shared `SharedState` and registers tools.
- Runs `MarketLead`, `ProductLead`, and `FinancialLead` analyses sequentially.
- Sends pre-computed specialist outputs to `InvestmentLead` for final synthesis.

### MarketLead, ProductLead, FinancialLead (`leads.py`)

- `MarketLead` produces TAM and competition assessments.
- `ProductLead` produces product fit and UX assessment.
- `FinancialLead` evaluates revenue model and unit economics.
- These leads currently call helper workers and append summaries to shared state.

### Worker nodes (`workers.py`)

- `tam_worker`: estimates total addressable market
- `competition_worker`: assesses competitive intensity
- `product_assessment_worker`: evaluates product fit and UX risk
- `financial_worker`: assesses revenue model and unit economics

Note: worker functions are designed for live model calls, but currently include fallback heuristics when the response cannot be parsed.

### InvestmentLead (`investment_agent.py`)

- Orchestrates the final report generation.
- Uses `AgentExecutor` to call the model with structured prompt output.
- Produces JSON with market_score, product_score, financial_score, overall_score, risk_assessment, investment_recommendation, report, key_strengths, and key_risks.

### SharedState (`state.py`)

- Tracks conversation history, tool registrations, memory store, and tool logs.
- Persists final due diligence reports to `due_diligence_memory.json`.
- Appends tool and lead summaries as assistant content for downstream synthesis.

### Tools (`tools.py`)

- Structured analysis helpers such as `tam_analysis`, `competition_analysis`, `product_assessment`, `ux_assessment`, `technical_moat`, `revenue_model`, and `unit_economics`.
- Each tool returns JSON and is available for agents to invoke during their workflow.

### LLM client (`llm_client.py`)

- Implements raw Qubrid REST calls via `urllib.request`.
- Loads `QUBRID_BASE_URL` and `QUBRID_API_KEY` from `.env` or environment.
- Sends chat completions with model, messages, max_tokens, temperature, and top_p.

## Data flow

1. `main.py` starts the due diligence pipeline with a startup description.
2. Specialist lead modules run, producing domain-specific findings.
3. Findings are appended to shared state as assistant messages.
4. `InvestmentLead` receives the enriched prompt and synthesizes a final JSON recommendation.
5. The final report is persisted in the memory store.

## Design notes

- The architecture separates specialist analysis from final synthesis to mirror real diligence workflows.
- Tools are available to the top-level agent, enabling deeper analysis where needed.
- The executor enforces clean JSON responses and supports tool invocation loops.
- The project is intended as a flexible POC engine for additional due diligence dimensions.
