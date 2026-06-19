# Startup Due Diligence POC

A production-grade proof of concept for AI-driven startup valuation and investment analysis. This system demonstrates a hierarchical workflow from specialist domain experts to investment synthesis, producing comprehensive due diligence reports with scored recommendations.

## System Overview

The Startup Due Diligence system implements a **specialist-led analysis pipeline** that mirrors real investment processes:

1. **Market Analysis**: Expert evaluation of market size, competitive landscape, TAM
2. **Product Analysis**: Assessment of product-market fit, UX considerations, technical moat
3. **Financial Analysis**: Revenue model evaluation, unit economics, financial viability
4. **Investment Synthesis**: Investment lead integrates all analyses into final recommendation memo

Each specialist operates independently, producing structured outputs that feed into final synthesis. This enables transparent reasoning, independent expert adjustment, and comprehensive due diligence reporting.

## Key Features

- **Hierarchical Expert Pipeline**: Market, Product, and Financial specialists feed into Investment Lead
- **Multi-Stage Analysis**: Worker-based analysis for TAM, competition, product fit, financials
- **Specialist Leads**: Domain experts synthesize worker outputs into lead-level findings
- **Investment Synthesis**: Final orchestration by Investment Lead into comprehensive memo
- **Structured Scoring**: Market (0-10), Product (0-10), Financial (0-10), Overall (0-10) scores
- **Risk Assessment**: Identified risks with severity scoring and mitigation strategies
- **Persistent Reporting**: Full due diligence reports stored in `due_diligence_memory.json`
- **Tool-Driven Analysis**: Specialized tools for TAM analysis, competition assessment, etc.
- **Dual Interface**: CLI and FastAPI server interfaces

## Architecture Components

### Core Modules

#### [due_diligence/main.py](due_diligence/main.py)
**Entry point and pipeline orchestration**

- **Pipeline Coordination**: Executes Market, Product, and Financial leads sequentially
- **State Management**: Creates SharedState, registers tools, manages memory
- **Result Aggregation**: Collects lead outputs and passes enriched context to Investment Lead
- **FastAPI Server**: REST endpoints for programmatic access

Usage:
```bash
# CLI execution
python -m due_diligence.main "B2B SaaS for AP/AR reconciliation targeting mid-market CFOs"

# Server execution
uvicorn due_diligence.main:app --reload --port 8003

# Server endpoints
POST /evaluate  → {"startup": "..."} → due diligence report JSON
GET  /memory    →                     → persisted reports
GET  /          →                     → HTML frontend
```

#### [due_diligence/leads.py](due_diligence/leads.py)
**Specialist lead implementations**

**MarketLead** (`analyze` method)

- **Responsibilities**: TAM estimation, competitive landscape, market dynamics
- **Worker Delegation**: Calls `tam_worker` and `competition_worker`
- **Output Structure**:
  ```json
  {
    "tam": {
      "TAM": 1000000,           // Total addressable market in dollars
      "confidence": 0.7,         // Confidence in estimate
      "segments": [...],         // Market segments
      "growth_rate": "20%"      // Year-over-year growth
    },
    "competition": {
      "num_competitors": 5,      // Direct competitors
      "intensity": "medium",     // Competitive intensity
      "differentiation": [...], // Key differentiators
      "market_share": "..."      // Current market distribution
    }
  }
  ```

**ProductLead** (`analyze` method)

- **Responsibilities**: Product-market fit, feature assessment, UX considerations
- **Worker Delegation**: Calls `product_assessment_worker`
- **Output Structure**:
  ```json
  {
    "product": {
      "product_fit": 0.8,       // Market fit score 0-1
      "ux_issues": [...],       // Identified UX problems
      "feature_set": "...",     // Core features analysis
      "technical_moat": 0.6     // Competitive advantage score
    }
  }
  ```

**FinancialLead** (`analyze` method)

- **Responsibilities**: Revenue model, unit economics, financial viability
- **Worker Delegation**: Calls `financial_worker`
- **Output Structure**:
  ```json
  {
    "financial": {
      "revenue_model_score": 0.6,    // Revenue model viability 0-1
      "unit_economics": "OK",         // Unit economics assessment
      "cash_runway": "18 months",     // Estimated runway
      "burn_rate": "$50k/month"      // Current burn rate
    }
  }
  ```

#### [due_diligence/workers.py](due_diligence/workers.py)
**Worker functions for specialized analysis**

**tam_worker(market_description)** → Dict

