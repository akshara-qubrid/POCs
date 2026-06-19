# AI Product Manager - Architecture

## System Overview

The AI Product Manager implements a **hierarchical multi-agent orchestration architecture** designed to decompose complex product planning into specialized domain-specific analyses and synthesize results into actionable requirements.

### Core Design Philosophy

The system operates on three key principles:

1. **Agent Specialization**: Each agent has a narrowly-defined responsibility (business, engineering, product management)
2. **Isolation with Shared Tools**: Agents use isolated conversation histories but access shared tool implementations
3. **Deterministic Structured Output**: All outputs are validated JSON, enabling perfect programmatic consumption

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│  (Entry Point + Orchestration)                              │
│  - Creates SharedState                                      │
│  - Registers Tools                                          │
│  - Instantiates Agents                                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌──────────┐
   │Business │   │Engineer │   │ PM Agent │
   │ Agent   │   │ Agent   │   │(Final)   │
   └────┬────┘   └────┬────┘   └─────┬────┘
        │             │              │
        │ (Isolated)  │ (Isolated)  │ (Isolated)
        │ State       │ State       │ State
        │             │             │
   ┌────▼────────────▼─────────────▼────┐
   │      AgentExecutor (Generic)       │
   │  - Message Building                │
   │  - LLM Invocation                  │
   │  - JSON Parsing                    │
   │  - Tool Loop (max 8 iterations)    │
   └────┬─────────────────────────────┬─┘
        │                             │
        ▼                             ▼
   ┌─────────────┐  ┌────────────────────────┐
   │ LLM Client  │  │ State.run_tool()       │
   │ (Qubrid)    │  │ - Finds tool by name  │
   │             │  │ - Executes func       │
   │ Via HTTP    │  │ - Logs execution      │
   └─────────────┘  │ - Appends result      │
                    └────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │ Tool Functions │
                    │ - market_      │
                    │   opportunity  │
                    │ - technical_   │
                    │   assessment   │
                    │ - competitive_ │
                    │   analysis     │
                    │ - roadmap_     │
                    │   planner      │
                    └────────────────┘
```

## Components

### 1. SharedState (`state.py`)

**Responsibility**: Centralized state management with memory persistence and tool registry

**Data Model**:
```python
@dataclass
class SharedState:
    memory_path: str                              # File path for persistence
    history: List[Dict[str, Any]]                 # Conversation turns
    tools: Dict[str, Tool]                        # Registered functions
    memory_store: List[Dict[str, Any]]            # Persisted records
    tool_log: List[Dict[str, Any]]                # Audit trail
```

**Key Operations**:

1. **Tool Registration**
   ```python
   tool = Tool(
       name="market_opportunity",
       description="Analyze market opportunity and personas",
       func=market_opportunity_impl
   )
   state.register_tool(tool)
   ```

2. **Tool Lookup and Execution**
   - `_normalize_tool_key()`: Converts tool names to canonical form (lowercase, underscore-separated)
   - `_find_tool_key()`: Implements fuzzy matching (handles "SWOT" → "competitive_analysis")
   - `run_tool(name, input)`: Executes tool, logs call, appends result to history

3. **Memory Persistence**
   - `add_memory(record)`: Appends to store and syncs to disk
   - `save_memory()`: Writes memory_store as JSON (skipped if `memory_path=":memory:"`)
   - `load_memory()`: Loads from disk on initialization
   - `query_memory(text)`: Full-text search across memory store

4. **Conversation History**
   - `add_message(role, content, metadata)`: Appends turn to history
   - History filtered to last 20 messages during message building (token optimization)

**Isolation Pattern**:
```python
# Each agent gets isolated state
state = SharedState(memory_path=":memory:")  # Transient state
for tool in all_tools:
    state.register_tool(tool)                 # Share tools
