# Architectural Patterns

This document describes the six core design patterns in this skeleton, why each
decision was made, and the trade-offs involved.  Every pattern was extracted from
a production multi-agent LangGraph application and generalized for reuse.

---

## Pattern 1: LangGraph Orchestration

### What It Is

The execution graph is a **typed state machine** built with LangGraph's
`StateGraph`.  Nodes are plain Python functions that read/write a shared
`TypedDict` state.  Edges can be *unconditional* (always go from A to B) or
*conditional* (a Python function inspects the state and returns the name of the
next node).

### Key Implementation Details

```python
# State definition — graphs/state.py
class ResearchState(TypedDict, total=False):
    findings: Annotated[list[dict], operator.add]  # ← reducer
    current_idx: int
    ...

# Graph definition — graphs/research_graph.py
graph = StateGraph(ResearchState)
graph.add_node("research", research_node)
graph.add_conditional_edges("research", has_more_questions)
compiled = graph.compile()
result = compiled.invoke(input_state)
```

### The `Annotated[list, add]` Reducer

When multiple nodes contribute items to the same list (e.g., findings produced
in a loop), a naïve dict update would *overwrite* the list.  LangGraph's
`Annotated[list, operator.add]` tells the framework to *concatenate* partial
updates instead.

**Without reducer:** Node returns `{"findings": [new_item]}` → replaces entire list.  
**With reducer:** Node returns `{"findings": [new_item]}` → appends to existing list.

### Module-Level Caches

LLM clients and agent instances are cached at module level:

```python
_llm_client_cache = None
_agent_cache: dict[str, Any] = {}
```

**Why:** Each graph node is a fresh function call.  Without caching, every node
would create a new HTTP client (TCP handshake) and agent instance (prompt
recompilation).  Caching amortizes startup cost across all nodes in a run.

**Trade-off:** Module-level state makes testing harder.  The skeleton provides
`reset_caches()` for test isolation.

### Conditional Routing

```python
def has_more_questions(state) -> str:
    if state["current_idx"] < len(state["sub_questions"]):
        return "research"      # loop back
    return "synthesize"        # proceed
```

Edge functions return a **node name** (string).  This is more explicit than
magic routing — you can read the graph topology from the code.

### Trade-offs

| Decision | Pro | Con |
|----------|-----|-----|
| TypedDict state (not Pydantic) | Matches LangGraph's dict semantics | No runtime validation on state updates |
| Module-level caches | Fast, avoids reconnects | Need explicit reset in tests |
| Sync nodes calling async agents | Compatible with LangGraph's sync `.invoke()` | Requires `asyncio.run_until_complete()` bridge |
| Factory function `build_graph()` | Easy to test, no global graph | Slight indirection |

---

## Pattern 2: Agent ↔ Agent Communication

### What It Is

Agents **never talk directly** to each other.  All communication happens through
the shared graph state.  Each agent reads the fields it needs and writes a
frozen result dict.  Downstream agents see upstream outputs as read-only
snapshots.

### The Frozen-Result Pattern

```python
class Finding(BaseModel, frozen=True):
    sub_question: str
    answer: str
    sources: list[str]
    confidence: float
```

`frozen=True` means once a `Finding` is created, its fields can't be modified.
This prevents subtle bugs where a downstream agent accidentally mutates an
upstream result in shared state.

### State Threading (not Message Passing)

Unlike frameworks that use message queues between agents, LangGraph threads
state through nodes:

```
plan_node(state) → {"sub_questions": [...]}
research_node(state) → {"findings": [new_finding]}  # reads sub_questions, writes findings
synthesize_node(state) → {"summary": {...}}          # reads findings, writes summary
```

**Advantage:** All context is available in one dict — agents don't need to know
about message routing or queues.

**Disadvantage:** State can grow large.  For very large pipelines, consider
trimming state between stages.

### Locked Fields

In production workflows, some fields are "locked" by an upstream agent and must
not be changed by downstream agents.  Example: a SpecAgent locks `who` and
`where`, and the NarrativeAgent must use those exact values.  This isn't
enforced structurally in the skeleton (for simplicity), but the pattern is
documented in agents via prompt instructions.

