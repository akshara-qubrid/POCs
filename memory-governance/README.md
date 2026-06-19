# Memory Governance POC

A production-grade proof of concept for intelligent memory lifecycle management. This system demonstrates a sophisticated multi-stage decision pipeline that evaluates whether information should be persisted as memory based on retention viability, contextual relevance, and governance policies.

## System Overview

The Memory Governance system implements a **three-stage evaluation pipeline** for memory ingestion:

1. **Retention Stage**: Evaluates intrinsic value - should this information be stored at all?
2. **Relevance Stage**: Evaluates contextual value - how useful will this be in future contexts?
3. **Governance Stage**: Synthesizes both analyses and makes final store/discard decision with importance scoring

Each stage operates independently with isolated state, enabling transparent decision auditing and modular policy updates.

## Key Features

- **Multi-Stage Decision Pipeline**: Separates retention, relevance, and governance logic into independent agents
- **Isolated Sub-Agent State**: Each evaluator uses transient state (`":memory:"`) preventing conversation contamination
- **Transparent Scoring**: Retention scores (0-1), relevance scores (0-1), importance scores (0-1) with reasoning
- **Selective Persistence**: Only approved items are written to persistent memory store
- **Tool-Driven Evaluation**: Agents can request specialized scoring tools during evaluation
- **Batch Processing**: Supports both single-item evaluation and batch processing of multiple items
- **Persistent Memory Store**: Accepted memories stored in `memory_governance_memory.json` with full provenance
- **Dual Interface**: CLI and FastAPI server interfaces for flexible integration

## Architecture Components

### Core Modules

#### [memory_governance/main.py](memory_governance/main.py)
**Entry point, demonstration, and REST API server**

- **Batch Demo Mode**: Processes 4 sample items with varied retention scenarios
- **Single-Item Mode**: Evaluates individual items with context
- **FastAPI Server**: Exposes REST endpoints for programmatic access
- **Summary Output**: Prints governance decisions with importance scores

Usage:
```bash
# Batch demo (4 sample items)
python -m memory_governance.main

# Single item evaluation
python -m memory_governance.main "User prefers dark mode" "UI preferences"

# Server mode
uvicorn memory_governance.main:app --reload --port 8002

# Server endpoints
POST /consider  → {"item": "...", "context": "..."} → governance decision
GET  /memory    →                                    → persisted memories
GET  /          →                                    → HTML frontend
```

#### [memory_governance/agents.py](memory_governance/agents.py)
**Specialized evaluation agents with isolated state**

**RetentionAgent** (`evaluate` method)

- **Purpose**: Determines if an item has inherent value worth storing
- **Isolated State**: Creates fresh SharedState with `:memory:` path
- **Tool Access**: Registered `score_retention` tool for deeper analysis
- **Model**: `mistralai/Mistral-7B-Instruct-v0.3`, max_tokens=600
- **Output Fields**:
  - `should_store` (boolean): Initial recommendation
  - `retention_score` (0-1 float): Quantified value assessment
  - `category` (string): Classification (e.g., "user_preference", "system_event", "historical_context")
  - `is_duplicate` (boolean): Whether item seems redundant with known memories
  - `reasoning` (string): Explanation for retention score

**Evaluation Logic**:
- Distinguishes signal from noise (e.g., "dark mode preference" vs "random heartbeat")
- Detects system noise (logs, debug messages, irrelevant events)
- Assesses uniqueness and distinctiveness
- Provides actionable reasoning for downstream stages

**RelevanceAgent** (`evaluate` method)

- **Purpose**: Assesses likelihood of retrieval and usefulness in future contexts
- **Isolated State**: Fresh SharedState with `:memory:` path
- **Tool Access**: Registered `score_relevance` tool for analysis
- **Model**: `mistralai/Mistral-7B-Instruct-v0.3`, max_tokens=600
- **Output Fields**:
  - `relevance_score` (0-1 float): Estimated future usefulness
  - `retrieval_priority` (string): high/medium/low priority for indexing
  - `future_usefulness` (string): Detailed explanation of potential applications
  - `memory_relationships` (array of strings): How this connects to other memory domains
  - `reasoning` (string): Justification for relevance assessment

