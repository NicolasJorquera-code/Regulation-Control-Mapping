# ControlNexus Architecture

This document provides an in-depth technical breakdown of the ControlNexus system architecture, covering data models, pipeline flows, agent design, graph orchestration, and infrastructure.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Core Data Models](#2-core-data-models)
3. [Configuration System](#3-configuration-system)
4. [Analysis Layer](#4-analysis-layer)
5. [Remediation Layer](#5-remediation-layer)
6. [Agent Architecture](#6-agent-architecture)
7. [LangGraph Orchestration](#7-langgraph-orchestration)
8. [Memory Layer (ChromaDB)](#8-memory-layer-chromadb)
9. [Tool Function Calling](#9-tool-function-calling)
10. [Validation Engine](#10-validation-engine)
11. [Transport Layer](#11-transport-layer)
12. [Streamlit Dashboard](#12-streamlit-dashboard)
13. [Testing Strategy](#13-testing-strategy)
14. [Deployment Architecture](#14-deployment-architecture)

---

## 1. System Overview

ControlNexus is a three-layer system for managing internal financial controls:

```
                    +------------------+
                    |   Streamlit UI   |  <-- Layer 3: Dashboard (HITL)
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
    +---------v----------+     +------------v-----------+
    |   Analysis Layer   |     |   Remediation Layer    |  <-- Layers 1 & 2
    |  (4 scanners)      |     |  (multi-agent LLM)     |
    +--------------------+     +------------------------+
              |                             |
    +---------v-----------------------------v-----------+
    |              Core Data Models & Config            |
    +---------------------------------------------------+
    |     ChromaDB Memory  |  LLM Transport  |  Tools   |
    +---------------------------------------------------+
```

### Design Principles

- **Deterministic first:** Every LLM-dependent path has a pure-Python fallback. The system produces useful output without any API keys.
- **Pydantic everywhere:** All data structures are Pydantic v2 models with `ConfigDict(frozen=True)` on immutable types.
- **Async by default:** All agents use `async def execute()` and `async def call_llm()`. The transport layer is built on `httpx.AsyncClient`.
- **Graph-native:** Both analysis and remediation pipelines are LangGraph `StateGraph` instances with typed state, fan-out/fan-in parallelism, and conditional routing.

---

## 2. Core Data Models

**File:** `src/controlnexus/core/state.py`

The data model hierarchy follows the control lifecycle:

```
HierarchyNode          APQC process tree node
    |
ControlAssignment      (hierarchy_id, control_type, BU) triple
    |
SpecResult             Locked specification from SpecAgent
    |
NarrativeResult        5W prose from NarrativeAgent
    |
EnrichmentResult       Quality-rated enrichment from EnricherAgent
    |
ValidationResult       6-rule pass/fail from Validator (frozen)
    |
FinalControlRecord     22-field export-ready record
```

### FinalControlRecord (22 fields)

The central data type. Contains:
- **Identity:** `control_id`, `hierarchy_id`, `leaf_name`
- **Classification:** `control_type`, `selected_level_1`, `selected_level_2`, `business_unit_id`, `business_unit_name`
- **Placement:** `placement` (Preventive/Detective/Corrective), `method` (Manual/Automated/Semi-automated)
- **5W Narrative:** `who`, `what`, `when`, `frequency`, `where`, `why`, `full_description`
- **Quality:** `quality_rating`, `validator_passed`, `validator_retries`, `validator_failures`
- **Evidence:** `evidence`

The `to_export_dict()` method returns a 19-key subset matching the Excel export column schema.

### Gap Models

Analysis produces four typed gap models:

| Model | Fields | Source Scanner |
|-------|--------|----------------|
| `RegulatoryGap` | framework, required_theme, current_coverage, severity | `regulatory_coverage_scan` |
| `BalanceGap` | control_type, expected_pct, actual_pct, direction | `ecosystem_balance_analysis` |
| `FrequencyIssue` | control_id, hierarchy_id, expected/actual_frequency | `frequency_coherence_scan` |
| `EvidenceIssue` | control_id, hierarchy_id, issue | `evidence_sufficiency_scan` |

These aggregate into `GapReport` with an `overall_score` (0--100) computed from weighted dimension scores.

---

## 3. Configuration System

**File:** `src/controlnexus/core/config.py`

All configuration is YAML-based in the `config/` directory:

### taxonomy.yaml
Defines the control type taxonomy with L1/L2 hierarchies:
```yaml
control_types:
  - level_1: Preventive
    level_2: [Authorization, Segregation of Duties, ...]
  - level_1: Detective
    level_2: [Reconciliation, Variance Analysis, ...]
```

### standards.yaml
Contains 5W quality standards, phrase banks, and quality rating definitions used by the NarrativeAgent and Validator.

### placement_methods.yaml
Maps placement types (Preventive/Detective/Corrective) to valid methods (Manual/Automated/Semi-automated) with the full taxonomy hierarchy.

### sections/section_{1-13}.yaml
Per-section profiles containing:
- **AffinityMatrix:** Expected control type distribution percentages
- **Registry:** Roles, systems, regulatory frameworks, and keywords
- **Exemplars:** Gold-standard control examples per type

Loader functions: `load_section_profile()`, `load_all_section_profiles()`, `load_taxonomy_catalog()`, `load_standards()`, `load_placement_methods()`.

---

## 4. Analysis Layer

### Ingest (`analysis/ingest.py`)

```
Excel File (.xlsx)
    |
    v
openpyxl.load_workbook(read_only=True)
    |
    v
For each sheet matching "section_*":
    Parse header row -> column mapping
    For each data row:
        Type coercion (_coerce_bool, _coerce_int, _parse_failures)
        -> FinalControlRecord
    |
    v
list[FinalControlRecord]
```

Handles: missing columns, string-encoded lists (`"['X','Y']"`), boolean strings, and null values.

### Pipeline (`analysis/pipeline.py`)

Orchestrates four independent scanners:

```
controls + section_profiles
    |
    +---> regulatory_coverage_scan()    Weight: 40%
    +---> ecosystem_balance_analysis()  Weight: 25%
    +---> frequency_coherence_scan()    Weight: 15%
    +---> evidence_sufficiency_scan()   Weight: 20%
    |
    v
Weighted score = sum(weight_i * score_i)
    |
    v
GapReport(overall_score, summary, gaps...)
```

### Scanner Details

**1. Regulatory Coverage Scanner**
- Groups controls by top-level section ID (extracted from `hierarchy_id`)
- For each section's regulatory frameworks, builds keyword sets
- Counts controls whose `why + full_description` match framework keywords
- Flags frameworks below 60% coverage threshold

**2. Ecosystem Balance Analysis**
- Loads expected type distribution from section AffinityMatrix
- Calculates actual type percentages across controls
- Flags types that are over-represented (>2x expected) or under-represented (<0.5x expected)

**3. Frequency Coherence Scanner**
- Maps each control's `when` text to a canonical frequency via `derive_frequency_from_when()`
- Compares derived frequency against type-specific expectations (e.g., Reconciliation should be Monthly or more frequent)
- Flags mismatches

**4. Evidence Sufficiency Scanner**
- Scores each control's `evidence` field (0--3): artifact name, preparer/sign-off, retention location
- Flags controls scoring below 2/3

---

## 5. Remediation Layer

### Planner (`remediation/planner.py`)

Converts `GapReport` into an ordered assignment list:

```python
Priority: regulatory (highest) -> balance -> frequency -> evidence
```

Balance gaps filter to `direction == "under"` only (over-represented types are not remediated).

### Path Handlers (`remediation/paths.py`)

Four gap-type-specific path handlers prepare context for the agent pipeline:

| Gap Source | Handler | Output |
|------------|---------|--------|
| regulatory | `prepare_regulatory_path` | Spec inputs for new regulatory control |
| balance | `prepare_balance_path` | Spec inputs for under-represented type |
| frequency | `prepare_frequency_fix` | Deterministic fix dict (no LLM needed) |
| evidence | `prepare_evidence_fix` | Enricher-only path context |

`route_assignment()` dispatches based on `gap_source` field.

### Excel Export (`export/excel.py`)

Writes `list[FinalControlRecord]` to `.xlsx` using openpyxl with 19 standardized columns. Handles list-to-string conversion for `validator_failures`.

---

## 6. Agent Architecture

**File:** `src/controlnexus/agents/base.py`

### Base Agent

```python
class BaseAgent:
    def __init__(self, ctx: AgentContext, name: str | None = None):
        self.context = ctx
        self.name = name or self.__class__.__name__
        self.call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def execute(self, **kwargs) -> dict:
        """Subclass implements this."""
        raise NotImplementedError

    async def call_llm(self, system_prompt, user_prompt, **kwargs) -> str:
        """Send system+user prompt to the LLM and return text."""
        ...

    async def call_llm_with_tools(
        self, messages, tools, tool_executor, *,
        max_tool_rounds=5, tool_choice=None,
    ) -> dict:
        """Multi-turn LLM call with tool execution loop.

        If tool_choice='required', forces at least one tool call on
        round 1, then relaxes to 'auto' for subsequent rounds so the
        LLM can produce a final content response."""
        ...

    @staticmethod
    def parse_json(text: str) -> dict:
        """Extracts JSON from plain or markdown-fenced responses."""
        ...
```

### Agent Registry

```python
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}

@register_agent
class MyAgent(BaseAgent):
    ...  # Automatically registered by class name
```

### Agent Implementations

| Agent | Purpose | Fallback Behavior |
|-------|---------|-------------------|
| `SpecAgent` | Generates locked 5W specification from assignment + taxonomy | Returns spec with defaults from assignment context |
| `NarrativeAgent` | Generates 30--80 word prose from spec + standards + phrase bank | Returns template narrative with spec values substituted |
| `EnricherAgent` | Refines narrative using nearest-neighbor context from ChromaDB | Returns input with "Satisfactory" quality rating |
| `AdversarialReviewer` | Red-teams controls: identifies weaknesses, provides rewrite guidance | Returns "Satisfactory" assessment |
| `DifferentiationAgent` | Rewrites controls flagged as near-duplicates | Prepends "Additionally, " to distinguish |

All agents are async. All agents produce structured JSON. All agents have deterministic no-LLM fallbacks.

### AgentContext

```python
@dataclass
class AgentContext:
    client: AsyncTransportClient | None = None
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120
```

---

## 7. LangGraph Orchestration

**Files:** `src/controlnexus/graphs/`

### State Definitions (`state.py`)

Uses `TypedDict` with `Annotated[list, add]` reducers for parallel-safe list accumulation:

```python
class AnalysisState(TypedDict, total=False):
    excel_path: str
    config_dir: str
    ingested_records: list[dict]
    section_profiles: dict[str, Any]
    regulatory_gaps: Annotated[list[dict], add]      # Parallel-safe
    balance_gaps: Annotated[list[dict], add]          # Parallel-safe
    frequency_issues: Annotated[list[dict], add]      # Parallel-safe
    evidence_issues: Annotated[list[dict], add]       # Parallel-safe
    gap_report: dict[str, Any]
```

The `add` reducer concatenates lists from parallel nodes, preventing overwrites when 4 scanners write concurrently.

### Analysis Graph (`analysis_graph.py`)

```
START --> ingest --> load_context --+--> reg_scan  --+
                                   +--> bal_scan  --+--> build_report --> END
                                   +--> freq_scan --+
                                   +--> evid_scan --+
```

- **Fan-out:** `load_context` has edges to all 4 scanner nodes (parallel execution)
- **Fan-in:** All 4 scanners converge on `build_report` (waits for all to complete)
- **build_report** computes weighted scores and assembles the `gap_report` dict

### Remediation Graph (`remediation_graph.py`)

```
START --> planner --> router --> spec_agent --> narrative_agent --> validator
                                                                      |
                                     +--------------------------------+
                                     |              |                 |
                                  enricher    narrative_agent      merge
                                     |         (retry, max 3)    (fallback)
                                     v
                                quality_gate
                                     |
                                   merge --> export --> END
```

Routing logic:
- **`should_retry`**: After validator, routes to `enricher` (passed), `narrative_agent` (retry < 3), or `merge` (fallback after 3 retries)
- **`quality_check`**: After quality gate, currently routes all to `merge` (adversarial review routing is stubbed for future enhancement)

Key design: The graph processes one assignment at a time (router picks `assignments[0]`). For multiple gaps, the graph would be invoked iteratively or the router would be extended to loop.

### ControlForge Modular Graph (`forge_modular_graph.py`)

The config-driven control generation pipeline. 8-node LangGraph StateGraph:

```
START --> init --> select --> spec --> narrative --> validate
                                                       |
                              +------------------------+
                              |                        |
                           enrich              narrative (retry)
                              |
                           merge --> [select (loop) | finalize] --> END
```

**ForgeState** (TypedDict):
```python
class ForgeState(TypedDict, total=False):
    config_path: str
    domain_config: dict[str, Any]
    llm_enabled: bool
    provider: str              # "ica", "openai", "anthropic" — set by init_node
    assignments: list[dict]
    current_idx: int
    current_assignment: dict
    current_spec: dict
    current_narrative: dict
    current_enriched: dict
    retry_count: int
    validation_passed: bool
    retry_appendix: str
    generated_records: Annotated[list[dict], _add]
    tool_calls_log: Annotated[list[dict], _add]
    plan_payload: dict
```

**Dual-mode prompt strategy:**

Each agent node checks `_supports_tools(provider)` and selects:
- **ICA (no tool support):** Fat prompts that inline all domain data (placements, methods, evidence rules, exemplars, registry). Tools offered with `tool_choice=None` (optional). The LLM typically ignores them.
- **OpenAI/Anthropic (tool support):** Slim prompts with minimal context + instructions to call lookup tools. `tool_choice="required"` forces at least one tool call on round 1. After tool results are appended, relaxes to `tool_choice="auto"` so the LLM produces a final JSON response.

Tool schema subsets per agent:

| Agent | Fat-mode tools | Slim-mode tools |
|-------|---------------|-----------------|
| SpecAgent | taxonomy_validator, hierarchy_search, regulatory_lookup | + placement_lookup, method_lookup, evidence_rules_lookup |
| NarrativeAgent | frequency_lookup, regulatory_lookup | + exemplar_lookup |
| EnricherAgent | taxonomy_validator, frequency_lookup, memory_retrieval | *(same — prompts already minimal)* |

**Event emission:** Every node emits `PipelineEvent`s via a module-level `EventEmitter`. Events include `PIPELINE_STARTED`, `CONTROL_STARTED`, `AGENT_STARTED/COMPLETED/FAILED`, `VALIDATION_PASSED/FAILED`, `AGENT_RETRY`, `TOOL_CALLED/COMPLETED`, `CONTROL_COMPLETED`, `PIPELINE_COMPLETED`.

### Event System (`core/events.py`)

```python
class EventType(str, Enum):
    PIPELINE_STARTED = "pipeline_started"
    CONTROL_STARTED = "control_started"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_RETRY = "agent_retry"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    CONTROL_COMPLETED = "control_completed"
    PIPELINE_COMPLETED = "pipeline_completed"
    # ... 19 total

@dataclass
class PipelineEvent:
    event_type: EventType
    message: str = ""
    data: dict = field(default_factory=dict)

class EventEmitter:
    """Fan-out event bus. Listeners call emitter.on(callback)."""
    def emit(self, event: PipelineEvent) -> None: ...
```

The UI layer registers a `StreamlitEventListener` that maps events to `st.status()` updates for real-time progress display.

---

## 8. Memory Layer (ChromaDB)

**Files:** `src/controlnexus/memory/`

### Embedder Protocol (`embedder.py`)

```python
class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def dimension(self) -> int: ...

class SentenceTransformerEmbedder(Embedder):
    model_name = "all-MiniLM-L6-v2"  # 384-dim
```

The protocol allows mock injection for tests (deterministic hash-based vectors) without downloading real models.

### ControlMemory Store (`store.py`)

Wraps ChromaDB with per-organization collections:

```python
class ControlMemory:
    def __init__(self, embedder: Embedder):
        self.client = chromadb.Client()  # Ephemeral by default
        self.embedder = embedder

    def index_controls(self, bank_id, records, run_id): ...
    def query_similar(self, bank_id, text, n, section_filter): ...
    def check_duplicate(self, bank_id, text, threshold=0.92): ...
    def compare_runs(self, bank_id, run_id_a, run_id_b): ...
    def clear(self, bank_id): ...
```

- **Collection naming:** `controls_{bank_id}` -- one collection per organization
- **Similarity metric:** Cosine distance
- **Deduplication threshold:** 0.92 (controls above this are flagged as near-duplicates)
- **Metadata:** Each document stores `control_id`, `section_id`, `run_id` for filtering

---

## 9. Tool Function Calling

**Files:** `src/controlnexus/tools/`

### Tool Schemas (`schemas.py`)

9 tools defined in OpenAI function-calling JSON schema format:

| Tool | Purpose | Input | Mode |
|------|---------|-------|------|
| `taxonomy_validator` | Validates L1/L2 type pair against taxonomy | `level_1`, `level_2` | Both |
| `regulatory_lookup` | Returns required themes + applicable types for a framework/section | `framework`, `section_id` | Both |
| `hierarchy_search` | Returns domain info for a section + keyword | `section_id`, `keyword` | Both |
| `frequency_lookup` | Derives expected frequency from control type + trigger | `control_type`, `trigger` | Both |
| `memory_retrieval` | Queries ChromaDB for similar controls | `query_text`, `section_id`, `n` | Both |
| `placement_lookup` | Returns allowed placements + definitions for a control type | `control_type` | Slim |
| `method_lookup` | Returns all control methods and definitions | *(none)* | Slim |
| `evidence_rules_lookup` | Returns evidence quality criteria for a control type | `control_type` | Slim |
| `exemplar_lookup` | Retrieves exemplar narratives for an APQC section | `section_id` | Slim |

The last 4 tools ("Slim" mode) replace data that fat prompts inline. They are only offered when the provider supports function calling (OpenAI/Anthropic).

### DomainConfig-Aware Tool Context (`domain_tools.py`)

The modular graph uses `build_domain_tool_executor(config)` which returns a closure dispatching by tool name. The closure captures the `DomainConfig` instance, avoiding global state:

```python
def build_domain_tool_executor(config: DomainConfig, *, memory=None, bank_id=""):
    dispatch = {
        "taxonomy_validator": lambda **kw: dc_taxonomy_validator(**kw, config=config),
        "placement_lookup":   lambda **kw: dc_placement_lookup(**kw, config=config),
        "method_lookup":      lambda **kw: dc_method_lookup(config=config),
        # ... 9 tools total
    }
    def executor(tool_name, arguments):
        return dispatch[tool_name](**arguments)
    return executor
```

### Legacy Module-Level Tool Context (`implementations.py`)

The original analysis/remediation graphs still use the module-level `configure_tools()` pattern with `_placement_config` and `_section_profiles` globals.

### LangGraph ToolNode (`nodes.py`)

```python
TOOL_MAP = {
    "taxonomy_validator": taxonomy_validator,
    "regulatory_lookup": regulatory_lookup,
    ...
}

def tool_node(state) -> dict:
    """Process tool_calls from last message, execute tools, return results."""
    messages = state.get("messages", [])
    last_msg = messages[-1]
    for tool_call in last_msg.get("tool_calls", []):
        result = execute_tool_call(tool_call["name"], tool_call["arguments"])
        # Append ToolMessage to state
    ...
```

---

## 10. Validation Engine

**File:** `src/controlnexus/validation/validator.py`

Pure Python, no LLM. Six deterministic rules:

| Rule | Check | Failure Code |
|------|-------|--------------|
| Multiple Whats | >2 distinct action verb *roots* in `what` (curated list of 42 roots; noun-suffix filtered) | `MULTIPLE_WHATS` |
| Vague When | `when` contains "periodic", "ad hoc", "as needed", etc. | `VAGUE_WHEN` |
| Who = Where | `who` and `where` are substrings of each other | `WHO_EQUALS_WHERE` |
| Why Missing Risk | `why` lacks risk marker words (risk, prevent, mitigate, ensure, compliance, ...) | `WHY_MISSING_RISK` |
| Word Count | `full_description` outside 30--80 words | `WORD_COUNT_OUT_OF_RANGE` |
| Spec Mismatch | `who` or `where` differs from locked spec values | `SPEC_MISMATCH` |

Returns `ValidationResult(passed: bool, failures: list[str], word_count: int)`. The result is frozen (immutable).

### Retry Mechanism

When validation fails, `build_retry_appendix()` generates targeted instructions for each failure type. The NarrativeAgent receives these instructions on retry to fix specific issues.

---

## 11. Transport Layer

**File:** `src/controlnexus/core/transport.py`

### AsyncTransportClient

```python
@dataclass
class AsyncTransportClient:
    api_key: str
    base_url: str
    model: str
    provider: str = "openai"   # "ica", "openai", or "anthropic"
    timeout_seconds: int = 120
    max_retries: int = 3
```

Features:
- **Provider tracking:** The `provider` field is set at construction time by `build_client_from_env()` and propagated into `ForgeState` so graph nodes can select prompt strategies.
- **Candidate URL discovery:** Tries `{base_url}/v1/chat/completions` then `{base_url}/chat/completions`. Strips trailing `/v1` from `base_url` to prevent doubled paths.
- **URL caching:** Caches the first successful URL to skip discovery on subsequent calls.
- **Tool calling support:** `chat_completion()` accepts `tools` and `tool_choice` parameters, passed through to the provider.
- **Retry with backoff:** Exponential backoff on transient failures (500, timeout, connection error).
- **Immediate fail on auth errors:** 401/403 raises immediately without retry.
- **Multi-provider support:** Factory function `build_client_from_env()` auto-detects ICA > OpenAI > Anthropic from environment variables.

### Provider Priority

```python
def build_client_from_env() -> AsyncTransportClient | None:
    # 1. Check ICA_BASE_URL + ICA_API_KEY → provider="ica"
    # 2. Check OPENAI_API_KEY           → provider="openai"
    # 3. Check ANTHROPIC_API_KEY        → provider="anthropic"
    # Returns None if no credentials found
```

---

## 13. Streamlit Dashboard

**Files:** `src/controlnexus/ui/`

### Architecture

```
app.py                          Main entrypoint, 4-tab layout
  |
  +-- styles.py                 IBM Carbon Design CSS + design tokens
  |
  +-- modular_tab.py            ControlForge Modular: config-driven generation
  |                             StreamlitEventListener for real-time st.status()
  |
  +-- components/
  |     upload.py               File upload -> ingest_excel() -> session state
  |     analysis_runner.py      Loads profiles, runs pipeline, stores GapReport
  |
  +-- renderers/
  |     gap_dashboard.py        GapReport visualization: cards, dimension details
  |
  +-- playground.py             Agent selector, JSON input, async execution
```

The Modular tab wires an `EventEmitter` before graph invocation via `set_emitter()`, registers a `StreamlitEventListener` callback that maps 12 event types to `st.status()` live updates (agent progress, tool calls, validation results, control completion), and resets the emitter after the run.

### Session State Management

```python
st.session_state["controls"]          # list[FinalControlRecord] from ingest
st.session_state["section_profiles"]  # dict[str, SectionProfile] from config
st.session_state["gap_report"]        # GapReport from analysis pipeline
st.session_state["accepted_gaps"]     # GapReport accepted for remediation
st.session_state["playground_last_result"]  # Last agent execution result
```

### IBM Carbon Design System

Self-contained CSS tokens (no external npm dependency) following Carbon guidelines:
- **Typography:** IBM Plex Sans + IBM Plex Mono
- **Colors:** Carbon gray scale, interactive blue (#0f62fe), support colors
- **Components:** Tiles, tags, score cards, upload sections, playground output terminal
- **Overrides:** Streamlit button, expander, text area, select box styling

---

## 14. Testing Strategy

### Test Pyramid

```
308 total tests
    |
    +-- 13 e2e integration tests (test_e2e.py)
    |       Full pipeline: ingest -> analysis -> remediation -> export
    |       LangGraph graph compilation and execution
    |
    +-- 295 unit tests (test_*.py)
            Models, config loading, agents, scanners, validator,
            memory, tools, export, graphs, dual-mode prompts,
            provider detection, event emission, lookup tools
```

### Mocking Strategy

- **LLM calls:** All agents have deterministic fallbacks. Tests never make real API calls.
- **ChromaDB:** Uses ephemeral in-memory client. Unique `bank_id` per test to avoid shared state.
- **Embedder:** `MockEmbedder` produces deterministic hash-based vectors (4-dim or 8-dim) without downloading real models.
- **Excel files:** Created in `TemporaryDirectory` with openpyxl, cleaned up automatically.

### Key Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 18 | All Pydantic models, frozen immutability, validation |
| `test_config.py` | 14 | All YAML loaders, taxonomy catalog, cross-validation |
| `test_agents.py` | 17 | Registry, base agent, parse_json, all 3 core agents |
| `test_validator.py` | 36 | All 6 rules, curated verb root detection, noun filtering, boundary conditions, retry appendix |
| `test_scanners.py` | 13 | All 4 scanners, edge cases, score_evidence |
| `test_pipeline.py` | 5 | run_analysis integration with real config |
| `test_graphs.py` | 10 | Graph compilation, node functions, conditional routing |
| `test_forge_modular_graph.py` | 73 | Assignment matrix, deterministic builders, 8-node graph execution, LLM node mocks, validation retry loop, prompt templates (fat+slim), event emission, dual-mode provider selection |
| `test_memory.py` | 14 | ChromaDB operations, embedder protocol |
| `test_tools.py` | 31 | Schemas, all 9 tools (5 original + 4 lookup), ToolNode processing, domain tool executor dispatch |
| `test_remediation.py` | 15 | Planner, all 4 paths, AdversarialReviewer, DifferentiationAgent |
| `test_export.py` | 5 | Excel export, headers, row count, round-trip |
| `test_ingest.py` | 8 | Type coercion, parse_failures, Excel parsing |
| `test_transport.py` | 12 | Candidate URLs, retry logic, multi-provider factory |
| `test_constants.py` | 11 | Frequency derivation, type codes, control ID builder |
| `test_e2e.py` | 13 | Full pipeline, graph execution, round-trips |

---

## 15. Deployment Architecture

### Docker

```dockerfile
FROM python:3.11-slim
# Install deps, copy source + config, expose 8501
ENTRYPOINT ["streamlit", "run", "src/controlnexus/ui/app.py", ...]
```

Health check validates the package imports successfully.

### CI/CD Pipeline (GitHub Actions)

```
push/PR --> [lint] --> [typecheck] --> [test] --> [docker build]
                \                       /
                 +-- parallel jobs ----+
```

- **lint:** `ruff check` + `ruff format --check`
- **typecheck:** `mypy` with strict mode, runs after lint
- **test:** `pytest` with JUnit XML artifact upload, runs after lint
- **docker:** Buildx with GitHub Actions cache, runs after test + typecheck pass

### Pre-commit Hooks

Local development quality gates:
1. `ruff` -- lint + auto-fix
2. `ruff-format` -- formatting
3. `mypy` -- type checking on `src/controlnexus/`
4. `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`, `check-merge-conflict`

### Environment Configuration

Production deployments use environment variables (no config files for secrets):

```env
# LLM Provider (pick one)
ICA_BASE_URL=...     ICA_API_KEY=...     ICA_MODEL=...
OPENAI_API_KEY=...   OPENAI_MODEL=...
ANTHROPIC_API_KEY=.. ANTHROPIC_MODEL=...

# ChromaDB (optional, defaults to ephemeral)
CHROMA_PERSIST_DIR=/data/chromadb

# Streamlit
STREAMLIT_SERVER_PORT=8501
```

---

## Appendix: Module Dependency Graph

```
core/
  models.py        <-- No internal deps
  constants.py     <-- No internal deps
  state.py         <-- models
  config.py        <-- models, state
  domain_config.py <-- (Pydantic v2, self-contained)
  events.py        <-- No internal deps
  transport.py     <-- exceptions

agents/
  base.py          <-- core/transport (call_llm, call_llm_with_tools)
  spec.py          <-- base
  narrative.py     <-- base
  enricher.py      <-- base
  adversarial.py   <-- base
  differentiator.py <-- base

analysis/
  ingest.py        <-- core/state
  scanners.py      <-- core/constants, core/models, core/state
  pipeline.py      <-- scanners, core/models, core/state

validation/
  validator.py     <-- core/state

memory/
  embedder.py      <-- (ABC only)
  store.py         <-- embedder, core/state

tools/
  schemas.py       <-- (pure data, 9 tool schemas)
  implementations.py <-- core/config, core/constants, memory/store
  domain_tools.py  <-- core/domain_config (DomainConfig-aware executors)
  nodes.py         <-- implementations

remediation/
  planner.py       <-- (dict processing only)
  paths.py         <-- core/constants

graphs/
  state.py         <-- (TypedDict only)
  analysis_graph.py <-- analysis/*, core/*, state
  remediation_graph.py <-- remediation/*, validation/*, state
  forge_modular_graph.py <-- agents/base, tools/domain_tools, tools/schemas,
                             validation/*, core/events, core/domain_config,
                             graphs/forge_modular_helpers
  forge_modular_helpers.py <-- core/domain_config (prompt builders, deterministic)

export/
  excel.py         <-- core/state

ui/
  app.py           <-- styles, components/*, renderers/*, modular_tab, playground
  styles.py        <-- streamlit
  modular_tab.py   <-- graphs/forge_modular_graph, core/events
  components/*     <-- analysis/*, core/*
  renderers/*      <-- core/state, styles
  playground.py    <-- agents/
```