---

## Pattern 3: Tool Integration

### What It Is

Agents call tools through a **closure** that captures configuration at creation
time.  Agents never import tool implementations directly.

```python
# Build once, pass to agents
executor = build_tool_executor(config)

# Agent calls tools by name
result = executor("web_search", {"query": "LangGraph"})
```

### The Executor Closure

```python
def build_tool_executor(config: DomainConfig):
    def executor(tool_name: str, args: dict) -> dict:
        fn = _TOOL_TABLE.get(tool_name)
        if fn is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return fn(config, **args)
    return executor
```

**Why closures:** Agents are decoupled from configuration storage.  In tests,
inject a mock executor.  In production, the executor captures the real
`DomainConfig`.

### Multi-Round Tool Loop

`BaseAgent.call_llm_with_tools()` implements a loop:

1. Send messages + tool schemas to LLM
2. If LLM returns `tool_calls`, execute each one
3. Append tool results as `{role: "tool"}` messages
4. Re-prompt the LLM
5. Repeat until LLM returns text (no more tool calls) or `max_tool_rounds` hit

### JSON Schemas

Tools are defined as OpenAI function-calling schemas:

```python
{
    "type": "function",
    "function": {
        "name": "web_search",
        "parameters": {"type": "object", "properties": {...}, "required": [...]}
    }
}
```

**Advantage:** Portable across LLM providers.  
**Alternative:** The skeleton also provides a standalone `ToolNode` (in
`tools/nodes.py`) for graphs that separate "agent decision" and "tool
execution" into distinct graph nodes.

### Trade-offs

| Decision | Pro | Con |
|----------|-----|-----|
| Closure-based executor | Testable, config-injected, agents are clean | One more level of indirection |
| Self-contained tool loop in BaseAgent | Simple for most use cases | Harder to observe individual tool calls from outside |
| OpenAI schema format | Standard, well-documented | Vendor-specific (though widely adopted) |

---

## Pattern 4: Abstraction Boundaries

### Interfaces

| Interface | Type | Purpose |
|-----------|------|---------|
| `EventListener` | `Protocol` | Any callable `(PipelineEvent) → None` can observe events |
| `BaseAgent` | `ABC` | Uniform agent contract: `async execute(**kwargs) → dict` |
| `AsyncTransportClient` | `dataclass` | Provider-agnostic LLM calls |
| `build_tool_executor()` | Closure factory | Decouples agents from tool storage |

### Protocol vs. ABC

- **Protocols** (structural typing) — use when you want zero coupling.
  `EventListener` is a Protocol: any function with the right signature works.
  No base class to inherit from.
- **ABCs** (nominal typing) — use when you want shared implementation.
  `BaseAgent` is an ABC: it provides `call_llm()`, `parse_json()`, etc.

### Transport Abstraction

`AsyncTransportClient` wraps `httpx` and speaks the OpenAI chat-completions API.
It handles:
- Multiple URL candidates (for reverse proxies)
- Exponential backoff on 429/5xx
- Immediate failure on 401/403
- `build_client_from_env()` auto-detects provider from env vars

**To add a new provider:** Extend `build_client_from_env()` with a new env-var
check.  If the provider speaks OpenAI-compatible API, no other changes needed.

---

## Pattern 5: UI ↔ Backend Contract

### The Contract

The UI talks to the backend through exactly two mechanisms:

1. **`graph.invoke(input_state) → final_state`** — synchronous, blocking call.
   The UI builds an input dict, the graph returns a result dict.
2. **`EventEmitter` + `StreamlitEventListener`** — fire-and-forget progress
   updates.  The UI wires a listener before calling `invoke()`.

### Event-Driven Progress

```python
# UI side
emitter = EventEmitter()
listener = StreamlitEventListener(progress_container)
emitter.on(listener)
set_emitter(emitter)

# Graph side (inside any node)
_emit(EventType.AGENT_STARTED, "ResearcherAgent started")
```

Each event is mapped to an emoji + status line:

```python
_EVENT_EMOJI = {
    EventType.PIPELINE_STARTED: "🚀",
    EventType.AGENT_STARTED: "🤖",
    EventType.AGENT_COMPLETED: "✔️",
    ...
}
```