**Evaluation Logic**:
- Considers contextual indicators (domain, temporal markers, specificity)
- Estimates retrieval patterns (how often this type of info is retrieved)
- Identifies cross-cutting concerns (applies to multiple domains)
- High relevance: Specific user preferences, architectural decisions, configuration
- Low relevance: Ephemeral system noise, redundant entries, temporal outliers

**MemoryGovernor** (orchestrator)

- **Initialization**: Takes shared_state (for persistence access only)
- **Sub-Agent Instantiation**: Creates RetentionAgent and RelevanceAgent instances
- **Decision Making**: Uses both retention and relevance scores to synthesize final decision
- **Memory Persistence**: Only stores items when final decision is `"store"`

**Flow** (`consider` method):

```
MemoryGovernor.consider(item, context)
    │
    ├─→ RetentionAgent.evaluate(item)
    │   └─→ Returns: {should_store, retention_score, category, is_duplicate, reasoning}
    │
    ├─→ RelevanceAgent.evaluate(item, context)
    │   └─→ Returns: {relevance_score, retrieval_priority, future_usefulness, 
    │                 memory_relationships, reasoning}
    │
    ├─→ MemoryGovernor executor runs synthesis prompt:
    │   Input: retention + relevance analyses, item, context
    │   Output: {decision, importance_score, retention_category, retrieval_priority, explanation}
    │
    ├─→ If decision == "store":
    │   └─→ shared_state.add_memory({item, context, retention, relevance, governance})
    │       └─→ Persisted to memory_governance_memory.json
    │
    └─→ Return governance decision
```

#### [memory_governance/agent_executor.py](memory_governance/agent_executor.py)
**Generic executor for JSON-based workflows (shared with ai-product-manager)**

Provides same capabilities as ai-product-manager:
- Message building with role alternation enforcement
- LLM invocation via Qubrid
- JSON parsing from responses
- Automatic tool invocation loops (max 8 iterations)

#### [memory_governance/state.py](memory_governance/state.py)
**State management with persistence and tool registry**

- **Memory Transience Pattern**: Sub-agents use `SharedState(memory_path=":memory:")` for isolated evaluation
- **Persistent Shared State**: Main pipeline uses default path for memory persistence
- **Tool Registry**: Shared tools across all agents
- **History Management**: Tracks all evaluation steps for auditing

#### [memory_governance/llm_client.py](memory_governance/llm_client.py)
**Qubrid REST API client (shared implementation)**

Same as ai-product-manager: loads `.env`, authenticates, makes HTTP POST requests, handles responses.

#### [memory_governance/tools.py](memory_governance/tools.py)
**Specialized evaluation tools**

**score_retention(item)** tool
- Evaluates retention criteria:
  - Information completeness
  - Uniqueness/distinctiveness
  - Signal-to-noise ratio
- Returns structured scoring in JSON

**score_relevance(item, context)** tool
- Evaluates relevance criteria:
  - Domain specificity
  - Cross-domain applicability
  - Temporal persistence
  - Retrieval likelihood
- Returns prioritization in JSON

## Execution Flow Walkthrough

### Scenario: Processing 4 Demo Items