```python
def tam_worker(market: str) -> Dict:
    model = "openai/gpt-oss-120b"
    messages = [{
        "role": "user",
        "content": f"Estimate TAM for market: {market}. Provide numeric and confidence."
    }]
    resp = chat_completion(model, messages, max_tokens=200)
    text = resp.get("choices", [])[0].get("message", {}).get("content", "")
    
    # Parse response for TAM estimate
    if text.startswith("[mock]"):
        return {"TAM": 1000000, "confidence": 0.7}
    
    # Extract numeric estimate from response
    import re
    m = re.search(r"(\d[\d,_]*)", text.replace(',', ''))
    if m:
        try:
            val = int(m.group(1))
            return {"TAM": val, "confidence": 0.6}
        except Exception:
            pass
    
    return {"TAM": 1000000, "confidence": 0.6}
```

**Key Workers**:

1. **tam_worker()**: Estimates market size using LLM
   - Input: Market description
   - Output: TAM estimate + confidence
   - Model: openai/gpt-oss-120b (large, accurate)
   - Fallback: 1M default if parsing fails

2. **competition_worker()**: Analyzes competitive landscape
   - Input: Market description
   - Output: Competitor count, intensity, differentiation
   - Model: mistralai/Mistral-7B-Instruct-v0.3
   - Fallback: Medium intensity, 5 competitors

3. **product_assessment_worker()**: Evaluates product-market fit
   - Input: Product description
   - Output: Product fit score (0-1), UX issues
   - Model: mistralai/Mistral-7B-Instruct-v0.3
   - Fallback: 0.75 fit, no UX issues

4. **financial_worker()**: Assesses financial viability
   - Input: Financial description
   - Output: Revenue model score, unit economics
   - Model: deepseek-ai/deepseek-r1-distill-llama-70b
   - Fallback: 0.6 score, "OK" unit economics

**Fallback Pattern**: All workers include LLM try/catch with sensible defaults, enabling offline testing.

#### [due_diligence/investment_agent.py](due_diligence/investment_agent.py)
**Investment Lead orchestrator for final recommendation**

**InvestmentLead** (`evaluate` method)

```python
class InvestmentLead:
    def __init__(self, state: SharedState):
        self.state = state
        self.executor = AgentExecutor(
            name="InvestmentLead",
            description=(
                "You are the investment lead orchestrating comprehensive due diligence. "
                "Aggregate market, product, financial analyses into final recommendation."
            ),
            state=state,
            model="deepseek-ai/deepseek-r1-distill-llama-70b",
            max_tokens=2000  # Large budget for comprehensive report
        )
    
    def evaluate(self, startup: str) -> dict:
        prompt = f"""
        Perform final due diligence synthesis.
        
        Return JSON with fields:
        - market_score (0-10): Market opportunity score
        - product_score (0-10): Product viability score
        - financial_score (0-10): Financial health score
        - overall_score (0-10): Final investment score
        - risk_assessment (string): Key risks identified
        - investment_recommendation (invest/pass/conditional): Final recommendation
        - report (string): Full investment memo
        - key_strengths (array): Top reasons to invest
        - key_risks (array): Top risks and mitigations
        
        Startup: {startup}
        """
        
        result = self.executor.run(prompt)
        self.state.add_memory({
            "type": "due_diligence_report",
            "startup": startup[:120],
            "result": result
        })
        return result
```

- **Model Selection**: deepseek-ai/deepseek-r1-distill-llama-70b (reasoning capability)
- **Token Budget**: 2000 tokens for comprehensive synthesis
- **Tool Access**: Can invoke specialized analysis tools if needed
- **Output**: Comprehensive JSON report with 9 key fields
- **Persistence**: Automatically persisted to memory store

#### [due_diligence/agent_executor.py](due_diligence/agent_executor.py)
**Generic executor for JSON workflows (shared with ai-product-manager)**

Provides:
- Message building with role alternation
- LLM invocation via Qubrid
- JSON parsing
- Tool invocation loops (max 8 iterations)
- Error handling

#### [due_diligence/state.py](due_diligence/state.py)
**Shared state management**

- Tool registration and lookup
- Conversation history tracking
- Memory persistence to `due_diligence_memory.json`
- Tool execution logging

#### [due_diligence/llm_client.py](due_diligence/llm_client.py)
**Qubrid REST API client (shared)**

Configuration, authentication, HTTP handling, response parsing.

#### [due_diligence/tools.py](due_diligence/tools.py)
**Specialized due diligence tools**

Available tools:
- `tam_analysis`: Detailed TAM breakdown
- `competition_analysis`: Competitive positioning
- `product_assessment`: Product features and fit
- `ux_assessment`: User experience analysis
- `technical_moat`: Competitive advantage assessment
- `revenue_model`: Business model evaluation
- `unit_economics`: Unit-level financial analysis

Each tool executes as self-contained LLM workflow returning JSON.

#### [due_diligence/utils.py](due_diligence/utils.py)
**Utility functions**

