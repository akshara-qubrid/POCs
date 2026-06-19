# Startup Due Diligence - Architecture

## System Overview

The Startup Due Diligence system implements a **hierarchical specialist analysis pipeline** that mirrors professional venture capital due diligence processes. The architecture decomposes investment evaluation into independent specialist domains that feed into a final investment synthesis stage.

### Core Philosophy

1. **Domain Expertise**: Each lead specializes in one dimension (market, product, finance)
2. **Independence**: Specialists work autonomously with their domain tools
3. **Hierarchical Synthesis**: Results flow upward to investment lead for final recommendation
4. **Structured Scoring**: Quantified assessments (0-10) enable direct comparison
5. **Transparent Reasoning**: Full memos alongside scores for human review

## System Architecture Diagram

```
┌────────────────────────────────────────────────────┐
│              main.py (Pipeline)                    │
│  - Coordinates all leads                           │
│  - Manages SharedState                             │
│  - Registers tools                                 │
└──────────────┬─────────────────────────────────────┘
               │
      ┌────────┼────────┐
      │        │        │
      ▼        ▼        ▼
  ┌──────┐ ┌──────┐ ┌────────┐
  │Market│ │Product│ │Financial│
  │ Lead │ │ Lead │ │ Lead   │
  └──┬───┘ └──┬───┘ └───┬────┘
     │        │        │
     │ Uses   │ Uses   │ Uses
     ▼        ▼        ▼
  ┌──────────────────────────────────┐
  │      Worker Functions            │
  │  - tam_worker()                  │
  │  - competition_worker()          │
  │  - product_assessment_worker()   │
  │  - financial_worker()            │
  └──────────────────────────────────┘
     │        │        │
     └────────┼────────┘
              │
              │ (Aggregated Results)
              ▼
   ┌────────────────────────┐
   │  InvestmentLead        │
   │  (Synthesis)           │
   │  - Integrates findings │
   │  - Generates scores    │
   │  - Makes recommendation│
   └────┬───────────────────┘
        │
        │ (Full Report)
        ▼
   ┌──────────────────────────────────┐
   │ due_diligence_memory.json         │
   │ (Persisted Reports)              │
   └──────────────────────────────────┘
```

## Components

### 1. Pipeline Orchestration (`main.py`)

**Responsibility**: Coordinate specialist leads, aggregate results, invoke synthesis

**Execution Sequence**:

```python
def run(startup: str):
    # 1. Initialize shared state and tools
    state = SharedState()  # Load due_diligence_memory.json
    for tool in get_tools():
        state.register_tool(tool)
    
    # 2. Market Analysis (sequential)
    print("[Pipeline] Running Market Lead analysis...")
    market_lead = MarketLead()
    market_result = market_lead.analyze(startup)
    state.add_message("assistant", f"MarketLead findings: {json.dumps(market_result)}")
    
    # 3. Product Analysis (sequential)
    print("[Pipeline] Running Product Lead analysis...")
    product_lead = ProductLead()
    product_result = product_lead.analyze(startup)
    state.add_message("assistant", f"ProductLead findings: {json.dumps(product_result)}")
    
    # 4. Financial Analysis (sequential)
    print("[Pipeline] Running Financial Lead analysis...")
    financial_lead = FinancialLead()
    financial_result = financial_lead.analyze(startup)
    state.add_message("assistant", f"FinancialLead findings: {json.dumps(financial_result)}")
    
    # 5. Investment Synthesis
    print("[Pipeline] Investment Lead synthesizing final report...")
    lead = InvestmentLead(state)
    enriched_prompt = startup + (
        f"\n\nPre-computed specialist analyses:\n"
        f"market: {json.dumps(market_result)}\n"
        f"product: {json.dumps(product_result)}\n"
        f"financial: {json.dumps(financial_result)}"
    )
    result = lead.evaluate(enriched_prompt)
    
    # 6. Return final report
    return result
```

**Key Points**:
- Sequential execution (can be parallelized at implementation level)
- All lead outputs appended to shared state as assistant messages
- Investment Lead receives enriched prompt with all specialist findings
- Results printed and persisted to memory

