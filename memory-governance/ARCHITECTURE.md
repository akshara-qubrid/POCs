# Memory Governance - Architecture

## System Overview

The Memory Governance system implements a **three-stage decision pipeline** for intelligent memory ingestion and persistence. Rather than storing everything or using simplistic rules, the system decomposes memory governance into specialized evaluation stages that assess different dimensions of memory value:

1. **Retention Stage**: Evaluates intrinsic value (is this worth keeping?)
2. **Relevance Stage**: Evaluates contextual value (how useful will this be?)
3. **Governance Stage**: Synthesizes both and makes final store/discard decision

This modular approach enables transparent reasoning, independent policy tuning, and audit trails.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      main.py                                 │
│  (Demonstration + Orchestration)                             │
│  - Batch demo or single item                                 │
│  - Creates shared MemoryGovernor                             │
│  - Prints summary with scores                                │
└──────────────────────┬───────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐    ┌──────────┐   ┌──────────┐
   │Retention│    │Relevance │   │ Memory   │
   │ Agent   │    │  Agent   │   │Governor  │
   └────┬────┘    └────┬─────┘   └─────┬────┘
        │              │              │
        │ (Isolated)   │ (Isolated)  │ (Isolated)
        │ State        │ State       │ State
        │              │             │
   ┌────▼──────────────▼─────────────▼─────┐
   │    AgentExecutor (Generic)             │
   │  - Tool invocation loops                │
   │  - JSON parsing & extraction           │
   │  - LLM coordination                    │
   └────┬──────────────────────────────────┬┘
        │                                  │
        ▼                                  ▼
   ┌─────────────┐         ┌───────────────────────┐
   │ LLM Client  │         │ Shared State          │
   │ (Qubrid)    │         │ - Persistence         │
   │             │         │ - Tool Registry       │
   │ Via HTTP    │         │ - Memory Store        │
   └─────────────┘         └───────────────────────┘
        │
        │ (Only if decision == "store")
        ▼
   ┌──────────────────────────────────┐
   │ memory_governance_memory.json     │
   │ (Persisted Approved Memories)    │
   └──────────────────────────────────┘
