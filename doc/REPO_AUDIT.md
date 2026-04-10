# REPO_AUDIT.md — Comprehensive Code Audit

> Generated 2026-04-09 as Phase 1 of the production-quality cleanup.
> No changes have been made to the codebase yet.

---

## Table of Contents

1. [Directory Tree](#1-directory-tree)
2. [Module Dependency Graph](#2-module-dependency-graph)
3. [Public Interfaces by Module](#3-public-interfaces-by-module)
4. [Configuration Surfaces](#4-configuration-surfaces)
5. [External Dependencies](#5-external-dependencies)
6. [File Sizes and Complexity](#6-file-sizes-and-complexity)
7. [Dead Code and Unused Symbols](#7-dead-code-and-unused-symbols)
8. [Code Quality Observations](#8-code-quality-observations)
9. [Architecture Observations](#9-architecture-observations)
10. [Testing Coverage Map](#10-testing-coverage-map)

---

## 1. Directory Tree

```
.
├── pyproject.toml                          # Package metadata + dependencies
├── README.md                               # Project overview
├── REPO_AUDIT.md                           # ← this file
├── config/
│   ├── default.yaml                        # Pipeline thresholds, scales, categories
│   └── risk_taxonomy.json                  # Risk category → sub-risk taxonomy
├── data/
│   ├── checkpoints/                        # JSON checkpoint files (pipeline state snapshots)
│   │   └── *.json                          # 10 checkpoint files
│   └── Control Dataset/                    # Control inventory Excel files
│       └── section_*__controls.xlsx
├── doc/
│   ├── ARCHITECTURE.md                     # Detailed architecture walkthrough
│   └── plan.md                             # Original implementation plan
├── langgraph-multiagent-skeleton/          # Upstream skeleton (NOT part of regrisk)
│   └── ...
├── src/
│   └── regrisk/
│       ├── __init__.py                     # Package root (__version__)
│       ├── exceptions.py                   # Exception hierarchy (5 classes)
│       ├── agents/
│       │   ├── __init__.py                 # Docstring only
│       │   ├── base.py                     # BaseAgent ABC, AgentContext, registry, helpers
│       │   ├── obligation_classifier.py    # ObligationClassifierAgent
│       │   ├── apqc_mapper.py              # APQCMapperAgent
│       │   ├── coverage_assessor.py        # CoverageAssessorAgent
│       │   └── risk_extractor_scorer.py    # RiskExtractorAndScorerAgent
│       ├── core/
│       │   ├── __init__.py                 # Docstring only
│       │   ├── config.py                   # PipelineConfig Pydantic model, YAML/JSON loaders
│       │   ├── events.py                   # EventType enum, PipelineEvent, EventEmitter
│       │   ├── models.py                   # 11 frozen Pydantic domain models
│       │   └── transport.py                # AsyncTransportClient (httpx), env-based factory
│       ├── export/
│       │   ├── __init__.py                 # Docstring only
│       │   └── excel_export.py             # Excel workbook generation + review import/export
│       ├── graphs/
│       │   ├── __init__.py                 # Docstring only
│       │   ├── classify_graph.py           # Graph 1 builder + node functions
│       │   ├── classify_state.py           # ClassifyState TypedDict
│       │   ├── assess_graph.py             # Graph 2 builder + node functions
│       │   └── assess_state.py             # AssessState TypedDict
│       ├── ingest/
│       │   ├── __init__.py                 # Docstring only
│       │   ├── regulation_parser.py        # Parse Promontory-format regulation Excel
│       │   ├── apqc_loader.py              # Load APQC hierarchy, build summary text
│       │   └── control_loader.py           # Discover/load/merge control files, build index
│       ├── tracing/
│       │   ├── __init__.py                 # Re-exports public API (TraceDB, etc.)
│       │   ├── db.py                       # SQLite trace database (schema, inserts, queries)
│       │   ├── decorators.py               # trace_node decorator, thread-local context
│       │   ├── listener.py                 # SQLiteTraceListener (event → DB)
│       │   └── transport_wrapper.py        # TracingTransportClient (LLM call → DB)
│       ├── ui/
│       │   ├── __init__.py                 # Docstring only
│       │   ├── app.py                      # Streamlit 5-tab application (1564 lines)
│       │   └── checkpoint.py               # Checkpoint save/load/list
│       └── validation/
│           ├── __init__.py                 # Docstring only
│           └── validator.py                # Deterministic validation + derive_inherent_rating
└── tests/
    ├── __init__.py
    ├── conftest.py                         # Shared fixtures (231 lines)
    ├── test_assess_graph.py                # Graph 2 integration tests
    ├── test_classify_graph.py              # Graph 1 integration tests
    ├── test_ingest.py                      # Ingest layer unit tests
    ├── test_models.py                      # Pydantic model tests
    ├── test_tracing.py                     # Tracing system tests
    └── test_validator.py                   # Validator unit tests
```

**Total source lines:** ~4,633 (src/regrisk/) + ~1,279 (tests/) = **~5,912 lines**

---

## 2. Module Dependency Graph

### Internal dependency direction (arrows = "imports from")

```
Layer 0 — No internal deps:
  exceptions.py
  core/events.py
  core/models.py (uses pydantic only)

Layer 1 — Depends on Layer 0:
  core/config.py          → (pydantic, yaml, json — no regrisk deps)
  core/transport.py       → exceptions
  validation/validator.py → (no regrisk deps)

Layer 2 — Depends on Layers 0–1:
  agents/base.py          → core/transport
  tracing/db.py           → (no regrisk deps — pure sqlite3)
  tracing/decorators.py   → tracing/db
  tracing/listener.py     → core/events, tracing/db
  tracing/transport_wrapper.py → core/transport, tracing/db, tracing/decorators
  ingest/regulation_parser.py  → core/models, exceptions
  ingest/apqc_loader.py        → core/models, exceptions
  ingest/control_loader.py     → core/models, exceptions
  export/excel_export.py       → (pandas only — no regrisk deps)

Layer 3 — Depends on Layers 0–2:
  agents/obligation_classifier.py → agents/base
  agents/apqc_mapper.py           → agents/base
  agents/coverage_assessor.py     → agents/base
  agents/risk_extractor_scorer.py → agents/base, validation/validator

Layer 4 — Depends on Layers 0–3:
  graphs/classify_state.py → (no regrisk deps — TypedDict only)
  graphs/assess_state.py   → (no regrisk deps — TypedDict only)
  graphs/classify_graph.py → agents/base, agents/obligation_classifier,
                              core/config, core/events, core/transport,
                              graphs/classify_state, tracing/decorators,
                              tracing/transport_wrapper, ingest/*,
                              validation/validator
  graphs/assess_graph.py   → agents/base, agents/{apqc_mapper, coverage_assessor,
                              risk_extractor_scorer}, core/events, core/transport,
                              core/models, graphs/assess_state,
                              tracing/decorators, tracing/transport_wrapper,
                              ingest/{apqc_loader, control_loader},
                              validation/validator

Layer 5 — Top-level UI:
  ui/checkpoint.py → (no regrisk deps — pure json/pathlib)
  ui/app.py        → core/config, core/events, export/excel_export,
                      graphs/{classify_graph, assess_graph},
                      ingest/{regulation_parser, apqc_loader, control_loader},
                      ui/checkpoint, tracing/{db, listener}
```

### Circular dependencies

**None detected.** The dependency graph is a clean DAG from bottom (exceptions, models) to top (UI).

### Inline/deferred imports

- `agents/base.py` lines 81, 126: Imports `regrisk.tracing.decorators` inside method bodies to avoid circular import at module load time. This is the only cross-layer import that uses deferred loading.
- `graphs/assess_graph.py` line 220: Uses `__import__("regrisk.core.models", ...)` inline in `prepare_assessment_node` — an unusual pattern that should be a normal import.

---

## 3. Public Interfaces by Module

### `regrisk.exceptions` (21 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `RegRiskError` | Exception | Base exception |
| `IngestError` | Exception | Data ingestion failures |
| `AgentError` | Exception | Agent failures |
| `TransportError` | Exception | LLM API call failures |
| `ValidationError` | Exception | Artifact validation failures |

### `regrisk.core.config` (97 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `CoverageThresholds` | Pydantic model | `semantic_match_min_confidence`, `frequency_tolerance` |
| `PipelineConfig` | Pydantic model | All pipeline settings (14 fields) |
| `load_config(path)` | Function | YAML → PipelineConfig |
| `load_risk_taxonomy(path)` | Function | JSON → dict |
| `default_config_path()` | Function | Returns `config/default.yaml` Path |
| `default_taxonomy_path()` | Function | Returns `config/risk_taxonomy.json` Path |

### `regrisk.core.events` (115 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `EventType` | Enum (19 members) | Pipeline lifecycle events |
| `PipelineEvent` | frozen dataclass | Immutable event snapshot |
| `EventListener` | Protocol | Callable protocol for observers |
| `EventEmitter` | Class | Fan-out event dispatcher |
| `cli_listener` | Function | **⚠️ Defined but never imported/used anywhere** |

### `regrisk.core.models` (173 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `Obligation` | frozen Pydantic | Raw regulation row (14 fields) |
| `ObligationGroup` | frozen Pydantic | Section group with child obligations |
| `APQCNode` | frozen Pydantic | APQC hierarchy node (5 fields) |
| `ControlRecord` | frozen Pydantic | Control inventory row (15 fields) |
| `ClassifiedObligation` | frozen Pydantic | Enriched obligation (9 fields) |
| `ObligationAPQCMapping` | frozen Pydantic | Obligation→APQC link (6 fields) |
| `CoverageAssessment` | frozen Pydantic | Coverage evaluation result (9 fields) |
| `ScoredRisk` | frozen Pydantic | Scored risk (14 fields) |
| `GapReport` | Pydantic | Gap analysis output (6 fields) |
| `ComplianceMatrix` | Pydantic | Full obligation×control matrix |
| `RiskRegister` | Pydantic | Risk register with distribution stats |

**Note:** `GapReport`, `ComplianceMatrix`, `RiskRegister` are defined as Pydantic models but the graphs assemble them as plain dicts. They are only used in tests, not in production code.

### `regrisk.core.transport` (237 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `AsyncTransportClient` | dataclass | Async httpx chat-completion client |
| `build_client_from_env()` | Function | Auto-detect ICA/OpenAI from env vars |

### `regrisk.agents.base` (212 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `AGENT_REGISTRY` | dict | **⚠️ Populated by `@register_agent` but never read anywhere** |
| `register_agent` | Decorator | Registers agent class by name |
| `AgentContext` | dataclass | Runtime context (client, model, temp, tokens, timeout) |
| `BaseAgent` | ABC | `execute()`, `call_llm()`, `call_llm_with_tools()`, `parse_json()` |

### `regrisk.agents.obligation_classifier` (173 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `ObligationClassifierAgent` | Class | Classifies obligations by category, relationship, criticality |

### `regrisk.agents.apqc_mapper` (159 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `APQCMapperAgent` | Class | Maps obligations → APQC processes |

### `regrisk.agents.coverage_assessor` (130 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `CoverageAssessorAgent` | Class | Evaluates control coverage (3-layer evaluation) |

### `regrisk.agents.risk_extractor_scorer` (159 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `RiskExtractorAndScorerAgent` | Class | Extracts and scores risks for uncovered obligations |

### `regrisk.graphs.classify_graph` (313 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `set_emitter(emitter)` | Function | Set module-level EventEmitter |
| `get_emitter()` | Function | Get module-level EventEmitter |
| `reset_caches()` | Function | Reset LLM client, agents, event loop caches |
| `build_classify_graph(trace_db, run_id)` | Function | Build and compile Graph 1 |
| `init_node` | Function | Load config, detect LLM |
| `ingest_node` | Function | Parse regulation, APQC, controls |
| `classify_group_node` | Function | Classify one obligation group |
| `has_more_classify_groups` | Function | Conditional edge router |
| `end_classify_node` | Function | Emit completion event |

### `regrisk.graphs.assess_graph` (553 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `set_emitter(emitter)` | Function | Set module-level EventEmitter |
| `get_emitter()` | Function | Get module-level EventEmitter |
| `get_partial_assessments()` | Function | Return partial results on failure |
| `reset_caches()` | Function | Reset all caches |
| `build_assess_graph(trace_db, run_id)` | Function | Build and compile Graph 2 |
| `map_group_node` | Function | Map one obligation group to APQC |
| `prepare_assessment_node` | Function | Build assessment items |
| `assess_coverage_node` | Function | Assess one coverage item |
| `prepare_risks_node` | Function | Filter gaps |
| `extract_and_score_node` | Function | Score risks for one gap |
| `finalize_node` | Function | Assemble final reports |
| `has_more_map_groups` | Function | Conditional edge router |
| `has_more_assessments` | Function | Conditional edge router |
| `has_more_gaps` | Function | Conditional edge router |

### `regrisk.ingest.regulation_parser` (119 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `parse_regulation_excel(path)` | Function | Parse regulation → (name, obligations) |
| `group_obligations(obligations)` | Function | Group by section → ObligationGroup list |

### `regrisk.ingest.apqc_loader` (80 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `load_apqc_hierarchy(path)` | Function | Parse APQC Excel → APQCNode list |
| `build_apqc_summary(nodes, max_depth)` | Function | Build indented text for LLM prompts |
| `get_apqc_subtree(nodes, root_id)` | Function | Get descendants of a hierarchy node |

### `regrisk.ingest.control_loader` (118 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `discover_control_files(directory, pattern)` | Function | Glob for control Excel files |
| `load_and_merge_controls(file_paths)` | Function | Load + deduplicate controls |
| `build_control_index(controls)` | Function | Index controls by hierarchy_id |
| `find_controls_for_apqc(index, apqc_id)` | Function | Find controls matching an APQC node |

### `regrisk.export.excel_export` (184 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `export_gap_report(...)` | Function | Multi-sheet Excel workbook |
| `export_compliance_matrix(matrix, path)` | Function | **⚠️ Defined but never called** |
| `export_for_review(data, stage, path)` | Function | Review spreadsheet with approve column |
| `import_reviewed(path, stage)` | Function | Import human-reviewed approvals |

### `regrisk.tracing.db` (330 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `TraceDB` | Class | SQLite trace store (WAL mode, zero-config) |

### `regrisk.tracing.decorators` (182 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `set_current_trace_context(node_name, agent_name)` | Function | Thread-local context setter |
| `get_current_trace_context()` | Function | Thread-local context getter |
| `trace_node(db, run_id, node_name)` | Function | Decorator factory for node tracing |

### `regrisk.tracing.listener` (49 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `SQLiteTraceListener` | Class | PipelineEvent → SQLite events table |

### `regrisk.tracing.transport_wrapper` (150 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `TracingTransportClient` | Class | Drop-in AsyncTransportClient wrapper logging LLM calls |

### `regrisk.validation.validator` (108 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `VALID_CATEGORIES` | set | Valid obligation categories |
| `VALID_RELATIONSHIP_TYPES` | set | Valid relationship types |
| `VALID_COVERAGE_STATUSES` | set | Valid coverage statuses |
| `VALID_SEMANTIC_MATCHES` | set | Valid semantic match values |
| `VALID_RELATIONSHIP_MATCHES` | set | Valid relationship match values |
| `validate_classification(c)` | Function | → (bool, list[str]) |
| `validate_mapping(m)` | Function | → (bool, list[str]) |
| `validate_coverage(a)` | Function | → (bool, list[str]) |
| `validate_risk(r)` | Function | → (bool, list[str]) |
| `derive_inherent_rating(impact, frequency)` | Function | Impact × frequency → rating string |

### `regrisk.ui.checkpoint` (180 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `STAGE_CLASSIFIED` | str const | `"classified"` |
| `STAGE_MAPPED` | str const | `"mapped"` |
| `STAGE_ASSESSED` | str const | `"assessed"` |
| `STAGE_ASSESS_PARTIAL` | str const | `"assess_partial"` |
| `CHECKPOINT_DIR` | Path | `data/checkpoints/` |
| `stage_label(stage)` | Function | Human-readable stage name |
| `stage_keys(stage)` | Function | Session state keys to save |
| `save_checkpoint(stage, data, dir)` | Function | Write JSON checkpoint |
| `load_checkpoint(path)` | Function | Read JSON checkpoint |
| `list_checkpoints(dir)` | Function | List available checkpoints |

### `regrisk.ui.app` (1564 lines)
| Symbol | Type | Description |
|--------|------|-------------|
| `main()` | Function | Streamlit entry point |
| Internal: 20+ private helper functions for tabs, rendering, graph invocation |

---

## 4. Configuration Surfaces

### 4.1 Environment Variables

| Variable | Module | Default | Purpose |
|----------|--------|---------|---------|
| `ICA_API_KEY` | `core/transport.py` | — | IBM Cloud AI API key |
| `ICA_BASE_URL` | `core/transport.py` | — | ICA endpoint base URL |
| `ICA_MODEL_ID` | `core/transport.py` | `anthropic.claude-sonnet-4-5-20250929-v1:0` | ICA model identifier |
| `ICA_TIMEOUT` | `core/transport.py` | `300` | ICA request timeout (seconds) |
| `ICA_MAX_RETRIES` | `core/transport.py` | `5` | ICA max retry count |
| `ICA_MAX_BACKOFF` | `core/transport.py` | `60` | ICA max backoff (seconds) |
| `ICA_TOOL_CALLING` | `core/transport.py` | `false` | Enable ICA tool calling |
| `OPENAI_API_KEY` | `core/transport.py` | — | OpenAI API key |
| `OPENAI_BASE_URL` | `core/transport.py` | `https://api.openai.com` | OpenAI endpoint |
| `OPENAI_MODEL` | `core/transport.py` | `gpt-4o` | OpenAI model name |
| `.env` file | `ui/app.py` | — | Loaded via `python-dotenv` at app startup |

### 4.2 YAML Configuration (`config/default.yaml`)

| Key | Type | Default | Used by |
|-----|------|---------|---------|
| `name` | str | `reg-obligation-mapper` | PipelineConfig |
| `description` | str | — | PipelineConfig |
| `active_statuses` | list[str] | `["In Force", "Pending"]` | Ingest filtering |
| `control_file_pattern` | str | `section_*__controls.xlsx` | Control file discovery |
| `obligation_categories` | list[str] | 5 categories | Classification |
| `relationship_types` | list[str] | 5 types | Classification |
| `criticality_tiers` | list[str] | `["High", "Medium", "Low"]` | Classification |
| `actionable_categories` | list[str] | 3 categories | Mapping filter |
| `apqc_mapping_depth` | int | `3` | APQC summary depth |
| `max_apqc_mappings_per_obligation` | int | `5` | APQC mapping cap |
| `coverage_thresholds.semantic_match_min_confidence` | float | `0.6` | Coverage assessment |
| `coverage_thresholds.frequency_tolerance` | int | `1` | Coverage assessment |
| `min_risks_per_gap` | int | `1` | Risk extraction |
| `max_risks_per_gap` | int | `3` | Risk extraction |
| `impact_scale` | dict | 4-point scale | Risk scoring |
| `frequency_scale` | dict | 4-point scale | Risk scoring |
| `risk_id_prefix` | str | `RISK` | Risk ID generation |

### 4.3 JSON Configuration (`config/risk_taxonomy.json`)

8 top-level risk categories, each with description + sub-risks list:
Credit Risk, Operational Risk, Market Risk, Compliance Risk, Strategic Risk, Reputational Risk, Interest Rate Risk, Liquidity Risk.

### 4.4 CLI / Script Arguments

No CLI arguments. The application is launched via:
```bash
python -m streamlit run src/regrisk/ui/app.py
```

All configuration is via env vars, YAML, or the Streamlit UI scope controls.

---

## 5. External Dependencies

### 5.1 Runtime Dependencies (from `pyproject.toml`)

| Package | Version | Used by | How |
|---------|---------|---------|-----|
| `langgraph` | ≥0.2 | `graphs/classify_graph.py`, `graphs/assess_graph.py` | `StateGraph`, `END`, `START` |
| `langchain-core` | ≥0.3 | **⚠️ Declared but never directly imported** | Transitive dep of langgraph |
| `pydantic` | ≥2.0 | `core/config.py`, `core/models.py` | `BaseModel`, `Field`, frozen models |
| `streamlit` | ≥1.35 | `ui/app.py` | Entire UI framework |
| `httpx` | ≥0.27 | `core/transport.py` | Async HTTP client for LLM API calls |
| `pyyaml` | ≥6.0 | `core/config.py` | YAML config loading |
| `pandas` | ≥2.0 | `ingest/*.py`, `export/excel_export.py`, `ui/app.py` | Data loading/export |
| `openpyxl` | ≥3.1 | Transitive (via pandas) | Excel file engine |
| `matplotlib` | ≥3.8 | `ui/app.py` | Risk heatmap rendering |
| `python-dotenv` | ≥1.0 | `ui/app.py` | `.env` file loading |

### 5.2 Dev Dependencies

| Package | Version | Used by |
|---------|---------|---------|
| `pytest` | ≥8.0 | Test runner |
| `pytest-asyncio` | ≥0.23 | **⚠️ Declared but no async tests exist** |

### 5.3 Standard Library Notable Usage

| Module | Used by |
|--------|---------|
| `sqlite3` | `tracing/db.py` |
| `asyncio` | `core/transport.py`, `graphs/classify_graph.py`, `graphs/assess_graph.py` |
| `threading` | `tracing/decorators.py` (thread-local trace context) |
| `json` | Multiple (checkpoint, tracing, base agent) |
| `re` | `regulation_parser.py`, `control_loader.py`, `agents/base.py`, `transport.py` |
| `glob` | `control_loader.py` |
| `tempfile` | `ui/app.py` |
| `uuid` | `ui/app.py` |
| `io` | `ui/app.py` |

---

## 6. File Sizes and Complexity

| File | Lines | Functions | Classes | Notes |
|------|-------|-----------|---------|-------|
| `ui/app.py` | **1564** | ~25 | 0 | **⚠️ Largest file by far. Should be decomposed.** |
| `graphs/assess_graph.py` | **553** | 14 | 0 | Large but cohesive (all Graph 2 logic). |
| `tracing/db.py` | 330 | 15 | 1 | Acceptable — single-responsibility. |
| `graphs/classify_graph.py` | 313 | 11 | 0 | Acceptable — all Graph 1 logic. |
| `agents/base.py` | 212 | 8 | 3 | Acceptable. |
| `core/transport.py` | 237 | 5 | 1 | chat_completion method is ~120 lines (complex retry logic). |
| `export/excel_export.py` | 184 | 5 | 0 | Acceptable. |
| `tracing/decorators.py` | 182 | 4 | 0 | Acceptable. |
| `ui/checkpoint.py` | 180 | 5 | 0 | Acceptable. |
| `agents/obligation_classifier.py` | 173 | 3 | 1 | Acceptable. |
| `core/models.py` | 173 | 0 | 11 | Acceptable — pure data definitions. |
| `agents/apqc_mapper.py` | 159 | 3 | 1 | Acceptable. |
| `agents/risk_extractor_scorer.py` | 159 | 4 | 1 | Acceptable. |
| `tracing/transport_wrapper.py` | 150 | 3 | 1 | Acceptable. |
| `agents/coverage_assessor.py` | 130 | 2 | 1 | Acceptable. |
| `ingest/regulation_parser.py` | 119 | 3 | 0 | Acceptable. |
| `ingest/control_loader.py` | 118 | 5 | 0 | Acceptable. |
| `validation/validator.py` | 108 | 5 | 0 | Acceptable. |
| `core/config.py` | 97 | 4 | 2 | Acceptable. |
| `core/events.py` | 115 | 5 | 2 | Acceptable. |
| `ingest/apqc_loader.py` | 80 | 3 | 0 | Acceptable. |
| `tracing/listener.py` | 49 | 1 | 1 | Small and focused. |
| `graphs/assess_state.py` | 46 | 0 | 1 | TypedDict only. |
| `graphs/classify_state.py` | 36 | 0 | 1 | TypedDict only. |
| `exceptions.py` | 21 | 0 | 5 | Small and focused. |

---

## 7. Dead Code and Unused Symbols

### 7.1 Unused Functions / Variables (defined in src, never called/imported)

| Symbol | Location | Evidence |
|--------|----------|----------|
| `cli_listener()` | `core/events.py:112` | Never imported anywhere. Grep confirms 0 imports. |
| `export_compliance_matrix()` | `export/excel_export.py:133` | Never imported or called anywhere. |
| `AGENT_REGISTRY` | `agents/base.py:27` | Populated by `@register_agent` but never read/iterated by any consumer. The graphs instantiate agents directly. |
| `AgentError` | `exceptions.py` | Never raised anywhere in the codebase. |

### 7.2 Unused Imports (imported but never used in the importing file)

| Import | Location | Evidence |
|--------|----------|----------|
| `discover_control_files` | `ui/app.py:73` | Imported but never called in app.py. |
| `get_assess_emitter` (aliased from `get_emitter`) | `ui/app.py:61` | Imported but never referenced. |
| `set_current_trace_context` | `graphs/classify_graph.py:33` | Imported but never called (used inside trace_node decorator). |
| `set_current_trace_context` | `graphs/assess_graph.py:39` | Same — imported but never called directly. |
| `derive_inherent_rating` | `graphs/assess_graph.py:44` | Imported but only used by `risk_extractor_scorer`, not in this file. |

### 7.3 Pydantic Models Defined but Not Used in Production

| Model | Location | Usage |
|-------|----------|-------|
| `GapReport` | `core/models.py:150` | Only used in `tests/test_models.py`. Graphs build gap_report as a plain dict. |
| `ComplianceMatrix` | `core/models.py:161` | Same — only in tests. |
| `RiskRegister` | `core/models.py:167` | Same — only in tests. |
| `ClassifiedObligation` | `core/models.py:86` | Only in tests. Graphs use plain dicts. |
| `ObligationAPQCMapping` | `core/models.py:101` | Only in tests. |
| `CoverageAssessment` | `core/models.py:113` | Only in tests. |
| `ScoredRisk` | `core/models.py:130` | Only in tests. |

These models define the correct schema but the pipeline passes dicts instead. This is a design decision (TypedDicts in graph state vs frozen models), but it means validation is manual rather than Pydantic-enforced.

### 7.4 Potentially Unused Dependencies

| Package | Status |
|---------|--------|
| `langchain-core` | ⚠️ Never directly imported. Likely a transitive dependency of `langgraph`. May be safely removable from `pyproject.toml` if langgraph declares it. |
| `pytest-asyncio` | ⚠️ No async tests exist in the test suite. |

### 7.5 Files/Modules That Are Never Imported

| Path | Status |
|------|--------|
| `langgraph-multiagent-skeleton/` | Upstream reference project. Not part of the regrisk package. Could be moved to a separate location. |
| `doc/plan.md` | Original implementation plan. Documentation only. |

---

## 8. Code Quality Observations

### 8.1 Missing Type Annotations

- **`ui/app.py`**: Most functions lack return type annotations. Many use `Any` for session state values.
- **`graphs/classify_graph.py` & `assess_graph.py`**: Module-level caches use `Any` type (`_llm_client_cache: Any`).
- **`export/excel_export.py`**: `export_gap_report()` accepts `path: str` but the UI calls it with a `BytesIO` object — type mismatch.

### 8.2 Magic Strings / Numbers

- Category names (`"Controls"`, `"Documentation"`, etc.) are repeated as bare strings in: `ui/app.py`, graph nodes, agent fallbacks, and validator.
- Coverage statuses (`"Covered"`, `"Partially Covered"`, `"Not Covered"`) repeated across agents, graphs, UI, validator.
- Relationship types and criticality tiers repeated similarly.
- `config/default.yaml` defines these, and `validator.py` defines `VALID_*` sets, but they aren't used consistently across all modules.
- `"data/traces.db"` hardcoded in `ui/app.py`.
- `"gpt-4o"` default model repeated in `classify_graph.py` and `assess_graph.py`.

### 8.3 Error Handling

- `classify_graph.py` `ingest_node`: catches bare `Exception` for regulation/APQC/control parsing — appends to errors list but continues. Reasonable for resilience but should log with traceback.
- `ui/app.py`: Several `try/except Exception` blocks that show `st.warning()` but don't log.
- `core/events.py` `EventEmitter.emit()`: Catches and prints exceptions from listeners — should use `logging`.

### 8.4 DRY Violations

- **Graph module-level singletons**: `classify_graph.py` and `assess_graph.py` duplicate identical patterns for: `_emitter`, `_llm_client_cache`, `_agent_cache`, `_event_loop`, `set_emitter()`, `get_emitter()`, `_emit()`, `_get_loop()`, `_build_context()`, `_get_agent()`, `reset_caches()`, `_install_tracing_transport()`. This is ~80 lines duplicated.
- **`_display_col_name()` and `_COL_DISPLAY_OVERRIDES`**: Duplicated identically in `ui/app.py` and `export/excel_export.py`.
- **`_clean_str()`**: Duplicated in `regulation_parser.py` and `control_loader.py`.
- **Obligation data access pattern**: `ob.get("field", "") if isinstance(ob, dict) else ob.field` repeated in `obligation_classifier.py`.

### 8.5 Function Length

| Function | File | Approx Lines | Issue |
|----------|------|-------------|-------|
| `_render_upload_tab()` | `ui/app.py` | ~210 | Should be decomposed (data sources + scope + launch are 3 logical blocks) |
| `_render_traceability_tab()` | `ui/app.py` | ~180 | Multiple logical sections (run selector, overview, timeline, nodes, LLM calls, maintenance) |
| `_render_results_tab()` | `ui/app.py` | ~90 | Borderline |
| `_run_assessment()` | `ui/app.py` | ~85 | Duplicates setup logic from `_run_mapping()` |
| `chat_completion()` | `core/transport.py` | ~120 | Complex retry/URL-discovery logic — necessary complexity but warrants section comments |
| `finalize_node()` | `graphs/assess_graph.py` | ~75 | Borderline |

### 8.6 Naming Issues

- `_get_loop()` — in both graph modules. Name is vague; `_get_or_create_event_loop()` would be clearer.
- `_build_context()` — also vague. `_build_agent_context()` better.
- `_emit()` — very generic name for module-level function.
- `data` — used as variable name in several places (e.g., checkpoints, config loading).

### 8.7 Inline Import Hack

`assess_graph.py:220` does:
```python
__import__("regrisk.core.models", fromlist=["ControlRecord"]).ControlRecord(**c)
```
This should be a normal top-level import — `ControlRecord` is already indirectly available via `core/models` and there's no circular dependency.

---

## 9. Architecture Observations

### 9.1 Clean Separations

✅ **Ingest layer** is fully deterministic — no LLM calls, no side effects.  
✅ **Agents** follow a consistent ABC pattern with deterministic fallbacks.  
✅ **Tracing** is fully decoupled via decorator + wrapper pattern.  
✅ **Validation** is stateless and deterministic.  
✅ **No circular dependencies** in the import graph.  
✅ **Config** is separated from code (YAML + JSON + env vars).  

### 9.2 Layer Violations

| Issue | Severity |
|-------|----------|
| `ui/app.py` imports from `ingest/` directly to render data previews. This is reasonable (UI needs data) but bypasses the graph pipeline for preview rendering. | Low |
| `agents/base.py` imports `tracing.decorators` at call time. This cross-layer reference (agent → tracing) is needed for trace context propagation but is non-obvious. | Low |

### 9.3 Module Placement Issues

| Issue | Suggestion |
|-------|-----------|
| `derive_inherent_rating()` in `validation/validator.py` is a pure business logic function (impact × frequency → rating), not a validator. | Could move to `core/models.py` or a `core/scoring.py` module. |
| `build_apqc_summary()` in `ingest/apqc_loader.py` produces LLM prompt text — this is prompt engineering, not data ingestion. | Could stay, but consider a `prompts/` module if prompt logic grows. |

### 9.4 `ui/app.py` Size (1564 lines)

This file handles:
1. CSS styling
2. Data preview (regulation, APQC, controls)
3. Scope selection UI
4. Graph invocation (classify + map + assess)
5. Classification review table + export/import
6. Mapping review table + export/import
7. Results dashboard (metrics, heatmap, gaps, risks)
8. Traceability viewer (run selector, timeline, node inspector, LLM inspector)
9. Data lineage chains
10. Checkpoint save/load UI

**Recommendation:** Split into:
- `ui/app.py` — Main layout, tabs, entry point
- `ui/upload_tab.py` — Tab 1 (upload, scope, launch)
- `ui/review_tabs.py` — Tabs 2-3 (classification + mapping review)
- `ui/results_tab.py` — Tab 4 (dashboard, heatmap, gaps)
- `ui/traceability_tab.py` — Tab 5 (trace viewer, lineage)
- `ui/components.py` — Shared rendering helpers (`_render_html_table`, etc.)

---

## 10. Testing Coverage Map

| Module | Test File | Coverage Notes |
|--------|-----------|---------------|
| `core/config.py` | — | ❌ **No tests.** `PipelineConfig`, `load_config()` untested. |
| `core/events.py` | — | ❌ **No tests.** `EventEmitter`, `PipelineEvent` untested. |
| `core/models.py` | `test_models.py` (204 lines) | ✅ All 11 models tested for construction and field validation. |
| `core/transport.py` | — | ❌ **No tests.** `AsyncTransportClient`, retry logic, URL discovery untested. |
| `exceptions.py` | — | ❌ **No tests.** (Trivial — low priority.) |
| `agents/base.py` | — | ❌ **No tests.** `BaseAgent.call_llm()`, `parse_json()`, `call_llm_with_tools()` untested. |
| `agents/obligation_classifier.py` | — | ❌ **No tests.** Deterministic fallback `_deterministic_classify()` untested. |
| `agents/apqc_mapper.py` | — | ❌ **No tests.** Deterministic fallback `_deterministic_map()` untested. |
| `agents/coverage_assessor.py` | — | ❌ **No tests.** |
| `agents/risk_extractor_scorer.py` | — | ❌ **No tests.** |
| `graphs/classify_graph.py` | `test_classify_graph.py` (79 lines) | ⚠️ Integration test only — builds and runs full graph in deterministic mode. |
| `graphs/assess_graph.py` | `test_assess_graph.py` (106 lines) | ⚠️ Integration test only. |
| `ingest/regulation_parser.py` | `test_ingest.py` | ✅ `parse_regulation_excel()`, `group_obligations()` tested. |
| `ingest/apqc_loader.py` | `test_ingest.py` | ✅ `load_apqc_hierarchy()`, `build_apqc_summary()`, `get_apqc_subtree()` tested. |
| `ingest/control_loader.py` | `test_ingest.py` | ✅ `discover_control_files()`, `load_and_merge_controls()`, `build_control_index()`, `find_controls_for_apqc()` tested. |
| `export/excel_export.py` | — | ❌ **No tests.** `export_gap_report()`, `export_for_review()`, `import_reviewed()` untested. |
| `tracing/db.py` | `test_tracing.py` (300 lines) | ✅ Comprehensive — all CRUD operations and queries. |
| `tracing/decorators.py` | `test_tracing.py` | ✅ `trace_node` decorator tested. |
| `tracing/listener.py` | `test_tracing.py` | ✅ `SQLiteTraceListener` tested. |
| `tracing/transport_wrapper.py` | `test_tracing.py` | ✅ `TracingTransportClient` tested. |
| `validation/validator.py` | `test_validator.py` (227 lines) | ✅ All 5 validators + `derive_inherent_rating()` tested. |
| `ui/app.py` | — | ❌ **No tests.** (1564 lines untested — highest risk.) |
| `ui/checkpoint.py` | — | ❌ **No tests.** `save_checkpoint()`, `load_checkpoint()`, `list_checkpoints()` untested. |

### Priority Testing Gaps

1. **`agents/base.py`** — `parse_json()` handles messy LLM output; `call_llm()` has complex fallback behavior. High value.
2. **`agents/*` deterministic fallbacks** — These run in CI/demos. Need unit tests.
3. **`core/transport.py`** — Retry logic, URL discovery, provider detection. Critical for LLM mode.
4. **`export/excel_export.py`** — `import_reviewed()` reads user-provided files. Input validation matters.
5. **`ui/checkpoint.py`** — Checkpoint integrity is critical for resumability.
6. **`core/config.py`** — Config loading validation.

---

## Summary of Findings

### Phase 2 Targets (Dead Code Removal)

1. Remove `cli_listener()` from `core/events.py`
2. Remove `export_compliance_matrix()` from `export/excel_export.py`
3. Remove unused import `discover_control_files` from `ui/app.py`
4. Remove unused import `get_assess_emitter` from `ui/app.py`
5. Remove unused imports `set_current_trace_context` from both graph modules
6. Remove unused import `derive_inherent_rating` from `graphs/assess_graph.py`
7. Flag `AGENT_REGISTRY` as dead code (populated but never consumed)
8. Flag `AgentError` as dead code (defined but never raised)
9. Flag `langchain-core` and `pytest-asyncio` in pyproject.toml
10. Flag unused Pydantic models as candidates for integration (use them instead of dicts)

### Phase 3 Priorities (Code Quality)

1. Decompose `ui/app.py` (1564 lines → 5-6 files)
2. Extract shared graph infrastructure (~80 duplicated lines)
3. Consolidate magic strings into constants/config references
4. Add docstrings to all public functions
5. Complete type annotations
6. Fix `export_gap_report()` type signature (`path` vs `BytesIO`)
7. Replace `__import__` hack in assess_graph.py
8. Add section comments to `transport.py` retry logic

### Phase 4 Priorities (Architecture)

1. Move `derive_inherent_rating()` to a more appropriate module
2. Evaluate whether Pydantic models should replace raw dicts in graph state

### Phase 5 Priorities (Documentation)

1. README.md is accurate — minor updates needed
2. ARCHITECTURE.md is comprehensive and current
3. `ui/app.py` needs section separators and navigation comments

---

*End of Phase 1 audit. Awaiting approval to proceed to Phase 2.*