# No cross-contamination of conversation history
```

### 2. AgentExecutor (`agent_executor.py`)

**Responsibility**: Generic executor for JSON-based workflows with automatic tool looping

**Initialization**:
```python
executor = AgentExecutor(
    name="BusinessAgent",
    description="You are a business analyst. Evaluate market opportunity...",
    state=state,                              # Uses shared/isolated state
    model="mistralai/Mistral-7B-Instruct-v0.3",
    max_tokens=1200
)
```

**Execution State Machine**:

```
[Start: instruction]
    ↓
[Iteration 1..8]
    │
    ├─→ _build_messages(instruction)
    │   ├─→ Create system message
    │   ├─→ Filter history (last 20, no consecutive same-role)
    │   ├─→ Ensure alternating user/assistant
    │   └─→ Return messages array
    │
    ├─→ chat_completion(model, messages, ...)
    │   └─→ HTTP POST to Qubrid
    │
    ├─→ extract_json(response_text)
    │   └─→ Parse JSON from response
    │
    ├─→ Check response type:
    │   │
    │   ├─ If has "tool" + "input" keys:
    │   │  ├─→ state.run_tool(tool_name, input)
    │   │  ├─→ Append result as assistant message
    │   │  ├─→ Set instruction to "Tool returned: ... Continue with final output"
    │   │  └─→ [Loop to next iteration]
    │   │
    │   ├─ If has "final" key:
    │   │  └─→ Return action["final"]  [SUCCESS]
    │   │
    │   └─ If is dict:
    │      └─→ Return action  [SUCCESS]
    │
    └─→ If no valid response structure:
        └─→ Raise ValueError  [ERROR]

If iterations >= 8:
    └─→ Raise RuntimeError  [TIMEOUT]
```

**Message Building Deep Dive** (`_build_messages`):

```python
def _build_messages(self, instruction: str) -> List[Dict[str, str]]:
    # 1. System message with context
    system = {
        "role": "system",
        "content": f"You are {self.name}. {self.description}\n"
                   f"Available tools:\n{self.state.get_tool_descriptions()}"
    }
    
    # 2. Process history (alternating role enforcement)
    messages = [system]
    last_role = None
    for entry in self.state.history[-20:]:  # Last 20 to avoid token overflow
        role = entry["role"]
        if role == last_role:
            continue  # Skip consecutive same-role (maintains alternation)
        messages.append({"role": role, "content": entry["content"]})
        last_role = role
    
    # 3. Append instruction (must be user role for API compliance)
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = instruction  # Replace last user message
    else:
        messages.append({"role": "user", "content": instruction})
    
    return messages
```

**Tool Invocation Loop**:

When model returns `{"tool": "market_opportunity", "input": "..."}`:

1. `state.run_tool("market_opportunity", input)` is called
2. Tool function executes and returns result dict
3. Result appended to history: `add_message("assistant", f"market_opportunity output: {result}")`
4. New instruction generated: `"Tool 'market_opportunity' returned: {...}. Continue..."`
5. Loop continues with next iteration
6. Model now sees tool output in conversation and can reference it
7. On next iteration, model returns `{"final": {...}}` with synthesis

### 3. LLM Client (`llm_client.py`)

**Responsibility**: Qubrid REST API integration with optional observability

**Configuration Loading**:
```python
def _load_dotenv():
    # Looks for .env at project root
    # Parses KEY=VALUE format
    # Populates os.environ (non-overwriting)
    
    # Example .env:
    # QUBRID_BASE_URL=https://platform.qubrid.com/v1
    # QUBRID_API_KEY=pk_test_123456789
    # LANGCHAIN_TRACING_V2=true
    # LANGCHAIN_API_KEY=ls_...
```

**Chat Completion Flow**:

```python
def chat_completion(model, messages, max_tokens, temperature, run_name):
    config = _get_config()  # Reads QUBRID_BASE_URL, QUBRID_API_KEY
    url = f"{config['base_url']}/chat/completions"
    
    payload = {
        "model": model,                    # e.g., "mistralai/Mistral-7B-Instruct-v0.3"
        "messages": messages,              # [{"role": "system", ...}, ...]
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 1,
        "stream": False
    }
    
    # Optional: Create LangSmith trace
    start_time = datetime.datetime.now()
    run_id = uuid.uuid4()
    
    # Make HTTP POST request
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # Handle errors
        pass
    
    # Optional: Update LangSmith trace with results
    _trace(client, run_id, run_name, messages, result, ...)
    
    return result
