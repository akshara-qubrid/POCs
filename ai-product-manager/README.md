# AI Product Manager POC

A production-grade proof of concept for AI-driven product management workflows. This system demonstrates a sophisticated multi-agent orchestration architecture that decomposes product planning into specialized domain agents (business, engineering, product management) and synthesizes their outputs into comprehensive Product Requirements Documents (PRDs).

## System Overview

The AI Product Manager operates as a hierarchical orchestration pipeline:

1. **Business Analysis Phase**: A business-focused agent analyzes market opportunity, competitive positioning, target personas, and monetization strategies
2. **Technical Assessment Phase**: An engineering-focused agent evaluates technical feasibility, proposes architectures, estimates complexity, and identifies technical risks
3. **PRD Synthesis Phase**: A product management agent orchestrates both analyses and synthesizes findings into a structured, actionable PRD

All agents operate with isolated state to prevent conversation history contamination while having access to shared tools and persistent memory.

## Key Features

- **Multi-Agent Orchestration**: Three specialized agents (`BusinessAgent`, `EngineerAgent`, `PMAgent`) operate independently with clean separation of concerns
- **Isolated State Management**: Each agent receives a fresh state instance (`memory_path=":memory:"`) ensuring no cross-agent conversation pollution while maintaining tool access
- **Live LLM Integration**: Direct Qubrid REST API integration for model inference with automatic role alternation enforcement
- **Structured JSON Output**: All agents produce validated JSON responses enabling programmatic downstream consumption
- **Tool-Driven Workflows**: Agents can request tool execution (market analysis, technical assessment, competitive analysis, roadmap planning) and receive results before final output
- **Persistent Memory**: PRDs and analyses are persisted to `ai_product_manager_memory.json` for audit trails and historical analysis
- **Dual Interface**: CLI and FastAPI server interfaces for flexible integration patterns

## Architecture Components

### Core Modules

#### [ai_product_manager/main.py](ai_product_manager/main.py)
**Entry point and orchestration layer**

- **CLI Mode**: Accepts product idea as command-line argument, executes full pipeline, outputs final PRD
- **Server Mode**: FastAPI application exposing `/` (HTML frontend), `/run` (POST endpoint), `/memory` (GET endpoint)
- **Pipeline Orchestration**: Creates SharedState, registers tools, instantiates agents in proper sequence
- **Error Handling**: Robust exception handling with debug output for troubleshooting

Usage:
```bash
# CLI execution
python -m ai_product_manager.main "Your product idea"

# Server execution
uvicorn ai_product_manager.main:app --reload --port 8001

# Server endpoints
POST /run     → {"idea": "..."}     → PRD JSON response
GET  /memory  →                     → Array of persisted PRDs
GET  /        →                     → HTML frontend
```

#### [ai_product_manager/agents.py](ai_product_manager/agents.py)
**Agent implementations with role-specific logic**

**BusinessAgent** (`analyze_market` method)
- Creates isolated SharedState with fresh conversation history
- Uses AgentExecutor with specialized system prompt emphasizing market opportunity analysis
- Instructs model to use market_opportunity or competitive_analysis tools if beneficial
- Model: `mistralai/Mistral-7B-Instruct-v0.3`, max_tokens=1200
- Expected output fields: `market_summary`, `monetization_strategy`, `user_personas` (array), `competitive_considerations`, `opportunity_score` (0-10)

**EngineerAgent** (`assess_tech` method)
- Creates isolated SharedState with engineering-focused system prompt
- Evaluates technical feasibility, architectural patterns, complexity estimation
- Suggests using technical_assessment tool for deeper analysis
- Model: `mistralai/Mistral-7B-Instruct-v0.3`, max_tokens=1200
- Expected output fields: `feasibility` (high/medium/low), `architecture_recommendation`, `complexity_estimate`, `risks` (array), `suggested_stack` (array)