### Session State

Streamlit reruns the complete script on every widget interaction.  All state
that must survive across reruns lives in `st.session_state`:

```python
st.session_state["final_report"] = result.get("final_report")
```

### Trade-offs

| Decision | Pro | Con |
|----------|-----|-----|
| Module-level `set_emitter()` | Simple, no dependency injection framework | Global state, harder to test |
| Blocking `graph.invoke()` | Streamlit-friendly (no async needed in UI) | UI thread blocked during execution |
| Event → emoji mapping in UI | Decoupled from backend event types | Must update mapping when adding events |

---

## Pattern 6: Config-Driven Behavior

### Two Config Types

| Config | Lives In | Changes When | Contains |
|--------|----------|-------------|----------|
| `AppConfig` | Code defaults / env vars | Deployment changes | Model name, temperature, max tokens, timeout |
| `DomainConfig` | `config/*.yaml` | Domain changes | Quality criteria, topic areas, word limits |

### Single Source of Truth

`DomainConfig` is loaded once and passed (or sliced) to every agent and tool.
Agents never read YAML or environment variables directly.

```
YAML file → load_config() → DomainConfig → build_tool_executor(config) → agents
```

### YAML → Pydantic Validation

```python
class DomainConfig(BaseModel):
    max_sub_questions: int = Field(ge=1, le=20, default=5)
    quality_criteria: list[str] = Field(default_factory=list)
```

Invalid configs fail at load time with clear error messages, not at runtime deep
inside an agent.

### Trade-offs

| Decision | Pro | Con |
|----------|-----|-----|
| YAML for domain config | Human-editable, version-controllable | No IDE auto-complete (use JSON Schema for that) |
| Pydantic for runtime models | Validation, serialization, IDE support | Extra layer between YAML and usage |
| No in-memory caching of config | Simple, testable, supports hot-reload | Slightly slower (re-parse on each load) |

---

## Advanced Patterns (Not in Skeleton)

These patterns exist in the source project but were omitted from the skeleton
for simplicity.  Add them when your project needs them.

### Fan-Out / Fan-In Graph

Run multiple analysis nodes in parallel, each writing to a shared list with
`Annotated[list, add]`:

```python
graph.add_edge("load", "scanner_a")
graph.add_edge("load", "scanner_b")
graph.add_edge("load", "scanner_c")
graph.add_edge(["scanner_a", "scanner_b", "scanner_c"], "merge")
```

### Vector Memory (ChromaDB)

Add semantic deduplication with an embedding protocol:

```python
class Embedder(ABC):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def dimension(self) -> int: ...

class ControlMemory:
    def query_similar(self, text: str, n: int = 5) -> list[dict]: ...
    def check_duplicate(self, text: str, threshold: float = 0.92) -> bool: ...
```

### XML Tool Calling Fallback

For LLM providers that don't support OpenAI function calling natively, parse
XML-formatted tool calls from the response:

```python
def parse_xml_tool_calls(text: str) -> list[dict]:
    # Extract <tool_call><name>...</name><arguments>...</arguments></tool_call>
```

### Multi-Tenant Config Isolation

Use a per-tenant config directory structure:

```
config/
├── profiles/
│   ├── tenant_a.yaml
│   └── tenant_b.yaml
└── sections/
    ├── section_1.yaml
    └── section_2.yaml
```

### Adversarial Review Loop

Chain a "red team" reviewer agent that critiques output before acceptance,
routing failures back to the generating agent with specific feedback codes.

---

## Anti-Patterns to Avoid

1. **Agents importing agents** — agents should communicate only through graph
   state, never by calling each other directly.
2. **Tools with side effects in shared state** — tools should be pure functions
   or clearly scoped to a request. Don't use tools to mutate graph state.
3. **LLM calls in validators** — validators should be deterministic. Use
   failure codes for agent feedback, not LLM interpretation.
4. **Giant monolithic state** — split state into logical sections. Use type
   aliases for complex nested structures.
5. **Hardcoded prompts** — move prompt templates to config or constants at
   module level, not buried inside agent methods.