```

**Response Parsing**:
```python
def get_response_text(response):
    # Navigate: response["choices"][0]["message"]["content"]
    # Handles missing fields gracefully
    return text
```

**Token Usage Tracking**:
- Handles both `usage` and `usage_metadata` field names (API variation handling)
- Logged to LangSmith if tracing enabled
- Useful for cost monitoring and optimization

### 4. Agent Layer (`agents.py`)

**Responsibility**: Domain-specific agent logic with specialized prompts

#### BusinessAgent

```python
class BusinessAgent:
    def __init__(self, shared_state):
        self.shared_state = shared_state
    
    def analyze_market(self, idea: str) -> dict:
        # 1. Create isolated state
        state = SharedState(memory_path=":memory:")
        for tool in all_tools:
            state.register_tool(tool)
        
        # 2. Create executor with business-focused prompt
        executor = AgentExecutor(
            name="BusinessAgent",
            description="You are the business analyst. Evaluate market opportunity...",
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=1200
        )
        
        # 3. Execute with structured prompt
        prompt = f"""
        Analyse the product idea: {idea}
        
        Return JSON with fields:
        - market_summary (string)
        - monetization_strategy (string)
        - user_personas (array of strings)
        - competitive_considerations (string)
        - opportunity_score (0-10 integer)
        
        You may call market_opportunity or competitive_analysis tools first if helpful.
        """
        
        # 4. Run executor (may loop with tool calls)
        result = executor.run(prompt)
        return result
```

**Execution Sequence**:
1. Isolated state created (fresh history, shared tools)
2. AgentExecutor loops up to 8 times
3. First iteration: Model may call `market_opportunity` tool
4. Tool result appended to history
5. Second iteration: Model synthesizes and returns `{"final": {...}}`
6. Result returned to caller

#### EngineerAgent

Similar pattern with engineering-focused prompt and technical assessment tools.

#### PMAgent

```python
class PMAgent:
    def build_prd(self, idea: str) -> dict:
        # 1. Get business analysis
        business_analysis = self.business.analyze_market(idea)
        
        # 2. Get technical analysis
        technical_analysis = self.engineer.assess_tech(idea)
        
        # 3. Create isolated state for synthesis
        state = SharedState(memory_path=":memory:")
        executor = AgentExecutor(
            name="PMAgent",
            description="You are the product manager. Synthesise analyses into PRD...",
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=2048  # Larger token budget for final output
        )
        
        # 4. Build synthesis prompt with both analyses
        prompt = f"""
        Build a complete PRD for the product idea.
        
        Business analysis: {business_analysis}
        Technical analysis: {technical_analysis}
        
        Return JSON with fields:
        - summary
        - user_stories (array)
        - technical_recommendations
        - business_recommendations
        - mvp_roadmap (array)
        - risks (array)
        """
        
        # 5. Execute
        result = executor.run(prompt)
        
        # 6. Persist to shared state
        self.shared_state.add_memory({
            "type": "prd",
            "idea": idea,
            "result": result
        })
        
        return result
```

### 5. Tools Layer (`tools.py`)

**Responsibility**: Domain-specific tool implementations callable by agents

**Tool Dataclass**:
```python
@dataclass
class Tool:
    name: str                    # "market_opportunity"
    description: str            # Used in model prompts for tool discovery
    func: Callable[[str], Any]  # Actual implementation
```

**Tool Execution Pattern**:

```python
def _execute_model(prompt: str, max_tokens: int = 800) -> Dict:
    # All tools follow same pattern:
    messages = [
        {"role": "system", "content": "You are a structured business analysis tool..."},
        {"role": "user", "content": prompt}
    ]
    response = chat_completion(_MODEL, messages, max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)

def market_opportunity(idea: str) -> Dict[str, Any]:
    prompt = f"""Analyze market opportunity...
    Return JSON with fields: market_summary, monetization_strategy, ...
    idea: {idea}"""
    return _execute_model(prompt)