**PMAgent** (`build_prd` method)
- Orchestrates BusinessAgent and EngineerAgent execution sequentially
- Receives both analysis outputs and synthesizes into comprehensive PRD
- Uses roadmap_planner tool for milestone and user story generation
- Model: `mistralai/Mistral-7B-Instruct-v0.3`, max_tokens=2048
- Expected output fields: `summary`, `user_stories` (array), `technical_recommendations`, `business_recommendations`, `mvp_roadmap` (array), `risks` (array)
- Persists final PRD to shared state memory

#### [ai_product_manager/agent_executor.py](ai_product_manager/agent_executor.py)
**Generic executor for JSON-based agent workflows with tool looping**

**Architecture**:
- Implements strict state machine for conversation flow
- Enforces Qubrid API requirement: alternating user/assistant message roles
- Supports automatic tool invocation loops (up to 8 iterations)

**Message Building** (`_build_messages` method):
1. Constructs system message with agent name, description, tool listing
2. Filters conversation history to last 20 messages (prevents token overflow)
3. Removes consecutive same-role messages (maintains alternation)
4. Appends user instruction, ensuring final message is user role
5. Returns Qubrid-compatible messages array

**Execution Loop** (`run` method):
1. Iterates up to MAX_ITERATIONS (8) times
2. On each iteration:
   - Builds properly formatted messages via `_build_messages`
   - Calls `chat_completion` via LLM client
   - Extracts response text
   - Parses JSON using `extract_json` utility
   - If contains `"tool"` and `"input"` keys: invokes tool via `state.run_tool()`, appends result as assistant message, continues
   - If contains `"final"` key: returns the final output
   - If is any dict: returns as-is
3. Raises RuntimeError if max iterations exceeded without final response

**Tool Invocation Pattern**:
- Agent returns `{"tool": "market_opportunity", "input": "B2B SaaS for finance"}`
- Executor calls `state.run_tool(tool_name, input_str)`
- Tool result appended to history as assistant message: `"market_opportunity output: {...}"`
- Executor continues with instruction to produce final JSON
- This enables multi-step reasoning with external computation

#### [ai_product_manager/state.py](ai_product_manager/state.py)
**Shared state management with memory persistence and tool registry**

**SharedState Dataclass Fields**:
- `memory_path` (str): JSON file path for persistence; use `":memory:"` for transient state
- `history` (List[Dict]): Conversation history with role, content, metadata
- `tools` (Dict[str, Tool]): Registered tool functions keyed by name
- `memory_store` (List[Dict]): Persistent memory records
- `tool_log` (List[Dict]): Audit trail of tool invocations

**Core Methods**:
- `add_message(role, content, metadata)`: Appends to conversation history
- `register_tool(tool)`: Registers Tool object with name-based lookup
- `get_tool_descriptions()`: Returns formatted list of available tools for model prompts
- `run_tool(tool_name, tool_input)`: Executes registered tool, logs execution, appends result as assistant message
- `_normalize_tool_key(name)` & `_find_tool_key(requested)`: Fuzzy tool name matching (handles variations like "swot" → "competitive_analysis")
- `add_memory(record)`: Persists record to memory store and saves to disk
- `save_memory()`: Writes memory_store to JSON file (respects `:memory:` transient mode)
- `load_memory()`: Loads persisted memories from JSON
- `query_memory(query_text)`: Text-based search across memory store

**Initialization** (`__post_init__`):
- Automatically loads memory from disk if path exists
- Enables instant access to historical analyses

#### [ai_product_manager/llm_client.py](ai_product_manager/llm_client.py)
**Qubrid REST API integration with optional LangSmith tracing**