```
run_demo() called with default items:
[
  {
    "item": "User prefers dark mode and compact layout",
    "context": "UI personalization preferences"
  },
  {
    "item": "ERROR: connection timeout at 2026-06-15",
    "context": "System reliability tracking"
  },
  {
    "item": "Q3 roadmap discussion notes with team",
    "context": "Product X roadmap"
  },
  {
    "item": "DEBUG heartbeat ok",
    "context": "Product X roadmap"
  }
]

┌─────────────────────────────────────────────────┐
│ Processing Item 1: "User prefers dark mode..." │
└─────────────────────────────────────────────────┘

MemoryGovernor.consider(item, context):
    │
    ├─→ RetentionAgent.evaluate():
    │   ├─→ Create isolated state
    │   ├─→ AgentExecutor loop (iteration 1):
    │   │   └─→ LLM may call score_retention tool
    │   ├─→ AgentExecutor loop (iteration 2):
    │   │   └─→ LLM returns {
    │   │         "should_store": true,
    │   │         "retention_score": 0.9,
    │   │         "category": "user_preference",
    │   │         "is_duplicate": false,
    │   │         "reasoning": "Specific UI preferences with high personalization value"
    │   │       }
    │   └─→ Retention result returned
    │
    ├─→ RelevanceAgent.evaluate():
    │   ├─→ Create isolated state
    │   ├─→ Similar loop to Retention
    │   └─→ Returns {
    │         "relevance_score": 0.95,
    │         "retrieval_priority": "high",
    │         "future_usefulness": "Will be queried every time rendering UI",
    │         "memory_relationships": ["user_interface", "personalization", "accessibility"],
    │         "reasoning": "Essential for user experience decisions"
    │       }
    │
    ├─→ MemoryGovernor synthesis:
    │   ├─→ Create isolated state
    │   ├─→ Prompt includes both retention + relevance analyses
    │   ├─→ Model synthesizes: {
    │   │     "decision": "store",
    │   │     "importance_score": 0.92,
    │   │     "retention_category": "user_preference",
    │   │     "retrieval_priority": "high",
    │   │     "explanation": "High retention and relevance scores support storing"
    │   │   }
    │   │
    │   └─→ Since decision=="store": persist to memory
    │       shared_state.add_memory({
    │         "item": "User prefers dark mode...",
    │         "context": "UI preferences",
    │         "retention": {...},
    │         "relevance": {...},
    │         "governance": {...}
    │       })
    │       → Written to memory_governance_memory.json
    │
    └─→ Print: "[STORE] score=0.92  'User prefers dark mode...'"

┌────────────────────────────────────────────┐
│ Processing Item 2: "ERROR: connection..." │
└────────────────────────────────────────────┘

RetentionAgent.evaluate():
    └─→ Returns {
          "should_store": false,
          "retention_score": 0.2,
          "category": "system_event",
          "is_duplicate": false,
          "reasoning": "Ephemeral system error, not actionable long-term knowledge"
        }

RelevanceAgent.evaluate():
    └─→ Returns {
          "relevance_score": 0.15,
          "retrieval_priority": "low",
          "future_usefulness": "Minimal, error likely transient",
          "memory_relationships": [],
          "reasoning": "Low retrieval value, event-specific"
        }

MemoryGovernor synthesis:
    └─→ decision="discard"
        → NOT persisted
        → Print: "[DISCARD] 'ERROR: connection timeout...'"

┌─────────────────────────────────────┐
│ Processing Item 3 & 4 similarly     │
└─────────────────────────────────────┘

Final summary:
  [STORE] score=0.92     'User prefers dark mode...'
  [DISCARD] score=0.2    'ERROR: connection timeout...'
  [STORE] score=0.85     'Q3 roadmap discussion...'
  [DISCARD] score=0.1    'DEBUG heartbeat ok'
```

### Memory Store Result

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
      "reasoning": "Specific UI preferences with high personalization value"
    },
    "relevance": {
      "relevance_score": 0.95,
      "retrieval_priority": "high",
      "future_usefulness": "Will be queried every time rendering UI",
      "memory_relationships": ["user_interface", "personalization", "accessibility"],
      "reasoning": "Essential for user experience decisions"
    },
    "governance": {
      "decision": "store",
      "importance_score": 0.92,
      "retention_category": "user_preference",
      "retrieval_priority": "high",
      "explanation": "High retention and relevance scores support storing"
    }
  },
  ...
]
```

## Installation & Setup

```bash
# Navigate to project
cd memory-governance

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
QUBRID_BASE_URL=https://platform.qubrid.com/v1
QUBRID_API_KEY=your_api_key_here
EOF
```

## Usage Examples

### CLI Mode
```bash
# Batch demo with 4 sample items
python -m memory_governance.main