```

## Components

### 1. RetentionAgent (Retention Stage)

**Responsibility**: Assess intrinsic value and storage worthiness

**Evaluation Questions**:
- Is this information specific and actionable?
- Does it contain unique knowledge or redundant noise?
- Is it well-formed and complete enough to understand?
- Could this influence future decisions?

**Implementation** (`agents.py`):

```python
class RetentionAgent:
    def evaluate(self, item: str) -> dict:
        # Create isolated state for evaluation
        state = SharedState(memory_path=":memory:")
        for tool in all_tools:
            state.register_tool(tool)
        
        # Create executor with retention-focused prompt
        executor = AgentExecutor(
            name="RetentionAgent",
            description=(
                "You are the retention specialist. Evaluate whether this item "
                "should be stored in memory. Assign retention score (0-1), "
                "categorize, detect duplicates, return structured JSON."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=600
        )
        
        # Execute evaluation
        prompt = f"""
        Evaluate retention value of: {item}
        
        Return JSON with fields:
        - should_store (bool): Initial recommendation
        - retention_score (0-1): Quantified value
        - category (string): Type classification
        - is_duplicate (bool): Redundancy check
        - reasoning (string): Justification
        
        May call score_retention tool for analysis.
        """
        
        result = executor.run(prompt)
        return result
```

**Scoring Criteria**:

| Item Type | Example | Score | Reason |
|-----------|---------|-------|--------|
| User Preference | "User prefers dark mode" | 0.9 | Specific, actionable, persistent |
| Architectural Decision | "Use PostgreSQL for relational data" | 0.95 | High-value, rarely changes |
| System Noise | "DEBUG heartbeat ok" | 0.1 | Ephemeral, non-actionable |
| Error Event | "Connection timeout at 03:12" | 0.2 | Transient, event-specific |
| Meeting Note | "Q3 roadmap priorities: A, B, C" | 0.85 | Specific, decision-relevant |

**Output Structure**:
```json
{
  "should_store": true,
  "retention_score": 0.9,
  "category": "user_preference",
  "is_duplicate": false,
  "reasoning": "Specific UI preference with long-term relevance for personalization"
}
```

### 2. RelevanceAgent (Relevance Stage)

**Responsibility**: Assess contextual value and retrieval likelihood

**Evaluation Questions**:
- How relevant is this to the provided context?
- Will this be queried in future decision-making?
- Does this apply across multiple domains?
- What is the temporal persistence of this information?

**Implementation** (`agents.py`):

```python
class RelevanceAgent:
    def evaluate(self, item: str, context: str) -> dict:
        state = SharedState(memory_path=":memory:")
        for tool in all_tools:
            state.register_tool(tool)
        
        executor = AgentExecutor(
            name="RelevanceAgent",
            description=(
                "You are the relevance specialist. Given item and context, "
                "evaluate future usefulness, contextual relevance, and "
                "retrieve priority. Return structured JSON."
            ),
            state=state,
            model="mistralai/Mistral-7B-Instruct-v0.3",
            max_tokens=600
        )
        
        prompt = f"""
        Evaluate relevance of item to context:
        item: {item}
        context: {context}
        
        Return JSON with fields:
        - relevance_score (0-1): Estimated future usefulness
        - retrieval_priority (high/medium/low): Indexing priority
        - future_usefulness (string): Scenarios for retrieval
        - memory_relationships (array): Domain connections
        - reasoning (string): Justification
        
        May call score_relevance tool for analysis.
        """
        
        result = executor.run(prompt)
        return result
```

**Scoring Criteria**:

| Context | Item | Score | Reason |
|---------|------|-------|--------|
| UI personalization | "User prefers dark mode" | 0.95 | High retrieval frequency |
| System reliability | "ERROR: connection timeout" | 0.15 | Low relevance, transient |
| Product roadmap | "Q3 priorities: A, B, C" | 0.88 | Core to roadmap decisions |
| Product roadmap | "DEBUG heartbeat ok" | 0.05 | Noise in domain context |

**Output Structure**:
```json
{
  "relevance_score": 0.95,
  "retrieval_priority": "high",
  "future_usefulness": "Retrieved every UI render, critical for personalization",
  "memory_relationships": ["user_interface", "personalization", "accessibility"],
  "reasoning": "Direct application to rendering logic with frequent access pattern"
}
```

### 3. MemoryGovernor (Governance Stage)

**Responsibility**: Synthesize retention + relevance into final decision and importance score

**Decision Logic**:

```python
class MemoryGovernor:
    def consider(self, item: str, context: str) -> dict:
        # 1. Retention evaluation (intrinsic value)
        retention = self.retention_agent.evaluate(item)
        retention_score = retention.get("retention_score", 0)
        
        # 2. Relevance evaluation (contextual value)
        relevance = self.relevance_agent.evaluate(item, context)
        relevance_score = relevance.get("relevance_score", 0)
        
        # 3. Governance synthesis
        governor_executor = self._make_governor_executor()
        prompt = f"""
        Based on retention and relevance analyses, make final decision:
        
        retention_analysis: {retention}
        relevance_analysis: {relevance}
        
        Return JSON with fields:
        - decision (store/discard): Final decision
        - importance_score (0-1): Combined score
        - retention_category: From retention analysis
        - retrieval_priority: From relevance analysis
        - explanation: Reasoning for decision
        """
        
        result = governor_executor.run(prompt)
        
        # 4. Persistence (only if decision=="store")
        if result.get("decision") == "store":
            self.shared_state.add_memory({
                "item": item,
                "context": context,
                "retention": retention,
                "relevance": relevance,
                "governance": result
            })
        
        return result
```

**Decision Matrix**:

```
Retention (X) vs Relevance (Y) → Decision

         Low Rel (0.2)  Mid Rel (0.5)  High Rel (0.8)
Low Ret  DISCARD        CONDITIONAL    MAYBE
Mid Ret  CONDITIONAL    CONDITIONAL    STORE
High Ret MAYBE          STORE          STORE

STORE: Save to persistent memory
CONDITIONAL: Possible store depending on importance_score threshold (e.g., > 0.7)
DISCARD: Do not persist
MAYBE: Store for now, may be pruned later based on access patterns
```

**Importance Score Calculation**:
```
importance_score = (retention_score * 0.5) + (relevance_score * 0.5)

Examples:
- retention=0.9, relevance=0.95 → importance=0.925 → STORE
- retention=0.2, relevance=0.1  → importance=0.15  → DISCARD
- retention=0.9, relevance=0.2  → importance=0.55  → CONDITIONAL
```

**Output Structure**:
```json
{
  "decision": "store",
  "importance_score": 0.92,
  "retention_category": "user_preference",
  "retrieval_priority": "high",
  "explanation": "High retention and relevance scores support storing this memory"
}
```

### 4. SharedState (Persistence & Tool Registry)

**Responsibility**: Manage shared tool registry, persist approved memories, query history

**Key Operations**:

1. **Transient Mode for Sub-Agents**:
   ```python
   # Each evaluation agent uses fresh state
   state = SharedState(memory_path=":memory:")  # No disk persistence
   ```

2. **Persistent Mode for Governor**:
   ```python
   # Main pipeline maintains persistent store
   state = SharedState()  # Uses memory_governance_memory.json
   state.add_memory(record)  # Writes to disk immediately
   ```

3. **Tool Registry**:
   ```python
   state.register_tool(Tool(
       name="score_retention",
       description="Score retention value of memory item",
       func=score_retention_impl
   ))
   ```

4. **Memory Persistence**:
   ```python
   memory_store = [
       {
           "item": "...",
           "context": "...",
           "retention": {...},
           "relevance": {...},
           "governance": {...}
       },
       ...
   ]
   # Saved to memory_governance_memory.json (append-only)
   ```

### 5. AgentExecutor (Generic Orchestrator)

**Responsibility**: Execute agents with proper LLM interaction and tool looping

Shared with ai-product-manager:
- Message building with role alternation
- Tool invocation loops (max 8 iterations)
- JSON parsing and validation
- Error handling and debugging

**Execution Flow**:

```
Iteration 1:
  - _build_messages() → [system, user]
  - chat_completion() → LLM call
  - extract_json() → {"tool": "score_retention", "input": "..."}
  - state.run_tool() → Execute tool, append result
  
Iteration 2:
  - _build_messages() → [system, user, assistant (tool result), user]
  - chat_completion() → LLM call
  - extract_json() → {"final": {...}}
  - Return result
```

### 6. Tools (`tools.py`)

**Available Tools**:

1. **score_retention(item)**: Specializes in retention criteria
   - Analyzes signal-to-noise ratio
   - Checks for duplicates
   - Evaluates actionability
   - Returns retention score + category

2. **score_relevance(item, context)**: Specializes in relevance criteria
   - Maps contextual applicability
   - Estimates retrieval likelihood
   - Identifies domain relationships
   - Returns relevance score + priority

**Tool Invocation Pattern**:
```python
def get_tools() -> List[Tool]:
    return [
        Tool(
            name="score_retention",
            description="Analyze retention value and signal quality",
            func=score_retention
        ),
        Tool(
            name="score_relevance",
            description="Analyze relevance and retrieval priority",
            func=score_relevance
        ),
    ]
```

## Execution Flow Detailed Walkthrough

### Single Item Evaluation

```
Input: item="User prefers dark mode", context="UI preferences"

main.run_demo(items, context)
    │
    └─→ MemoryGovernor.consider(item, context)
        │
        ├─→ [Stage 1: Retention]
        │   RetentionAgent.evaluate(item)
        │       ├─→ Create isolated state (":memory:")
        │       ├─→ Create executor with system prompt
        │       ├─→ executor.run(prompt)
        │       │   ├─→ Iteration 1:
        │       │   │   ├─→ Model may call score_retention tool
        │       │   │   └─→ Tool result appended to history
        │       │   └─→ Iteration 2:
        │       │       └─→ Model returns {"final": {...}}
        │       │
        │       └─→ Return {
        │             "should_store": true,
        │             "retention_score": 0.9,
        │             "category": "user_preference",
        │             "is_duplicate": false,
        │             "reasoning": "..."
        │           }
        │
        ├─→ [Stage 2: Relevance]
        │   RelevanceAgent.evaluate(item, context)
        │       ├─→ Similar isolated state creation
        │       ├─→ Similar executor loop
        │       │
        │       └─→ Return {
        │             "relevance_score": 0.95,
        │             "retrieval_priority": "high",
        │             "future_usefulness": "...",
        │             "memory_relationships": [...],
        │             "reasoning": "..."
        │           }
        │
        └─→ [Stage 3: Governance]
            MemoryGovernor executor.run(synthesis_prompt)
                ├─→ Includes both retention + relevance outputs
                ├─→ Model sees full analysis context
                │
                └─→ Return {
                      "decision": "store",
                      "importance_score": 0.925,
                      "retention_category": "user_preference",
                      "retrieval_priority": "high",
                      "explanation": "..."
                    }
            
            Decision == "store" → Persist to memory
                shared_state.add_memory({
                    "item": item,
                    "context": context,
                    "retention": {...},
                    "relevance": {...},
                    "governance": {...}
                })
                → memory_governance_memory.json updated

Output: governance result dict + persisted memory record
```

### Batch Processing (4 Demo Items)

```
ITEM 1: "User prefers dark mode"
  → [Stage 1: Retention] score=0.9, should_store=true
  → [Stage 2: Relevance] score=0.95, priority=high
  → [Stage 3: Governance] decision=STORE, importance=0.925
  → PERSISTED ✓

ITEM 2: "ERROR: connection timeout"
  → [Stage 1: Retention] score=0.2, should_store=false
  → [Stage 2: Relevance] score=0.15, priority=low
  → [Stage 3: Governance] decision=DISCARD, importance=0.175
  → NOT PERSISTED ✗

ITEM 3: "Q3 roadmap discussion notes"
  → [Stage 1: Retention] score=0.85, should_store=true
  → [Stage 2: Relevance] score=0.88, priority=high
  → [Stage 3: Governance] decision=STORE, importance=0.865
  → PERSISTED ✓

ITEM 4: "DEBUG heartbeat ok"
  → [Stage 1: Retention] score=0.1, should_store=false
  → [Stage 2: Relevance] score=0.05, priority=low
  → [Stage 3: Governance] decision=DISCARD, importance=0.075
  → NOT PERSISTED ✗

Summary:
  [STORE]   score=0.925  'User prefers dark mode...'
  [DISCARD] score=0.175  'ERROR: connection timeout...'
  [STORE]   score=0.865  'Q3 roadmap discussion...'
  [DISCARD] score=0.075  'DEBUG heartbeat ok'
```

## Persistence Model

### Memory Store Structure

```json
[
  {
    "item": "User prefers dark mode and compact layout",
    "context": "UI personalization preferences",
    "retention": {
      "should_store": true,
      "retention_score": 0.9,
      "category": "user_preference",
      "is_duplicate": false,
      "reasoning": "..."
    },
    "relevance": {
      "relevance_score": 0.95,
      "retrieval_priority": "high",
      "future_usefulness": "...",
      "memory_relationships": ["user_interface", "personalization"],
      "reasoning": "..."
    },
    "governance": {
      "decision": "store",
      "importance_score": 0.925,
      "retention_category": "user_preference",
      "retrieval_priority": "high",
      "explanation": "..."
    }
  },
  ...
]
```

### Isolation Strategy

**Sub-Agents** (RetentionAgent, RelevanceAgent, MemoryGovernor):
```python
state = SharedState(memory_path=":memory:")  # Fresh, transient
```
- No cross-contamination between evaluations
- Each agent starts with clean conversation history
- Prevents feedback loops or cascading errors

**Main Pipeline** (MemoryGovernor persistence):
```python
state = SharedState()  # Default: memory_governance_memory.json
```
- Persists approved memories to disk
- Maintains long-term audit trail
- Enables memory queries via `query_memory(text)`

## Evaluation Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│ Incoming Memory Item (item, context)                    │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │  Retention      │
        │  Evaluation     │
        │  (0-1 score)    │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  Relevance      │
        │  Evaluation     │
        │  (0-1 score)    │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │  Governance     │
        │  Synthesis      │
        │  + Decision     │
        └────────┬────────┘
                 │
         ┌───────┴────────┐
         │                │
    ┌────▼────┐      ┌────▼──────┐
    │ decision │      │ decision  │
    │= "store" │      │= "discard"│
    └────┬────┘      └───────────┘
         │
    ┌────▼────────────┐
    │ Persist to      │
    │ memory_         │
    │ governance_     │
    │ memory.json     │
    └─────────────────┘
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Time per item | 10-15s | 3 agents × 2-3 iterations each |
| Tokens per item | 1500-2500 | Sum of all 3 stages |
| Storage per item | ~5-10KB | With full provenance |
| Batch throughput | 4 items/min | Parallelizable per item |
| Memory footprint | 50MB + store | Base Python + JSON store |

## Design Advantages

1. **Transparency**: Full provenance of all decisions (retention + relevance + governance)
2. **Modularity**: Each stage independently tunable/replaceable
3. **Auditability**: Complete reasoning path preserved
4. **Selective Persistence**: Only valuable items stored (cost optimization)
5. **Multi-Dimensional**: Retention ≠ Relevance (independent assessment)
6. **Isolation**: No cross-agent contamination
7. **Scalability**: Easily parallelizable at item level

## Customization Points

- **Retention Scoring**: Tune noise thresholds, category mapping
- **Relevance Scoring**: Adjust temporal decay, domain weighting
- **Importance Threshold**: Control store/discard boundary
- **Tool Selection**: Add domain-specific scoring tools
- **Model Selection**: Different models per stage
- **Token Budgets**: Per-stage tuning
- **Persistence Path**: Store in different backends (S3, database, etc.)

## Future Extensions

- Temporal decay (older memories rescored periodically)
- Cross-memory similarity detection (prevent near-duplicates)
- Access pattern tracking (optimize indexing)
- Domain-specific evaluation policies
- Integration with vector databases for semantic search
- Batch API for large-scale ingestion
- Analytics dashboard for memory health metrics