def get_tools() -> List[Tool]:
    return [
        Tool(name="market_opportunity", description="...", func=market_opportunity),
        Tool(name="technical_assessment", description="...", func=technical_assessment),
        # ... etc
    ]
```

**Tool Availability**:
- Tools become available to agents via `state.get_tool_descriptions()`
- Agents can request tools via `{"tool": "name", "input": "..."}`
- Executor calls `state.run_tool(name, input)` which invokes `Tool.func(input)`

### 6. Utilities (`utils.py`)

**JSON Extraction**:

```python
def extract_json(text: str) -> dict:
    # Handle multiple formats:
    # 1. Raw JSON: {"key": "value"}
    # 2. Markdown: ```json\n{...}\n```
    # 3. Partial/corrupted JSON (repair attempts)
    # 4. Nested JSON
    
    # Returns dict; empty {} if nothing found
    # Robust against LLM formatting variations
```

## Execution Flow Detailed Walkthrough

### Phase 1: Initialization (main.py)

```
Entry: main("Social app for pet owners")
    │
    ├─→ Print header
    │
    ├─→ state = SharedState()  # Loads ai_product_manager_memory.json
    │
    ├─→ for tool in get_tools():
    │       state.register_tool(tool)  # Register 4 tools
    │
    ├─→ business = BusinessAgent(state)
    ├─→ engineer = EngineerAgent(state)
    ├─→ pm = PMAgent(state, business, engineer)
    │
    └─→ prd = pm.build_prd(idea)
```

### Phase 2: Business Analysis

```
PMAgent.build_prd()
    │
    └─→ business.analyze_market("Social app for pet owners")
        │
        ├─→ state = SharedState(memory_path=":memory:")  # Fresh, transient
        ├─→ Register 4 tools
        │
        ├─→ executor = AgentExecutor(
        │       name="BusinessAgent",
        │       model="mistralai/Mistral-7B-Instruct-v0.3",
        │       state=state
        │   )
        │
        └─→ executor.run(prompt)
            │
            ├─→ Iteration 1:
            │   ├─→ _build_messages() → [system, user]
            │   ├─→ chat_completion(model, messages, ...)
            │   │   └─→ HTTP POST to Qubrid
            │   ├─→ Qubrid response: {"tool": "market_opportunity", "input": "..."}
            │   ├─→ extract_json(response)
            │   └─→ Result has "tool" key
            │
            ├─→ Tool invocation:
            │   ├─→ state.run_tool("market_opportunity", input)
            │   ├─→ Tool function: _execute_model(prompt)
            │   │   └─→ Another chat_completion call
            │   ├─→ Result: {"market_size": "...", ...}
            │   └─→ state.add_message("assistant", "market_opportunity output: {...}")
            │
            ├─→ Iteration 2:
            │   ├─→ instruction = "Tool returned: {...}. Continue with final output..."
            │   ├─→ _build_messages(instruction)
            │   │   └─→ [system, user (first iteration), assistant (tool output), user (new)]
            │   ├─→ chat_completion(model, messages, ...)
            │   ├─→ Qubrid response: {"final": {"market_summary": "...", ...}}
            │   └─→ Result has "final" key
            │
            └─→ Return action["final"]  # Done
        
        result = {
            "market_summary": "...",
            "monetization_strategy": "...",
            "user_personas": ["pet owner", "vet", ...],
            "competitive_considerations": "...",
            "opportunity_score": 8
        }
```

### Phase 3: Technical Assessment (similar to Phase 2)

```
business.assess_tech("Social app for pet owners")
    └─→ Similar to business analysis, but with:
        - EngineerAgent system prompt
        - technical_assessment tool
        - Results include feasibility, architecture, complexity, risks
