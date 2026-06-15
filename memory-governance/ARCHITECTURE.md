# Memory Governance - ARCHITECTURE

## Overview

The Memory Governance POC models a multi-stage decision pipeline for whether data should be persisted as memory.
It separates the logic into three specialized agents and ensures each stage returns structured JSON.

## Components

### RetentionAgent

- Evaluates whether a candidate item should be stored
- Generates a `retention_score`, `category`, duplicate detection, and reasoning
- Uses a fresh isolated `SharedState` for each call

### RelevanceAgent

- Assesses how useful the item is likely to be in future contexts
- Produces `relevance_score`, `retrieval_priority`, `future_usefulness`, and memory relationships
- Also uses isolated state to avoid conversation history interactions

### MemoryGovernor

- Synthesizes retention and relevance analyses
- Returns a final decision: `store` or `discard`
- When storing, persists the item with metadata and governance output

### SharedState

- Tracks `history`, `tools`, `memory_store`, and `tool_log`
- Provides `register_tool()` and `run_tool()` helpers
- Persists accepted memory records to `memory_governance_memory.json`

### AgentExecutor

- Builds Qubrid conversation payloads with strict user/assistant alternation
- Calls `llm_client.chat_completion()` for live model inference
- Parses JSON responses and handles tool invocation loops

### Tools

- `score_retention`: scores retention and categorization
- `score_relevance`: scores relevance and retrieval priority

## Data flow

1. `main.py` registers tools and creates `MemoryGovernor`.
2. For each item/context, `MemoryGovernor.consider()` runs:
   - `RetentionAgent.evaluate()`
   - `RelevanceAgent.evaluate()`
3. `MemoryGovernor` uses both analyses to decide store/discard.
4. If stored, the item plus metadata is appended to the persistent memory store.

## Design details

- Each sub-agent uses `memory_path=':memory:'` so temporal history does not persist across different analysis passes.
- The final `MemoryGovernor` has access to the shared persistent memory store, allowing the system to accumulate accepted items.
- The architecture is intentionally modular, so new agent roles or governance tools can be added without changing the core executor.