# Single item evaluation
python -m memory_governance.main "User clicked button 5 times today" "user_interaction_tracking"

# Complex item with multiple contexts
python -m memory_governance.main \
  "Discovered: users in EU region have 40% higher churn after onboarding" \
  "user_retention,geographic_analysis,onboarding_effectiveness"
```

### Server Mode
```bash
# Start server on port 8002
uvicorn memory_governance.main:app --reload --port 8002

# Make API request
curl -X POST http://localhost:8002/consider \
  -H "Content-Type: application/json" \
  -d '{
    "item": "User preference: wants email digest on Sundays",
    "context": "communication_preferences"
  }'

# Get all stored memories
curl http://localhost:8002/memory | jq
```

## Decision Matrix

| Retention Score | Relevance Score | Governance Decision | Use Case |
|-----------------|-----------------|-------------------|----------|
| High (0.8+) | High (0.8+) | STORE | Critical user preferences, architectural decisions |
| High (0.8+) | Low (0.2-) | CONDITIONAL | Important but niche information |
| Low (0.2-) | High (0.8+) | CONDITIONAL | High-value pattern, low retention signal |
| Low (0.2-) | Low (0.2-) | DISCARD | Noise, ephemeral events, debug logs |

## Memory Governance Policies

The system evaluates memories across three dimensions:

### Retention Criteria
- **Specificity**: More specific = higher score
- **Actionability**: Can this inform decisions? 
- **Uniqueness**: Is this novel or redundant?
- **Completeness**: Does it have enough context?

### Relevance Criteria
- **Domain Applicability**: How many domains does this apply to?
- **Temporal Persistence**: Will this be relevant in 1 week? 1 month?
- **Retrieval Likelihood**: How often will this be queried?
- **Contextual Richness**: Does this enrich decision-making?

### Governance Synthesis
- **Score Weighting**: Retention 50%, Relevance 50% (tunable)
- **Threshold**: Importance > 0.7 → Store
- **Override**: Low scores but high cross-domain relevance may be stored
- **Audit Trail**: Full provenance recorded for all decisions

## Output Structure

### Single Decision Output
```json
{
  "decision": "store",
  "importance_score": 0.85,
  "retention_category": "user_preference",
  "retrieval_priority": "high",
  "explanation": "Clear user preference with high retrieval likelihood"
}
```

### Batch Results
```json
[
  {
    "item": "...",
    "decision": {
      "decision": "store",
      "importance_score": 0.92,
      ...
    }
  },
  ...
]
```

## Design Principles

1. **Transparent Multi-Stage Pipeline**: Each stage produces auditable output
2. **Isolated Evaluation**: Sub-agents don't contaminate each other's reasoning
3. **Qualitative + Quantitative**: Scores (0-1) + reasoning text
4. **Selective Persistence**: Only valuable items stored
5. **Modular Policies**: Easy to adjust scoring criteria per domain
6. **Full Provenance**: Complete decision history preserved
7. **Batch Capable**: Efficient processing of multiple items

## Performance Characteristics

- Average evaluation time per item: 10-15 seconds
- Token usage per item: 1500-2500 tokens
- Batch throughput: 4 items in ~45-60 seconds
- Memory footprint: 50MB base + ~5KB per stored item
- Storage: JSON-based, minimal overhead

## Extensions & Customization

The system can be extended with:
- Custom retention/relevance scoring tools
- Domain-specific evaluation logic
- Temporal decay (older memories scored lower)
- Cross-memory relationship mapping
- Integration with vector databases for semantic similarity
- Batch APIs for large-scale ingestion
- Analytics dashboard for memory health metrics