```

### Phase 4: PRD Synthesis

```
PMAgent.build_prd() continues after getting both analyses:
    │
    ├─→ state = SharedState(memory_path=":memory:")  # Fresh
    ├─→ Register 4 tools
    │
    ├─→ executor = AgentExecutor(
    │       name="PMAgent",
    │       max_tokens=2048  # Larger for final output
    │   )
    │
    └─→ executor.run(prompt containing both analyses)
        │
        ├─→ Iteration 1:
        │   ├─→ Model may call roadmap_planner tool
        │   └─→ Tool execution → append result
        │
        ├─→ Iteration 2:
        │   ├─→ Model returns: {"final": {
        │   │       "summary": "...",
        │   │       "user_stories": [...],
        │   │       "technical_recommendations": "...",
        │   │       "business_recommendations": "...",
        │   │       "mvp_roadmap": [...],
        │   │       "risks": [...]
        │   │   }}
        │   └─→ Returned
        │
        └─→ state.add_memory({"type": "prd", "idea": idea, "result": result})
            └─→ Persisted to ai_product_manager_memory.json
```

### Phase 5: Output

```
Return prd dict
    └─→ Print as formatted JSON
        └─→ Complete
```

## Execution Timing

| Phase | Typical Time | Iterations | Tool Calls |
|-------|--------------|-----------|-----------|
| Business Analysis | 5-10s | 2-3 | 1-2 |
| Technical Assessment | 5-10s | 2-3 | 1-2 |
| PRD Synthesis | 10-20s | 2-3 | 0-1 |
| **Total** | **20-40s** | **6-9** | **2-5** |

## Memory Persistence

### ai_product_manager_memory.json Structure

```json
[
  {
    "type": "prd",
    "idea": "Social app for pet owners",
    "result": {
      "summary": "...",
      "user_stories": [...],
      "technical_recommendations": "...",
      "business_recommendations": "...",
      "mvp_roadmap": [...],
      "risks": [...]
    }
  },
  ...
]
```

### Query Pattern

```python
state = SharedState()  # Auto-loads memory
results = state.query_memory("pet")  # Case-insensitive search
```

## Failure Modes & Handling

| Scenario | Handling |
|----------|----------|
| Tool not found | `SharedState._find_tool_key()` fuzzy matches; falls back to KeyError |
| Invalid JSON from LLM | `extract_json()` attempts repair; returns `{}` if unparseable |
| 8+ iterations without final | Raises RuntimeError with iteration count |
| Network error | `urllib.error.HTTPError` propagates (not caught) |
| Missing .env | RuntimeError: "QUBRID_BASE_URL and QUBRID_API_KEY must be set" |
| LangSmith tracing error | Logged but doesn't block execution |

## Performance Optimizations

1. **History Limiting**: Last 20 messages only (prevents token overflow)
2. **Role Alternation**: Skips consecutive same-role messages (maintains API compliance)
3. **Temperature Control**: 0.2 for deterministic tool outputs, 0.3 for analysis
4. **max_tokens Tuning**: 600-800 for tools, 1200 for agents, 2048 for final PRD
5. **Lazy Imports**: FastAPI, LangSmith imported only if needed
6. **Memory Transience**: Sub-agents use `:memory:` mode (no disk I/O until final)

## Integration Points

- **Input**: CLI string or FastAPI POST request
- **Output**: JSON dict
- **External**: Qubrid REST API, optional LangSmith tracing
- **Storage**: Filesystem JSON file (ai_product_manager_memory.json)
- **Frontend**: HTML served from `/frontend/index.html`

## Design Trade-offs

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Isolation | Transient state per agent | Prevent conversation contamination |
| Tools | Callable functions | Simplicity over framework |
| Output | Structured JSON only | Perfect programmatic consumption |
| Error Handling | Fail fast | Debugging clarity |
| History Length | Last 20 messages | Token limit vs. context retention |
| Role Alternation | Enforced | Qubrid API requirement |
| State Sharing | Transient for sub-agents | No history pollution |

## Future Extensions

- Parallel agent execution (currently sequential)
- Streaming responses for real-time output
- Multi-turn user feedback loop
- A/B testing different prompts/models per agent
- Caching tool results for repeated ideas
- Rate limiting and cost budgeting
- Integration with design tools and project management systems
