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
11. [Evaluation Harness](#11-evaluation-harness)
12. [Transport Layer](#12-transport-layer)
13. [Streamlit Dashboard](#13-streamlit-dashboard)
14. [Testing Strategy](#14-testing-strategy)
15. [Deployment Architecture](#15-deployment-architecture)

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
    def __init__(self, ctx: AgentContext):
        self.ctx = ctx          # Contains AsyncTransportClient
        self.token_usage = {}   # Tracks input/output tokens

    async def execute(self, **kwargs) -> dict:
        """Subclass implements this."""
        raise NotImplementedError

    async def call_llm(self, messages, **kwargs) -> dict:
        """Delegates to ctx.client.chat_completion()"""
        ...

    @staticmethod
    def _parse_json(text: str) -> dict:
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
    # Future: memory, tools, config
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

5 tools defined in OpenAI function-calling JSON schema format:

| Tool | Purpose | Input |
|------|---------|-------|
| `taxonomy_validator` | Validates L1/L2 type pair against taxonomy | `level_1`, `level_2` |
| `regulatory_lookup` | Returns required themes + applicable types for a framework/section | `framework`, `section_id` |
| `hierarchy_search` | Returns domain info for a section + keyword | `section_id`, `keyword` |
| `frequency_lookup` | Derives expected frequency from control type + trigger | `control_type`, `trigger` |
| `memory_retrieval` | Queries ChromaDB for similar controls | `query_text`, `section_id`, `n` |

### Module-Level Tool Context (`implementations.py`)

```python
# Module globals set before graph execution
_placement_config: dict = {}
_section_profiles: dict = {}
_memory: ControlMemory | None = None
_bank_id: str = ""

def configure_tools(placement_config, section_profiles, memory, bank_id):
    """Set module-level context for tool implementations."""
    global _placement_config, _section_profiles, _memory, _bank_id
    ...
```

This pattern avoids threading config through every tool call signature.

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
| Multiple Whats | >2 distinct action verbs in `what` | `MULTIPLE_WHATS` |
| Vague When | `when` contains "periodic", "ad hoc", "as needed", etc. | `VAGUE_WHEN` |
| Who = Where | `who` and `where` are substrings of each other | `WHO_EQUALS_WHERE` |
| Why Missing Risk | `why` lacks risk marker words (risk, prevent, mitigate, ensure, compliance, ...) | `WHY_MISSING_RISK` |
| Word Count | `full_description` outside 30--80 words | `WORD_COUNT_OUT_OF_RANGE` |
| Spec Mismatch | `who` or `where` differs from locked spec values | `SPEC_MISMATCH` |

Returns `ValidationResult(passed: bool, failures: list[str], word_count: int)`. The result is frozen (immutable).

### Retry Mechanism

When validation fails, `build_retry_appendix()` generates targeted instructions for each failure type. The NarrativeAgent receives these instructions on retry to fix specific issues.

---

## 11. Evaluation Harness

**Files:** `src/controlnexus/evaluation/`

### Four Scoring Dimensions

**Faithfulness (0--4):**
- +1 `who` matches spec
- +1 `where` matches spec
- +1 `control_type` is valid for `selected_level_1` in taxonomy
- +1 `placement` is valid for the control type

**Completeness (0--6):**
- +1 `who` has a specific role title (not "Control Owner", "Manager", etc.)
- +1 `what` contains an action verb
- +1 `frequency` is a real frequency (Daily, Weekly, Monthly, Quarterly, Semi-Annual, Annual)
- +1 `where` names a specific system
- +1 `why` contains a risk-related word
- +1 `full_description` is 30--80 words

**Diversity (0.0--1.0):**
- Computes pairwise cosine similarity across all control `full_description` embeddings
- `diversity = 1 - mean(similarities above 0.92 threshold)`
- Also reports `near_duplicate_count` (pairs above threshold)
- Requires an `Embedder` instance; returns 1.0 if no embedder provided

**Gap Closure (delta):**
- Re-runs `run_analysis()` on original + generated controls combined
- Delta = new_score - original_score
- Positive delta means the generated controls improved the ecosystem

### EvalReport

```python
class EvalReport(BaseModel):
    run_id: str
    faithfulness_avg: float    # 0.0-4.0
    completeness_avg: float    # 0.0-6.0
    diversity_score: float     # 0.0-1.0
    near_duplicate_count: int
    gap_closure_delta: float   # positive = improvement
    per_control_scores: list[ControlScore]
    total_controls: int
```

Optionally exports to `{run_id}__eval.json` for persistence.

---

## 12. Transport Layer

**File:** `src/controlnexus/core/transport.py`

### AsyncTransportClient

```python
@dataclass
class AsyncTransportClient:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: int = 120
    max_retries: int = 3
```

Features:
- **Candidate URL discovery:** Tries `{base_url}/v1/chat/completions` then `{base_url}/chat/completions`
- **URL caching:** Caches the first successful URL to skip discovery on subsequent calls
- **Retry with backoff:** Exponential backoff on transient failures (500, timeout, connection error)
- **Immediate fail on auth errors:** 401/403 raises immediately without retry
- **Multi-provider support:** Factory function `build_client_from_env()` auto-detects ICA > OpenAI > Anthropic from environment variables

### Provider Priority

```python
def build_client_from_env() -> AsyncTransportClient | None:
    # 1. Check ICA_BASE_URL + ICA_API_KEY
    # 2. Check OPENAI_API_KEY
    # 3. Check ANTHROPIC_API_KEY
    # Returns None if no credentials found
```

---

## 13. Streamlit Dashboard

**Files:** `src/controlnexus/ui/`

### Architecture

```
app.py                          Main entrypoint, 3-tab layout
  |
  +-- styles.py                 IBM Carbon Design CSS + design tokens
  |
  +-- components/
  |     upload.py               File upload -> ingest_excel() -> session state
  |     analysis_runner.py      Loads profiles, runs pipeline, stores GapReport
  |
  +-- renderers/
  |     gap_dashboard.py        GapReport visualization: cards, dimension details
  |     eval_dashboard.py       EvalReport visualization: score tiles, breakdowns
  |
  +-- playground.py             Agent selector, JSON input, async execution
```

### Session State Management

```python
st.session_state["controls"]          # list[FinalControlRecord] from ingest
st.session_state["section_profiles"]  # dict[str, SectionProfile] from config
st.session_state["gap_report"]        # GapReport from analysis pipeline
st.session_state["accepted_gaps"]     # GapReport accepted for remediation
st.session_state["eval_report"]       # EvalReport from evaluation harness
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
258 total tests
    |
    +-- 15 e2e integration tests (test_e2e.py)
    |       Full pipeline: ingest -> analysis -> remediation -> eval -> export
    |       LangGraph graph compilation and execution
    |
    +-- 243 unit tests (test_*.py)
            Models, config loading, agents, scanners, validator,
            memory, tools, evaluation, export, graphs
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
| `test_validator.py` | 16 | All 6 rules, boundary conditions, retry appendix |
| `test_scanners.py` | 13 | All 4 scanners, edge cases, score_evidence |
| `test_pipeline.py` | 5 | run_analysis integration with real config |
| `test_graphs.py` | 10 | Graph compilation, node functions, conditional routing |
| `test_memory.py` | 14 | ChromaDB operations, embedder protocol |
| `test_tools.py` | 20 | Schemas, all 5 tools, ToolNode processing |
| `test_evaluation.py` | 23 | All 4 scorers, cosine similarity, EvalReport, run_eval |
| `test_remediation.py` | 15 | Planner, all 4 paths, AdversarialReviewer, DifferentiationAgent |
| `test_export.py` | 5 | Excel export, headers, row count, round-trip |
| `test_ingest.py` | 8 | Type coercion, parse_failures, Excel parsing |
| `test_transport.py` | 12 | Candidate URLs, retry logic, multi-provider factory |
| `test_constants.py` | 11 | Frequency derivation, type codes, control ID builder |
| `test_e2e.py` | 15 | Full pipeline, graph execution, round-trips |

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
  events.py        <-- No internal deps
  transport.py     <-- exceptions

agents/
  base.py          <-- core/transport
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
  schemas.py       <-- (pure data)
  implementations.py <-- core/config, core/constants, memory/store
  nodes.py         <-- implementations

remediation/
  planner.py       <-- (dict processing only)
  paths.py         <-- core/constants

evaluation/
  models.py        <-- (Pydantic only)
  scorers.py       <-- analysis/pipeline, core/constants, memory/embedder
  harness.py       <-- scorers, models, core/models, core/state

graphs/
  state.py         <-- (TypedDict only)
  analysis_graph.py <-- analysis/*, core/*, state
  remediation_graph.py <-- remediation/*, validation/*, state

export/
  excel.py         <-- core/state

ui/
  app.py           <-- styles, components/*, renderers/*, playground
  styles.py        <-- streamlit
  components/*     <-- analysis/*, core/*
  renderers/*      <-- core/state, evaluation/models, styles
  playground.py    <-- agents/
```