**Configuration Loading** (`_load_dotenv`):
- Looks for `.env` file at project root
- Parses KEY=VALUE format (skips comments and empty lines)
- Populates `os.environ` with `setdefault` (doesn't override existing vars)

**Qubrid Configuration** (`_get_config`):
- Reads `QUBRID_BASE_URL` and `QUBRID_API_KEY` from environment
- Raises RuntimeError if not found (explicit failure vs. silent errors)
- Removes trailing slash from base URL

**LangSmith Integration** (optional observability):
- Detects if LangSmith is available (`from langsmith import Client`)
- Checks if tracing enabled (`LANGCHAIN_TRACING_V2=true`)
- Creates and updates LangSmith runs for LLM calls
- Captures request payloads, responses, token usage, errors
- Two-step pattern: create run (open), update run (close) matching LangSmith API

**Chat Completion** (`chat_completion` function):
- Inputs: model, messages (list), max_tokens, temperature, run_name
- Constructs payload: model, messages, max_tokens, temperature, top_p=1, stream=false
- Makes raw HTTP POST to `{base_url}/chat/completions`
- Parses JSON response from Qubrid
- Returns full response dict for downstream parsing
- Token handling: handles both `usage` and `usage_metadata` field variations

**Response Parsing** (`get_response_text` function):
- Navigates response structure: `response["choices"][0]["message"]["content"]`
- Handles missing fields gracefully
- Returns text for JSON extraction

#### [ai_product_manager/tools.py](ai_product_manager/tools.py)
**Tool implementations for market analysis, technical assessment, and planning**

**Tool Execution Pattern** (`_execute_model`):
- All tools use same pattern: prompt → model call → JSON extraction
- Uses `_MODEL` constant (`mistralai/Mistral-7B-Instruct-v0.3`)
- System prompt: "You are a structured business analysis tool. Respond with valid JSON only."
- Temperature: 0.2 (deterministic, less creative)
- max_tokens: 800 by default

**Available Tools**:

1. **market_opportunity(idea)**
   - Analyzes market size, target personas, monetization approaches
   - Output: `market_summary`, `monetization_strategy`, `user_personas`, `opportunity_score`

2. **technical_assessment(idea)**
   - Evaluates feasibility, recommended architecture, complexity
   - Output: `feasibility`, `architecture_recommendation`, `complexity_estimate`, `risks`

3. **competitive_analysis(idea)**
   - Identifies competitors, differentiators, competitive threats
   - Output: `competitors`, `differentiators`, `competitive_risks`

4. **roadmap_planner(idea)**
   - Generates user stories, MVP roadmap, release milestones
   - Output: `user_stories`, `mvp_roadmap`, `release_milestones`

**Tool Registration** (`get_tools`):
- Returns array of Tool dataclass instances
- Each Tool has: name, description (for model prompts), func (callable)

#### [ai_product_manager/utils.py](ai_product_manager/utils.py)
**JSON extraction from noisy LLM responses**

**JSON Extraction** (`extract_json` function):
- Searches for JSON in various formats:
  - Raw JSON object `{...}`
  - Markdown code fences with json language hint `` ```json ... ``` ``
  - Incomplete/corrupted JSON (attempts to repair)
  - Nested JSON structures
- Returns dict; empty dict `{}` if no valid JSON found
- Enables robust handling of LLM outputs that include markdown formatting

## Execution Flow Walkthrough

### Step 1: Initialization
```
python -m ai_product_manager.main "Social app for pet owners"
↓
main() creates SharedState()
↓
register_tool() called 4 times (market_opportunity, technical_assessment, 
competitive_analysis, roadmap_planner)
↓
BusinessAgent, EngineerAgent, PMAgent instantiated with shared state
```

### Step 2: Business Analysis
```
PMAgent.build_prd() calls BusinessAgent.analyze_market()
↓
Creates isolated state: SharedState(memory_path=":memory:")
↓
AgentExecutor instantiated with BusinessAgent system prompt
↓
First iteration:
  - _build_messages() creates: [system, user]
  - LLM returns: {"tool": "market_opportunity", "input": "Social app for pet owners"}
↓
Second iteration:
  - Tool executes: market_opportunity("Social app for pet owners")
  - Result appended to history as assistant message
  - _build_messages() creates: [system, user (modified to request final output)]
  - LLM returns: {"final": {market_summary: "...", ...}}
↓
ExecutionLoop terminates, returns market analysis dict
```

### Step 3: Technical Assessment (parallel execution)
```
Same as Step 2, but with EngineerAgent
↓
EngineerAgent.assess_tech() returns technical analysis dict
```

### Step 4: PRD Synthesis
```
PMAgent.build_prd() receives both analyses
↓
Creates isolated state for PMAgent executor
↓
Builds prompt including both business and technical analyses
↓
LLM may call roadmap_planner tool (similar loop)
↓
Returns final PRD dict
↓
self.shared_state.add_memory({"type": "prd", "idea": ..., "result": ...})
↓
Memory persisted to ai_product_manager_memory.json
```

### Step 5: Output
```
PRD dict returned and printed as formatted JSON
```

## Installation & Setup

```bash
# Clone and navigate
cd ai-product-manager

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
QUBRID_BASE_URL=https://platform.qubrid.com/v1
QUBRID_API_KEY=your_api_key_here
EOF

# Optional: Enable LangSmith tracing
cat >> .env << EOF
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key_here
LANGCHAIN_PROJECT_APM=ai-product-manager
EOF
```

## Usage Examples

### CLI Mode
```bash
# Basic execution
python -m ai_product_manager.main "B2B SaaS for expense management"

# With longer description
python -m ai_product_manager.main "AI-powered customer support platform that handles support tickets using computer vision and NLP"
```

### Server Mode
```bash
# Start server
uvicorn ai_product_manager.main:app --reload --port 8001

# Access frontend
open http://localhost:8001

# Make API request
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{"idea": "Mobile app for yoga instructors"}'

# Retrieve memory
curl http://localhost:8001/memory | jq
```

## Output Structure

Final PRD JSON contains:
```json
{
  "summary": "...",
  "user_stories": [
    "As a [persona], I want [feature] so that [benefit]",
    ...
  ],
  "technical_recommendations": "...",
  "business_recommendations": "...",
  "mvp_roadmap": [
    "Phase 1: Core features",
    "Phase 2: Monetization",
    ...
  ],
  "risks": [
    "Risk 1 with mitigation",
    ...
  ]
}
```

## Memory Persistence

PRDs are automatically saved to `ai_product_manager_memory.json`:
```json
[
  {
    "type": "prd",
    "idea": "Social app for pet owners",
    "result": { ... full PRD object ... }
  },
  ...
]
```

Query historical PRDs:
```python
state = SharedState()
matching = state.query_memory("pet")  # Searches all fields
```

## Design Principles

1. **Agent Isolation**: Each agent operates in transient state (`:memory:`) preventing conversation contamination
2. **Tool-Driven**: Agents request tools for deeper analysis rather than generating all insights inline
3. **Structured Output**: All outputs are JSON, enabling perfect programmatic consumption
4. **Transparent Orchestration**: Visible logging shows which agents run, when tools are called, iteration counts
5. **Minimal Dependencies**: Uses only stdlib (`urllib`, `json`, `pathlib`) + optional LangSmith for tracing
6. **Flexible Integration**: CLI, server, and programmatic APIs for maximum flexibility

## Requirements

- Python 3.12+
- `requests` or standard library urllib (included)
- Optional: `fastapi`, `uvicorn` (for server mode)
- Optional: `langsmith` (for tracing)

See [requirements.txt](requirements.txt) for exact versions.

## Troubleshooting

### "QUBRID_BASE_URL and QUBRID_API_KEY must be set"
- Ensure `.env` file exists in project root with proper credentials
- Check `.env` format: no spaces around `=`

### "Tool '[name]' not registered"
- Verify tool is in `get_tools()` output
- Check for typos in tool name
- Fuzzy matching handles common variations

### "exceeded 8 iterations without final response"
- Model may be stuck in loop requesting tools
- Increase temperature in agent_executor.py
- Check tool output format (must be JSON-serializable)

### LangSmith tracing not working
- Verify `LANGCHAIN_TRACING_V2=true` in .env
- Verify `LANGSMITH_API_KEY` is valid
- Check internet connectivity to api.smith.langchain.com

## Performance Characteristics

- Average execution time: 15-45 seconds (varies with LLM latency)
- Token usage: 2000-5000 tokens per PRD (depends on idea complexity)
- Memory footprint: ~50MB base + ~1MB per stored PRD
- Concurrent requests: Can be parallelized at main.py level (FastAPI handles natively)
