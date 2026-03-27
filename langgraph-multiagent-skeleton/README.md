# LangGraph Multi-Agent Skeleton

A **starter template** for building multi-agent applications with [LangGraph](https://github.com/langchain-ai/langgraph), Streamlit, and Pydantic. Clone this skeleton and adapt it to your domain — the architectural patterns are already wired up and working.

## What's Inside

A runnable "Research Assistant" demo that decomposes a question into sub-questions, researches each with tools, synthesizes findings, and reviews quality — exercising every pattern you'll need in a production multi-agent system:

```
User question
    │
    ▼
┌─────────┐     ┌────────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────┐
│  init    │────▶│  planner   │────▶│  researcher  │────▶│ synthesizer│────▶│ reviewer │──▶ finalize
│  (load   │     │  (decompose│     │  (tool calls │     │ (merge     │     │ (quality │
│  config) │     │  question) │     │   per sub-Q) │     │  findings) │     │  gate)   │
└─────────┘     └────────────┘     └──────┬───────┘     └─────┬──────┘     └────┬─────┘
                                          │ loop              │                  │
                                          └──────────┐        │ retry if         │
                                                     ▼        │ review fails     │
                                               has_more? ─────┘                  │
                                                                        should_retry?
```

## Directory Structure

```
langgraph-multiagent-skeleton/
├── README.md                       ← You are here
├── PATTERNS.md                     ← Design decisions & trade-offs
├── pyproject.toml                  ← Dependencies & packaging
├── Dockerfile                      ← Container deployment
│
├── config/
│   └── default.yaml                ← Domain configuration (quality criteria, topics, limits)
│
├── src/skeleton/
│   ├── __init__.py                 ← Package version
│   ├── exceptions.py               ← AgentError, TransportError, ValidationError
│   │
│   ├── core/                       ← Foundation layer (no agent/graph imports)
│   │   ├── config.py               ← AppConfig + DomainConfig + YAML loader
│   │   ├── models.py               ← Domain data models (Finding, Summary, ReviewResult)
│   │   ├── state.py                ← Re-exports for convenient graph-node imports
│   │   ├── events.py               ← EventType, PipelineEvent, EventEmitter, EventListener
│   │   └── transport.py            ← Async LLM client (OpenAI/Anthropic, retry, URL discovery)
│   │
│   ├── agents/                     ← Agent definitions
│   │   ├── base.py                 ← BaseAgent ABC, AgentContext, call_llm*, @register_agent
│   │   ├── planner.py              ← PlannerAgent: question → sub-questions
│   │   ├── researcher.py           ← ResearcherAgent: sub-question → finding (uses tools)
│   │   ├── synthesizer.py          ← SynthesizerAgent: findings → summary
│   │   └── reviewer.py             ← ReviewerAgent: summary → pass/fail + issues
│   │
│   ├── tools/                      ← Tool definitions & execution
│   │   ├── schemas.py              ← OpenAI function-calling JSON schemas
│   │   ├── implementations.py      ← Tool bodies + build_tool_executor() factory
│   │   └── nodes.py                ← Standalone LangGraph ToolNode (alternative pattern)
│   │
│   ├── graphs/                     ← LangGraph orchestration
│   │   ├── state.py                ← ResearchState TypedDict with Annotated[list, add] reducers
│   │   └── research_graph.py       ← 7-node graph: init→plan→research→synthesize→review→finalize
│   │
│   ├── validation/
│   │   └── validator.py            ← Deterministic rules with typed failure codes
│   │
│   ├── export/
│   │   └── markdown.py             ← Export findings + summary to Markdown
│   │
│   └── ui/
│       └── app.py                  ← Streamlit UI with live progress & graph invocation
│
└── tests/
    ├── conftest.py                 ← Mock transport, sample config fixtures
    ├── test_agents.py              ← Agent tests (deterministic mode)
    ├── test_graph.py               ← Full graph integration test
    ├── test_tools.py               ← Tool executor tests
    └── test_validator.py           ← Validation rule tests
```

## Getting Started

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Run Without an LLM (Deterministic Mode)

Every agent has a deterministic fallback path. No API keys needed:

```bash
# Run the graph from Python
python3 -c "
from skeleton.graphs.research_graph import build_graph
result = build_graph().invoke({
    'question': 'What is LangGraph?',
    'config_path': 'config/default.yaml',
})
print(result['final_report']['summary']['text'][:200])
"

# Run the Streamlit UI
streamlit run src/skeleton/ui/app.py
```

### 3. Run With an LLM

Set one of these environment variable pairs:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o          # optional, defaults to gpt-4o

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-20250514  # optional
```

Then run the same commands — agents will use the LLM with deterministic fallbacks on failure.

### 4. Run Tests

```bash
python3 -m pytest tests/ -v
```

### 5. Docker

```bash
docker build -t research-skeleton .
docker run -p 8501:8501 -e OPENAI_API_KEY=sk-... research-skeleton
```

## How to Adapt to Your Domain

Every file has `# CUSTOMIZE:` markers showing where to make changes. Here's the recommended order:

### Step 1: Define Your Domain Models

Edit `src/skeleton/core/models.py` — replace `SubQuestion`, `Finding`, `Summary`, `ReviewResult` with your domain types. Keep them frozen (immutable) so agents can't mutate each other's outputs.

### Step 2: Write Your Config

Edit `config/default.yaml` and `src/skeleton/core/config.py` — replace research-specific fields with your domain knowledge (taxonomy, rules, criteria, etc.). The `DomainConfig` is the single source of truth consumed by all agents and tools.

### Step 3: Implement Your Agents

Each agent in `src/skeleton/agents/` follows the same pattern:
- Subclass `BaseAgent` and implement `async execute(**kwargs) → dict`
- Use `call_llm()` for simple prompts or `call_llm_with_tools()` for tool-calling agents
- Always provide a deterministic fallback when `self.context.client is None`

### Step 4: Add Your Tools

Define OpenAI-format schemas in `tools/schemas.py`, implement bodies in `tools/implementations.py`, and register in `build_tool_executor()`. Agents receive tools via the executor closure — they never import tool implementations directly.

### Step 5: Wire Your Graph

Edit `graphs/state.py` (TypedDict fields) and `graphs/research_graph.py` (nodes, edges, conditional routing). The graph builder is a factory function returning `CompiledGraph` — the UI calls `build_graph().invoke(input_state)`.

### Step 6: Update the UI

Edit `ui/app.py` — change the layout, widgets, and result rendering. Keep the three patterns: `graph.invoke()` for execution, `StreamlitEventListener` for live progress, `st.session_state` for persistence.

## Key Architectural Patterns

See [PATTERNS.md](PATTERNS.md) for detailed documentation of the six core patterns:

1. **LangGraph Orchestration** — state machines, conditional routing, reducers
2. **Agent Communication** — shared state, frozen results, locked fields
3. **Tool Integration** — executor closures, JSON schemas, multi-round loops
4. **Abstraction Boundaries** — protocols, ABCs, transport clients
5. **UI ↔ Backend Contract** — graph.invoke(), event listeners, session state
6. **Config-Driven Behavior** — YAML → Pydantic, single-source-of-truth