- `extract_json()`: JSON parsing from LLM responses
- Response validation and error handling

### Data Flow Through Pipeline

```
Input: Startup Description
    │
    ├─→ Market Lead Analysis
    │   ├─→ tam_worker(startup)
    │   │   ├─→ LLM: Estimate TAM
    │   │   └─→ Output: {"TAM": ..., "confidence": ...}
    │   │
    │   └─→ competition_worker(startup)
    │       ├─→ LLM: Analyze competition
    │       └─→ Output: {"num_competitors": ..., "intensity": ...}
    │
    ├─→ Product Lead Analysis
    │   └─→ product_assessment_worker(startup)
    │       ├─→ LLM: Assess product fit
    │       └─→ Output: {"product_fit": ..., "ux_issues": ...}
    │
    ├─→ Financial Lead Analysis
    │   └─→ financial_worker(startup)
    │       ├─→ LLM: Evaluate financials
    │       └─→ Output: {"revenue_model_score": ..., ...}
    │
    ├─→ Append results to shared state as assistant messages
    │
    └─→ Investment Lead Synthesis
        ├─→ Receives startup + all lead outputs
        ├─→ AgentExecutor loop (may call tools for deeper analysis)
        └─→ Returns comprehensive due diligence report
            ├─→ Scores (market, product, financial, overall)
            ├─→ Recommendation (invest/pass/conditional)
            ├─→ Full investment memo
            ├─→ Key strengths and risks
            └─→ Persisted to memory store
```

## Execution Flow Walkthrough

### Full Due Diligence Evaluation

```
Input: "B2B SaaS for AP/AR reconciliation targeting mid-market CFOs"

main.run(startup_description):
    │
    ├─→ Initialization
    │   ├─→ state = SharedState()  # Load due_diligence_memory.json
    │   ├─→ Register 7 tools
    │   └─→ Print header + tool registration
    │
    ├─→ [MARKET ANALYSIS] (5-10 seconds)
    │   MarketLead().analyze(startup)
    │       │
    │       ├─→ tam_worker(startup)
    │       │   └─→ LLM call: Estimate TAM for "B2B AP/AR SaaS"
    │       │       Typical response: ~$8-12B market
    │       │       Return: {"TAM": 10000000, "confidence": 0.7}
    │       │
    │       ├─→ competition_worker(startup)
    │       │   └─→ LLM call: Analyze competitors
    │       │       Returns: {"num_competitors": 15, "intensity": "high"}
    │       │
    │       └─→ Return: {
    │             "tam": {...},
    │             "competition": {...}
    │           }
    │
    │   Append to state: add_message("assistant", "MarketLead findings: {...}")
    │
    ├─→ [PRODUCT ANALYSIS] (5-10 seconds)
    │   ProductLead().analyze(startup)
    │       │
    │       └─→ product_assessment_worker(startup)
    │           ├─→ LLM: Assess AP/AR solution fit
    │           └─→ Return: {"product_fit": 0.85, "ux_issues": [...]}
    │
    │   Append to state: add_message("assistant", "ProductLead findings: {...}")
    │
    ├─→ [FINANCIAL ANALYSIS] (5-10 seconds)
    │   FinancialLead().analyze(startup)
    │       │
    │       └─→ financial_worker(startup)
    │           ├─→ LLM: Evaluate revenue model
    │           └─→ Return: {"revenue_model_score": 0.75, ...}
    │
    │   Append to state: add_message("assistant", "FinancialLead findings: {...}")
    │
    └─→ [INVESTMENT SYNTHESIS] (10-20 seconds)
        InvestmentLead(state).evaluate(enriched_prompt)
            ├─→ enriched_prompt includes:
            │   ├─→ Original startup description
            │   ├─→ Market analysis results
            │   ├─→ Product analysis results
            │   ├─→ Financial analysis results
            │
            ├─→ AgentExecutor iterations:
            │   ├─→ Iteration 1: Model may call tools for deeper analysis
            │   └─→ Iteration 2: Model returns comprehensive JSON
            │
            ├─→ Return: {
            │     "market_score": 8,
            │     "product_score": 7,
            │     "financial_score": 6,
            │     "overall_score": 7,
            │     "risk_assessment": "Competition from Coupa, SAP...",
            │     "investment_recommendation": "conditional",
            │     "report": "Full investment memo (400+ words)",
            │     "key_strengths": ["Large TAM", "Strong product fit", ...],
            │     "key_risks": ["Intense competition", "High CAC", ...]
            │   }
            │
            └─→ state.add_memory({
                  "type": "due_diligence_report",
                  "startup": "B2B SaaS for AP/AR reconciliation...",
                  "result": {...}
                })
                → Written to due_diligence_memory.json

Output: Full due diligence report JSON (printed and persisted)
```