### 2. Specialist Leads Layer (`leads.py`)

**Responsibility**: Domain-specific analysis and delegation to workers

#### MarketLead Structure

```python
class MarketLead:
    def analyze(self, market: str):
        # Delegates to workers for specific analyses
        tam = tam_worker(market)
        comp = competition_worker(market)
        
        return {
            "tam": tam,              # TAM estimate
            "competition": comp      # Competitive landscape
        }
```

**TAM Estimation**:
- Model: openai/gpt-oss-120b (large, accurate for sizing)
- Prompt: "Estimate TAM for market: [market description]"
- Output: {"TAM": integer, "confidence": 0-1}
- Fallback: 1,000,000 default
- Parsing: Regex extraction of numeric values from response

**Competitive Analysis**:
- Model: mistralai/Mistral-7B-Instruct-v0.3
- Prompt: "List competitive landscape for market: [description]"
- Output: {"num_competitors": int, "intensity": string}
- Fallback: 5 competitors, "medium" intensity
- Parsing: Numeric extraction

#### ProductLead Structure

```python
class ProductLead:
    def analyze(self, product: str):
        p = product_assessment_worker(product)
        return {"product": p}
```

**Product Assessment**:
- Model: mistralai/Mistral-7B-Instruct-v0.3
- Prompt: "Assess product fit for: [product description]"
- Output: {"product_fit": 0-1, "ux_issues": [strings]}
- Fallback: 0.75 fit, empty issues array
- Parsing: Float and array extraction

#### FinancialLead Structure

```python
class FinancialLead:
    def analyze(self, data: str):
        f = financial_worker(data)
        return {"financial": f}
```

**Financial Assessment**:
- Model: deepseek-ai/deepseek-r1-distill-llama-70b
- Prompt: "Evaluate revenue model and unit economics for: [data]"
- Output: {"revenue_model_score": 0-1, "unit_economics": string}
- Fallback: 0.6 score, "OK" unit economics
- Parsing: Float and string extraction

### 3. Worker Functions (`workers.py`)

**Responsibility**: Specialized LLM calls for specific analyses

**Generic Worker Pattern**:

```python
def analysis_worker(input_text: str) -> Dict:
    model = "appropriate/model"
    messages = [{
        "role": "user",
        "content": f"Specific prompt for analysis: {input_text}"
    }]
    
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    
    # Handle mock responses
    if text.startswith("[mock]"):
        return {"default": "fallback_value"}
    
    # Parse actual response
    try:
        # Extract numeric or structured data
        return {"parsed_result": ...}
    except Exception:
        return {"default": "fallback_value"}
```

**Workers Available**:

| Worker | Model | Input | Output | Fallback |
|--------|-------|-------|--------|----------|
| tam_worker | openai/gpt-oss-120b | market | TAM, confidence | 1M, 0.6 |
| competition_worker | mistralai/7B | market | competitors, intensity | 5, "medium" |
| product_assessment | mistralai/7B | product | product_fit, ux_issues | 0.75, [] |
| financial_worker | deepseek-r1 | financial | revenue_score, economics | 0.6, "OK" |

**Error Handling**:
- Try/catch around `chat_completion()` call
- Try/catch around response parsing
- Sensible defaults if either fails
- Enables system to function offline or with API issues

### 4. Investment Lead (`investment_agent.py`)

**Responsibility**: Synthesis of all specialist findings into investment recommendation

**Implementation**:

```python
class InvestmentLead:
    def __init__(self, state: SharedState):
        self.state = state
        self.executor = AgentExecutor(
            name="InvestmentLead",
            description=(
                "You are the investment lead orchestrating market, product, "
                "and financial due diligence. Aggregate all scores and issue "
                "a final investment recommendation with a full investment memo."
            ),
            state=state,
            model="deepseek-ai/deepseek-r1-distill-llama-70b",  # Reasoning-focused model
            max_tokens=2000  # Large for comprehensive memo
        )
    
    def evaluate(self, startup: str) -> dict:
        prompt = f"""
        Perform final due diligence synthesis for the startup.
        
        Return JSON with fields:
        - market_score (0-10): Market opportunity score
        - product_score (0-10): Product viability score
        - financial_score (0-10): Financial health score
        - overall_score (0-10): Final investment score
        - risk_assessment (string): Key risks
        - investment_recommendation (invest/pass/conditional): Final recommendation
        - report (string): Full investment memo
        - key_strengths (array): Top reasons to invest
        - key_risks (array): Top risks and mitigations
        
        Startup description: {startup}
        """
        
        result = self.executor.run(prompt)
        self.state.add_memory({
            "type": "due_diligence_report",
            "startup": startup[:120],
            "result": result
        })
        return result
```

**Key Characteristics**:
- Uses reasoning-capable model (deepseek-r1)
- Large token budget (2000) for comprehensive analysis
- Can invoke specialized tools for deeper investigation
- Receives full specialist outputs in SharedState context
- Produces 9-field JSON for complete decision documentation
- Persists report to memory immediately

**Output Fields**:

| Field | Type | Purpose |
|-------|------|---------|
| market_score | 0-10 | Quantified market opportunity |
| product_score | 0-10 | Quantified product viability |
| financial_score | 0-10 | Quantified financial health |
| overall_score | 0-10 | Composite investment score |
| risk_assessment | string | Summary of critical risks |
| investment_recommendation | enum | invest/pass/conditional |
| report | string | Full investment memo (400+ words) |
| key_strengths | array | Top 3-5 reasons to invest |
| key_risks | array | Top 3-5 risks with mitigations |

### 5. AgentExecutor (Shared)

**Responsibility**: Generic JSON workflow orchestration

Shared with ai-product-manager and memory-governance:
- Message building with role alternation
- LLM invocation via Qubrid
- JSON parsing from responses
- Automatic tool invocation loops
- Error handling and retries

### 6. Shared State (`state.py`)

**Responsibility**: Manage tools, persist memory, track history

**Key Features**:
- Tool registry: `register_tool()`, `get_tool_descriptions()`, `run_tool()`
- Memory persistence: `add_memory()`, `save_memory()`, `load_memory()`
- Conversation history: `add_message()` for tracking lead findings
- Query interface: `query_memory()` for historical report retrieval

**Persistence Pattern**:
```python
# Main pipeline uses persistent state
state = SharedState()  # Uses due_diligence_memory.json

# Leads append their findings
state.add_message("assistant", f"MarketLead findings: {...}")

# Investment lead persists final report
state.add_memory({
    "type": "due_diligence_report",
    "startup": "...",
    "result": {...}
})

# Memory automatically saved to disk
```

### 7. Tools Layer (`tools.py`)

**Responsibility**: Specialized analysis tools available to Investment Lead

**Available Tools**:

1. **tam_analysis(startup_desc)**: Detailed TAM breakdown
   - Market segments
   - Addressable subsets
   - Growth rates

2. **competition_analysis(startup_desc)**: Competitive positioning
   - Direct competitors
   - Indirect competitors
   - Differentiation points

3. **product_assessment(startup_desc)**: Product features
   - Core features
   - Unique capabilities
   - Technical requirements

4. **ux_assessment(startup_desc)**: User experience
   - Onboarding complexity
   - Feature discoverability
   - Pain points

5. **technical_moat(startup_desc)**: Competitive advantage
   - Patent potential
   - Switching costs
   - Network effects

6. **revenue_model(startup_desc)**: Business model
   - Pricing strategy
   - Revenue streams
   - Customer acquisition

7. **unit_economics(startup_desc)**: Financial metrics
   - CAC (Customer Acquisition Cost)
   - LTV (Lifetime Value)
   - Payback period

**Tool Execution Pattern**:

```python
def _execute_model(prompt: str, max_tokens: int = 800) -> Dict:
    messages = [
        {"role": "system", "content": "You are a structured business analysis tool..."},
        {"role": "user", "content": prompt}
    ]
    response = chat_completion(_MODEL, messages, max_tokens, temperature=0.2)
    text = get_response_text(response)
    return extract_json(text)

def tam_analysis(startup_desc: str) -> Dict:
    prompt = f"""Analyze TAM for: {startup_desc}
    Return JSON with: market_segments, addressable_market, growth_rate"""
    return _execute_model(prompt)
```