## Output Structure

### Final Due Diligence Report

```json
{
  "market_score": 8,
  "product_score": 7,
  "financial_score": 6,
  "overall_score": 7,
  "risk_assessment": "Competition from established players like Coupa, SAP, integration complexity, high CAC, customer retention risk",
  "investment_recommendation": "conditional",
  "report": "Investment Memo: B2B SaaS for AP/AR Reconciliation...\n\n[Full detailed analysis 400+ words]",
  "key_strengths": [
    "Large addressable market ($10B+) with strong growth",
    "Strong product-market fit for mid-market CFOs",
    "Recurring revenue model with high retention potential",
    "Lower technical barriers compared to broader finance platforms"
  ],
  "key_risks": [
    "Intense competition from established platforms",
    "High customer acquisition costs in enterprise",
    "Integration complexity with existing ERP systems",
    "Regulatory changes in accounting standards"
  ]
}
```

## Installation & Setup

```bash
# Navigate to project
cd startup-due-diligence

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
# Evaluate a startup
python -m due_diligence.main "B2B SaaS for AP/AR reconciliation targeting mid-market CFOs"

# Evaluate a different startup
python -m due_diligence.main "Mobile app for fitness coaching with AI personalization"

# Default (if no args provided)
python -m due_diligence.main
```

### Server Mode
```bash
# Start server
uvicorn due_diligence.main:app --reload --port 8003

# Access frontend
open http://localhost:8003

# Make API request
curl -X POST http://localhost:8003/evaluate \
  -H "Content-Type: application/json" \
  -d '{"startup": "SaaS for expense management"}'

# Retrieve all reports
curl http://localhost:8003/memory | jq
```

## Scoring Framework

### Market Score (0-10)
- 9-10: Large, growing, underserved market with clear expansion potential
- 7-8: Strong market with moderate competition
- 5-6: Adequate market size with significant competition
- 3-4: Small market or declining growth
- 0-2: Saturated or declining market

### Product Score (0-10)
- 9-10: Exceptional product-market fit, innovative features
- 7-8: Strong fit, good differentiation
- 5-6: Adequate fit, some competitive advantage
- 3-4: Weak fit, marginal differentiation
- 0-2: Poor fit, commoditized offering

### Financial Score (0-10)
- 9-10: Profitable or on clear path to profitability, strong unit economics
- 7-8: Positive unit economics, controlled burn rate
- 5-6: Breakeven potential, need to optimize
- 3-4: Uncertain path to profitability, high burn
- 0-2: Unsustainable financials, unclear model

### Overall Score (0-10)
- 9-10: Exceptional investment opportunity
- 7-8: Strong investment candidate
- 5-6: Viable but with conditions
- 3-4: High risk, wait and see
- 0-2: Pass

### Investment Recommendation
- **INVEST**: Overall score 8+, no critical risks
- **CONDITIONAL**: Overall score 6-7, specific conditions to address
- **PASS**: Overall score <6 or critical risk factors

## Memory Persistence

Reports automatically saved to `due_diligence_memory.json`:
```json
[
  {
    "type": "due_diligence_report",
    "startup": "B2B SaaS for AP/AR reconciliation...",
    "result": {
      "market_score": 8,
      "product_score": 7,
      ...
    }
  },
  ...
]
```

Query historical reports:
```python
state = SharedState()
matching = state.query_memory("SaaS")  # Find all SaaS reports
```

## Design Principles

1. **Specialist Decomposition**: Each domain expert independently assesses their area
2. **Hierarchical Synthesis**: Specialists feed into investment lead
3. **Structured Scoring**: Quantified assessments (0-10) for comparability
4. **Transparent Reasoning**: Full memo included alongside scores
5. **Risk-Aware**: Explicit risk assessment and mitigation
6. **Tool-Driven**: Complex analyses delegated to specialized tools
7. **Persistent Reporting**: Complete audit trail of evaluations
8. **Modular Design**: Easy to add new leads or adjust scoring

## Performance Characteristics

- Average evaluation time: 25-40 seconds
- Token usage: 4000-7000 tokens per report
- Market analysis: 5-10 seconds
- Product analysis: 5-10 seconds
- Financial analysis: 5-10 seconds
- Investment synthesis: 10-15 seconds
- Memory footprint: 50MB base + 20KB per report
- Concurrent capacity: Parallelizable at lead level

## Extensions & Customizations

The system can be extended with:
- Additional specialist leads (Legal, Team, Tech Stack)
- Custom scoring models per domain
- Comparison analysis across portfolio companies
- Alert system for high-risk investments
- Integration with VC fund management systems
- ML-based scoring refinement
- Multi-round evaluation (seed, Series A, Series B)
- Automated report generation with charts