## Execution Flow Detailed Walkthrough

### Full Due Diligence Pipeline

```
Input: "B2B SaaS for AP/AR reconciliation targeting mid-market CFOs"

main.run(startup):
    │
    ├─→ [INITIALIZATION] 1 second
    │   ├─→ state = SharedState()  # Load existing reports
    │   ├─→ Register 7 tools
    │   └─→ Print "Startup Due Diligence Engine"
    │
    ├─→ [MARKET LEAD] 5-10 seconds
    │   MarketLead().analyze(startup):
    │       │
    │       ├─→ tam_worker("B2B SaaS for AP/AR reconciliation...")
    │       │   ├─→ LLM query to openai/gpt-oss-120b
    │       │   ├─→ "Estimate TAM for market: AP/AR SaaS for CFOs"
    │       │   └─→ Response: "TAM estimated at $8-12B based on..."
    │       │       Parsing: 10000000 (10M)
    │       │       Return: {"TAM": 10000000, "confidence": 0.7}
    │       │
    │       └─→ competition_worker("B2B SaaS for AP/AR...")
    │           ├─→ LLM query to mistralai/7B
    │           ├─→ "List competitive landscape for market: AP/AR SaaS"
    │           └─→ Response: "Competitors include Coupa, SAP, Infor..."
    │               Return: {"num_competitors": 8, "intensity": "high"}
    │
    │   result = {"tam": {...}, "competition": {...}}
    │   state.add_message("assistant", f"MarketLead findings: {result}")
    │   Print: "MarketLead: {'tam': {...}, 'competition': {...}}"
    │
    ├─→ [PRODUCT LEAD] 5-10 seconds
    │   ProductLead().analyze(startup):
    │       └─→ product_assessment_worker("B2B SaaS for AP/AR...")
    │           ├─→ LLM: "Assess product fit"
    │           └─→ Return: {"product_fit": 0.8, "ux_issues": ["integration_complexity"]}
    │
    │   result = {"product": {...}}
    │   state.add_message("assistant", f"ProductLead findings: {result}")
    │
    ├─→ [FINANCIAL LEAD] 5-10 seconds
    │   FinancialLead().analyze(startup):
    │       └─→ financial_worker("B2B SaaS for AP/AR...")
    │           ├─→ LLM: "Evaluate revenue model"
    │           └─→ Return: {"revenue_model_score": 0.7, "unit_economics": "positive"}
    │
    │   result = {"financial": {...}}
    │   state.add_message("assistant", f"FinancialLead findings: {result}")
    │
    └─→ [INVESTMENT LEAD SYNTHESIS] 10-15 seconds
        InvestmentLead(state).evaluate(enriched_prompt):
            ├─→ enriched_prompt = startup + all specialist results
            │
            ├─→ executor.run(prompt):
            │   ├─→ Iteration 1:
            │   │   ├─→ _build_messages() with full context
            │   │   ├─→ Model may call tam_analysis or other tools
            │   │   └─→ Tool result appended to history
            │   │
            │   └─→ Iteration 2:
            │       ├─→ Model has tool output in context
            │       └─→ Returns final JSON:
            │           {
            │             "market_score": 8,
            │             "product_score": 7,
            │             "financial_score": 6,
            │             "overall_score": 7,
            │             "risk_assessment": "...",
            │             "investment_recommendation": "conditional",
            │             "report": "Full investment memo...",
            │             "key_strengths": [...],
            │             "key_risks": [...]
            │           }
            │
            ├─→ state.add_memory({
            │     "type": "due_diligence_report",
            │     "startup": "B2B SaaS for AP/AR reconciliation...",
            │     "result": {...}
            │   })
            │   → Persisted to due_diligence_memory.json
            │
            └─→ Return result

Output: Full due diligence report JSON (30-40 seconds total)
```

## Execution Timing

| Stage | Duration | LLM Calls | Workers Used |
|-------|----------|-----------|--------------|
| Init | 1s | 0 | - |
| Market Lead | 7s | 2 | tam_worker, competition_worker |
| Product Lead | 6s | 1 | product_assessment_worker |
| Financial Lead | 6s | 1 | financial_worker |
| Investment Synthesis | 12s | 1-3 | tam_analysis, etc. (optional) |
| **Total** | **32s** | **5-7** | **4+** |

## Scoring Hierarchy

```
Market Analysis
├─ TAM estimation (absolute market size)
├─ Competitive intensity (1-10 scale)
└─ Growth rate (%)

Product Analysis
├─ Product fit (0-1 scale)
├─ UX assessment
├─ Technical moat
└─ Feature differentiation

Financial Analysis
├─ Revenue model viability (0-1)
├─ Unit economics quality
├─ Burn rate sustainability
└─ Path to profitability

Investment Lead Synthesis
├─ market_score: 0-10
├─ product_score: 0-10
├─ financial_score: 0-10
└─ overall_score: 0-10 (weighted average or custom formula)
```

## Recommendation Logic

```python
if overall_score >= 8 and not critical_risks:
    recommendation = "invest"
elif overall_score >= 6 and addressable_risks:
    recommendation = "conditional"
else:
    recommendation = "pass"
```

## Memory Persistence

### Storage Structure

```
due_diligence_memory.json
├─ [0] { type: "due_diligence_report", startup: "...", result: {...} }
├─ [1] { type: "due_diligence_report", startup: "...", result: {...} }
└─ [...] more reports
```

### Query Interface

```python
state = SharedState()
all_reports = state.memory_store

# Query by keyword
saas_reports = state.query_memory("SaaS")
b2b_reports = state.query_memory("B2B")

# Access scores from results
for report in all_reports:
    overall_score = report["result"]["overall_score"]
    recommendation = report["result"]["investment_recommendation"]
```

## Design Patterns

### 1. Lead-Worker Separation
- Leads: High-level domain orchestration
- Workers: Specific LLM calls with fallbacks

### 2. Horizontal Parallelization
- Market, Product, Financial leads can run in parallel
- Currently sequential for simplicity
- Easy to parallelize at implementation level

### 3. Vertical Synthesis
- Lower tiers (workers) feed middle tier (leads)
- Middle tier feeds top tier (investment lead)
- Information flows upward

### 4. Fallback Pattern
- Each worker has default return value
- Enables graceful degradation
- Allows offline testing

### 5. Persistent Reporting
- Every report saved with full specialist findings
- Complete audit trail
- Historical comparison capability

## Extensibility

### Add New Lead

```python
class TechStackLead:
    def analyze(self, startup: str):
        tech = tech_assessment_worker(startup)
        return {"tech_stack": tech}

# In main.py
tech_lead = TechStackLead()
tech_result = tech_lead.analyze(startup)
state.add_message("assistant", f"TechStackLead findings: {json.dumps(tech_result)}")

# Investment Lead will see in prompt
```

### Add New Tool

```python
def technical_risk_assessment(startup: str) -> Dict:
    prompt = f"Assess technical risks for: {startup}"
    return _execute_model(prompt, _MODEL)

# In get_tools():
Tool(name="technical_risk_assessment", description="...", func=technical_risk_assessment)
```

### Adjust Scoring Formula

```python
# In InvestmentLead, adjust weighting
overall_score = (market_score * 0.4) + (product_score * 0.3) + (financial_score * 0.3)
```

## Performance Optimizations

1. **Worker Parallelization**: Run market, product, financial in parallel (instead of sequential)
2. **Tool Caching**: Cache tool results for same startup descriptions
3. **Batch Processing**: Evaluate multiple startups in one API session
4. **Model Selection**: Use lighter models for workers, heavier for synthesis
5. **Token Limits**: Tune max_tokens per stage based on actual usage

## Error Handling & Resilience

- Worker fallbacks prevent cascade failures
- Tool invocation errors don't crash pipeline
- Missing specialist outputs handled gracefully
- LLM timeouts fall back to defaults
- All errors logged for debugging
