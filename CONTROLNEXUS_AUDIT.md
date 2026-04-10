# CONTROLNEXUS_AUDIT.md — Comprehensive Code Audit

> Generated 2026-04-09 as Phase 1 of the production-quality cleanup.
> No changes have been made to the codebase yet.
> Covers the entire ControlNexus repository (all modules), not just a single pipeline.

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
11. [Cross-Module Analysis](#11-cross-module-analysis)
12. [Cross-Cutting Findings](#12-cross-cutting-findings)

---

## 1. Directory Tree

```
.
├── pyproject.toml                                      # Package metadata + deps
├── Dockerfile                                          # Python 3.11-slim, Streamlit entrypoint
├── README.md                                           # Quick-start guide
├── Architecture.md                                     # Technical reference (18 sections)
├── CONTROLNEXUS_AUDIT.md                               # ← this file
├── .streamlit/config.toml                              # Streamlit config
├── config/
│   ├── taxonomy.yaml                         (358 L)   # 25 control types + 17 business units
│   ├── placement_methods.yaml                 (44 L)   # Placements, methods, control_taxonomy
│   ├── standards.yaml                         (25 L)   # Five-W rules, phrase bank, quality ratings
│   ├── profiles/
│   │   ├── banking_standard.yaml           (1678 L)   # Full banking org config (25 types, 17 BUs)
│   │   └── community_bank_demo.yaml         (102 L)   # Minimal demo config (3 types, 2 BUs)
│   └── sections/
│       ├── section_1.yaml … section_13.yaml            # 13 section profiles (71–131 L each)
├── data/                                               # Runtime data directory
├── docs/
│   ├── control-forge-modular.md                        # ControlForge Modular guide
│   ├── control-forge.md                                # Legacy ControlForge reference
│   ├── gap-analysis.md                                 # Gap analysis & remediation guide
│   └── langgraph-multiagent-skeleton.md                # Skeleton overview
├── langgraph-multiagent-skeleton/                      # Upstream reference (not on main yet)
│   ├── Dockerfile, PATTERNS.md, README.md, pyproject.toml
│   ├── config/default.yaml
│   ├── src/skeleton/                                   # Source files on feature branch only
│   │   ├── agents/ core/ export/ graphs/ tools/ ui/ validation/
│   └── tests/
├── output/                                             # UI-generated output files
├── src/
│   └── controlnexus/
│       ├── __init__.py                        (3 L)    # __version__ = "0.1.0"
│       ├── exceptions.py                     (13 L)    # 3 exception classes
│       ├── agents/                                     # LLM agent implementations
│       │   ├── __init__.py                   (20 L)    # Barrel exports
│       │   ├── base.py                      (409 L)    # BaseAgent ABC, AgentContext, registry
│       │   ├── adversarial.py                (69 L)    # AdversarialReviewer (red-team)
│       │   ├── differentiator.py             (72 L)    # DifferentiationAgent (dedup)
│       │   ├── enricher.py                   (69 L)    # EnricherAgent (quality refinement)
│       │   ├── narrative.py                  (71 L)    # NarrativeAgent (5W narrative)
│       │   └── spec.py                       (88 L)    # SpecAgent (locked specification)
│       ├── analysis/                                   # Gap analysis scanners
│       │   ├── __init__.py                    (1 L)    # Docstring only
│       │   ├── ingest.py                    (140 L)    # Excel → FinalControlRecord
│       │   ├── pipeline.py                  (136 L)    # 4-scanner orchestrator
│       │   ├── register_analyzer.py                    # Heuristic register summarizer
│       │   └── scanners.py                  (344 L)    # Regulatory/balance/frequency/evidence
│       ├── core/                                       # Foundation layer
│       │   ├── __init__.py                    (0 L)    # Empty
│       │   ├── config.py                    (113 L)    # YAML loaders (taxonomy, sections, etc.)
│       │   ├── constants.py                  (97 L)    # TYPE_CODE_MAP, frequency rules, ID builders
│       │   ├── domain_config.py             (363 L)    # DomainConfig Pydantic model (single YAML)
│       │   ├── events.py                    (119 L)    # EventType enum, EventEmitter, PipelineEvent
│       │   ├── models.py                    (194 L)    # RunConfig, TaxonomyCatalog, SectionProfile, etc.
│       │   ├── state.py                     (274 L)    # Pipeline state models (HierarchyNode → FinalControlRecord)
│       │   └── transport.py                 (205 L)    # AsyncTransportClient, multi-provider factory
│       ├── export/                                     # Excel output
│       │   ├── __init__.py                    (1 L)    # Docstring only
│       │   └── excel.py                      (75 L)    # FinalControlRecord → Excel
│       ├── graphs/                                     # LangGraph state machines
│       │   ├── __init__.py                    (1 L)    # Docstring only
│       │   ├── state.py                      (73 L)    # AnalysisState, RemediationState TypedDicts
│       │   ├── analysis_graph.py            (187 L)    # Gap analysis graph (8 nodes)
│       │   ├── forge_modular_graph.py       (770 L)    # ControlForge Modular graph (8 nodes)
│       │   ├── forge_modular_helpers.py     (739 L)    # Helpers: assignment matrix, prompts, etc.
│       │   └── remediation_graph.py         (269 L)    # Remediation graph (11 nodes)
│       ├── hierarchy/                                  # APQC hierarchy parsing
│       │   ├── __init__.py                   (14 L)    # Re-exports
│       │   ├── parser.py                    (272 L)    # Excel/CSV → HierarchyNode list
│       │   └── scope.py                      (61 L)    # Section filtering, breakdown
│       ├── memory/                                     # ChromaDB vector store
│       │   ├── __init__.py                    (6 L)    # Re-exports
│       │   ├── embedder.py                   (49 L)    # Embedding abstraction
│       │   └── store.py                     (214 L)    # ControlMemory (index, query, dedup)
│       ├── pipeline/                                   # Legacy orchestrator
│       │   ├── __init__.py                   (13 L)    # Re-exports
│       │   └── orchestrator.py            (1055 L)    # End-to-end pipeline (3-phase generation)
│       ├── remediation/                                # Gap remediation logic
│       │   ├── __init__.py                    (1 L)    # Docstring only
│       │   ├── paths.py                      (85 L)    # Gap-type routing (4 paths)
│       │   └── planner.py                    (78 L)    # GapReport → ControlAssignment list
│       ├── tools/                                      # Agent function calling
│       │   ├── __init__.py                   (21 L)    # Re-exports
│       │   ├── schemas.py                   (181 L)    # 8 tool schemas (OpenAI format)
│       │   ├── implementations.py           (157 L)    # Pure Python tool functions
│       │   ├── domain_tools.py              (286 L)    # DomainConfig-aware tool variants
│       │   ├── nodes.py                      (87 L)    # LangGraph ToolNode wrapper
│       │   └── xml_tool_parser.py            (68 L)    # ICA XML tool-call simulation
│       ├── ui/                                         # Streamlit dashboard
│       │   ├── __init__.py                    (1 L)
│       │   ├── app.py                       (146 L)    # Main entrypoint (5 tabs)
│       │   ├── controlforge_tab.py          (587 L)    # Legacy ControlForge tab
│       │   ├── modular_tab.py               (348 L)    # ControlForge Modular tab
│       │   ├── playground.py                (319 L)    # Agent playground
│       │   ├── styles.py                    (306 L)    # CSS, colors, theme utilities
│       │   ├── components/
│       │   │   ├── __init__.py                (1 L)
│       │   │   ├── analysis_runner.py        (74 L)
│       │   │   ├── data_table.py            (371 L)    # Rich data table component
│       │   │   ├── remediation_runner.py    (521 L)    # Remediation UI panel
│       │   │   └── upload.py                 (66 L)    # Excel upload component
│       │   └── renderers/
│       │       ├── __init__.py                (1 L)
│       │       └── gap_dashboard.py         (168 L)    # Gap analysis charts
│       └── validation/                                 # Deterministic validator
│           ├── __init__.py                    (0 L)
│           └── validator.py                 (233 L)    # 6-rule validator + retry appendix
└── tests/
    ├── __init__.py                            (0 L)
    ├── conftest.py                          (181 L)    # Shared fixtures
    ├── test_agents.py                       (415 L)    # 26 tests
    ├── test_config.py                       (122 L)    # 19 tests
    ├── test_config_proposer.py                         # ConfigProposer tests (feature branch)
    ├── test_config_wizard.py                           # Config wizard tests (feature branch)
    ├── test_constants.py                     (73 L)    # 14 tests
    ├── test_domain_config.py                (296 L)    # 28 tests
    ├── test_domain_tools.py                 (225 L)    # 23 tests
    ├── test_e2e.py                          (419 L)    # 13 tests
    ├── test_export.py                        (62 L)    # 5 tests
    ├── test_forge_modular_graph.py         (1216 L)    # 83 tests
    ├── test_graphs.py                       (149 L)    # 14 tests
    ├── test_ingest.py                       (198 L)    # 11 tests
    ├── test_memory.py                       (176 L)    # 14 tests
    ├── test_models.py                       (215 L)    # 23 tests
    ├── test_pipeline.py                     (101 L)    # 5 tests
    ├── test_remediation.py                  (166 L)    # 15 tests
    ├── test_scanners.py                     (231 L)    # 17 tests
    ├── test_tools.py                        (296 L)    # 29 tests
    ├── test_transport.py                    (189 L)    # 16 tests
    ├── test_validator.py                    (228 L)    # 36 tests
    ├── test_xml_tool_parser.py              (171 L)    # 14 tests
    └── fixtures/
        └── _create_fixtures.py
```

**Total source lines:** 10,705 (src/controlnexus/) + 5,129 (tests/) = **~15,834 lines**
**Total tests:** 405 (pytest-collected)
**Config lines:** ~3,530 (YAML)

---

## 2. Module Dependency Graph

### Internal dependency direction (arrows = "imports from")

```
Layer 0 — No internal deps (foundation):
  exceptions.py                     # 3 exception classes
  core/constants.py                 # TYPE_CODE_MAP, frequency rules, ID builders
  core/events.py                    # EventType enum, PipelineEvent, EventEmitter
  core/models.py                    # RunConfig, TaxonomyCatalog, etc. (pydantic only)
  core/state.py                     # HierarchyNode → FinalControlRecord (pydantic only)
  tools/schemas.py                  # Tool schema dicts (no deps)
  tools/xml_tool_parser.py          # XML parsing (re only)
  memory/embedder.py                # Embedder ABC (deferred sentence_transformers)
  ui/styles.py                      # CSS/color constants (streamlit only)

Layer 1 — Depends on Layer 0:
  core/config.py                    → core/models
  core/transport.py                 → exceptions
  core/domain_config.py             → (pydantic + yaml only, no internal deps)
  hierarchy/parser.py               → core/state
  hierarchy/scope.py                → (no internal deps — HierarchyNode from caller)
  validation/validator.py           → core/state
  export/excel.py                   → core/state
  remediation/paths.py              → (no internal deps — pure logic)
  remediation/planner.py            → (no internal deps — pure logic)

Layer 2 — Depends on Layers 0–1:
  agents/base.py                    → core/transport, exceptions, tools/xml_tool_parser
  analysis/ingest.py                → core/state
  analysis/scanners.py              → core/constants, core/models, core/state
  analysis/pipeline.py              → analysis/scanners, core/models, core/state
  tools/implementations.py          → core/constants, core/models
  tools/domain_tools.py             → core/domain_config
  tools/nodes.py                    → tools/implementations
  memory/store.py                   → memory/embedder

Layer 3 — Depends on Layers 0–2:
  agents/spec.py                    → agents/base, exceptions
  agents/narrative.py               → agents/base, exceptions
  agents/enricher.py                → agents/base, exceptions
  agents/differentiator.py          → agents/base
  agents/adversarial.py             → agents/base
  graphs/state.py                   → (no internal deps — defines add() reducer)
  graphs/forge_modular_helpers.py   → core/domain_config

Layer 4 — Orchestration hubs:
  graphs/analysis_graph.py          → analysis/{ingest, pipeline, scanners},
                                      core/{config, models, state},
                                      graphs/state                             (7 deps)
  graphs/remediation_graph.py       → graphs/state, remediation/{paths, planner},
                                      validation/validator                     (4 deps)
  graphs/forge_modular_graph.py     → agents/base, core/{domain_config, events,
                                      transport}, graphs/forge_modular_helpers,
                                      tools/{domain_tools, schemas},
                                      validation/validator                     (15+ deps)
  pipeline/orchestrator.py          → agents/{spec, narrative, enricher},
                                      agents/base, core/{config, models, state,
                                      transport}, export/excel, hierarchy/{parser,
                                      scope}, validation/validator             (12+ deps)

Layer 5 — UI (top-level):
  ui/app.py                         → ui/styles (tab imports are deferred via functions)
  ui/controlforge_tab.py            → pipeline/orchestrator, core/{config, state},
                                      export/excel, hierarchy/{parser, scope}
  ui/modular_tab.py                 → core/{domain_config, events},
                                      graphs/forge_modular_graph,
                                      ui/components/data_table
  ui/playground.py                  → agents, core/transport
  ui/components/analysis_runner.py  → analysis/pipeline, core/models
  ui/components/remediation_runner.py → core/state
  ui/components/upload.py           → analysis/ingest
  ui/renderers/gap_dashboard.py     → core/state, ui/styles
```

### Circular dependencies

**None detected.** The dependency graph is a clean DAG from bottom (exceptions, models) to top (UI).

### Deferred/inline imports

- `memory/embedder.py` line ~33: `from sentence_transformers import SentenceTransformer` inside `__init__()` — defers heavy ML dependency.
- No `__import__()` hacks found.

---

## 3. Public Interfaces by Module

### `controlnexus.exceptions` (13 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `AgentExecutionException` | Exception | Agent execution failures |
| `ExternalServiceException` | Exception | LLM API call failures |
| `ValidationException` | Exception | Validation failures |

### `controlnexus.core.config` (113 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `ConfigValidationError` | Exception | Config validation failures |
| `load_taxonomy()` | Function | YAML → list[TaxonomyItem] |
| `load_taxonomy_catalog()` | Function | YAML → TaxonomyCatalog |
| `load_section_profile()` | Function | YAML → SectionProfile |
| `load_section_profiles()` | Function | Load multiple sections |
| `load_all_section_profiles()` | Function | Load all 13 sections |
| `load_run_config()` | Function | YAML → RunConfig |
| `load_standards()` | Function | YAML → dict (five W, phrase bank, quality ratings) |
| `load_placement_methods()` | Function | YAML → dict (placements, methods, taxonomy) |
| `default_paths()` | Function | Returns (taxonomy_path, config_dir) tuple |

### `controlnexus.core.constants` (97 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `MAX_CONTROL_TARGET` | int | `10000` |
| `TYPE_CODE_MAP` | dict | 13 control type → 3-letter code mappings **⚠️ Incomplete — orchestrator.py has 24** |
| `FREQUENCY_ORDERED_RULES` | list[tuple] | 6 frequency detection rules |
| `derive_frequency_from_when()` | Function | Free-text → frequency string |
| `type_to_code()` | Function | Control type name → 3-letter code |
| `build_control_id()` | Function | Hierarchy ID + type code + sequence → control ID |

### `controlnexus.core.domain_config` (363 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `FrequencyTier` | Pydantic model | Name, rank, display, min_frequency pair |
| `ControlTypeConfig` | Pydantic model | Control type with code, default frequency, placement |
| `BusinessUnitConfig` | Pydantic model | BU with sections, key types, regulatory exposure |
| `AffinityConfig` | Pydantic model | Section affinity matrix (HIGH/MEDIUM/LOW/NONE) |
| `RegistryConfig` | Pydantic model | Roles, systems, evidence, triggers, frameworks |
| `ExemplarConfig` | Pydantic model | Reference control examples |
| `RiskProfileConfig` | Pydantic model | Inherent/regulatory/density risk scores |
| `ProcessAreaConfig` | Pydantic model | Section with domain, risk profile, affinity, registry |
| `DomainConfig` | Pydantic model | Master config (single-YAML source of truth) |
| `load_domain_config()` | Function | YAML → DomainConfig |

### `controlnexus.core.events` (119 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `EventType` | Enum (17 members) | PIPELINE_*, STAGE_*, AGENT_*, VALIDATION_*, TOOL_*, ITEM_*, WARNING |
| `PipelineEvent` | frozen dataclass | Immutable event with type, message, data, timestamp, run_id, stage |
| `EventListener` | Protocol | Callable protocol for observers |
| `EventEmitter` | Class | Fan-out event dispatcher with `.emit()`, `.on()` |
| `cli_listener()` | Function | **⚠️ Defined but never imported/used anywhere** |

### `controlnexus.core.models` (194 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `RiskProfile` | frozen Pydantic | inherent_risk, regulatory_intensity, control_density |
| `AffinityMatrix` | frozen Pydantic | HIGH/MEDIUM/LOW/NONE type lists |
| `DomainRegistry` | frozen Pydantic | Roles, systems, evidence, triggers, frameworks |
| `ExemplarControl` | frozen Pydantic | Reference control example |
| `SectionProfile` | frozen Pydantic | Section config with id, name, domain, risk, affinity, registry, exemplars |
| `ScopeConfig` | Pydantic | Sections list, subsection_prefix |
| `InputConfig` | Pydantic | hierarchy_path, control_register_path, config_dir |
| `SizingConfig` | Pydantic | target_count, per_section overrides |
| `CheckpointConfig` | Pydantic | save_checkpoints, checkpoint_dir |
| `TransportConfig` | Pydantic | model_override, temperature, max_tokens, timeout |
| `ConcurrencyConfig` | Pydantic | max_concurrent |
| `OutputConfig` | Pydantic | output_dir, filename, json_output |
| `RunConfig` | Pydantic | Top-level config aggregating all above |
| `TaxonomyItem` | frozen Pydantic | control_type, definition |
| `BusinessUnitProfile` | frozen Pydantic | BU with sections, key types, regulatory exposure |
| `TaxonomyCatalog` | frozen Pydantic | Full taxonomy catalog with control_types, business_units |

### `controlnexus.core.state` (274 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `HierarchyNode` | frozen Pydantic | APQC hierarchy node (8 fields) |
| `ControlAssignment` | frozen Pydantic | Control assignment for generation |
| `SpecResult` | frozen Pydantic | LLM spec output |
| `NarrativeResult` | frozen Pydantic | LLM narrative output |
| `EnrichmentResult` | frozen Pydantic | LLM enrichment output |
| `ValidationResult` | frozen Pydantic | Validator output (passed, failures, metrics) |
| `LLMEnrichmentResult` | frozen Pydantic | Combined LLM enrichment |
| `PreparedControl` | frozen Pydantic | Pre-LLM control with deterministic defaults |
| `FinalControlRecord` | frozen Pydantic | 22+ fields, `to_export_dict()` method |
| `GapReport` | frozen Pydantic | Gap analysis output |

### `controlnexus.core.transport` (205 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `AsyncTransportClient` | dataclass | Async httpx chat-completion client (multi-provider) |
| `build_client_from_env()` | Function | Auto-detect ICA/OpenAI/Anthropic from env vars |

### `controlnexus.agents.base` (409 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `AGENT_REGISTRY` | dict | Populated by `@register_agent`, consumed by `ui/playground.py` |
| `register_agent` | Decorator | Registers agent class by name |
| `AgentContext` | dataclass | Runtime context (client, model, temp, tokens, timeout) |
| `BaseAgent` | ABC | `execute()`, `call_llm()`, `call_llm_with_tools()`, `call_llm_with_xml_tools()`, `parse_json()` |

### `controlnexus.agents.*` (5 concrete agents)

| Agent | Lines | Method | Description |
|-------|-------|--------|-------------|
| `SpecAgent` | 88 | `execute()` | Locked control specification |
| `NarrativeAgent` | 71 | `execute()` | 5W narrative from spec |
| `EnricherAgent` | 69 | `execute()` | Quality refinement + rating |
| `DifferentiationAgent` | 72 | `execute()` | Semantic deduplication |
| `AdversarialReviewer` | 69 | `execute()` | Red-team control criticism |

### `controlnexus.analysis` (4 files, 620 lines)

| Symbol | Location | Description |
|--------|----------|-------------|
| `ingest_excel()` | `ingest.py` | Excel → list[FinalControlRecord] |
| `run_analysis()` | `pipeline.py` | 4-scanner orchestrator → GapReport |
| `regulatory_coverage_scan()` | `scanners.py` | Regulatory gap detection |
| `ecosystem_balance_analysis()` | `scanners.py` | Affinity distribution check |
| `frequency_coherence_scan()` | `scanners.py` | Frequency appropriateness |
| `evidence_sufficiency_scan()` | `scanners.py` | Evidence quality scoring |

### `controlnexus.graphs` (5 files, 2,039 lines)

| Symbol | Location | Description |
|--------|----------|-------------|
| `add()` | `state.py` | LangGraph list reducer |
| `AnalysisState` | `state.py` | Gap analysis graph state TypedDict |
| `RemediationState` | `state.py` | Remediation graph state TypedDict |
| `build_analysis_graph()` | `analysis_graph.py` | 8-node analysis graph |
| `build_forge_graph()` | `forge_modular_graph.py` | 8-node ControlForge graph |
| `build_remediation_graph()` | `remediation_graph.py` | 11-node remediation graph |
| `build_assignment_matrix()` | `forge_modular_helpers.py` | Weighted control distribution |
| `build_deterministic_spec()` | `forge_modular_helpers.py` | Deterministic spec builder |
| `build_deterministic_narrative()` | `forge_modular_helpers.py` | Deterministic narrative builder |
| `build_deterministic_enriched()` | `forge_modular_helpers.py` | Deterministic enrichment builder |
| `_add()` | `forge_modular_graph.py` | **⚠️ Duplicate of `add()` in state.py** |

### `controlnexus.pipeline.orchestrator` (1,055 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `PlanningResult` | dataclass | Planning phase output |
| `Orchestrator` | Class | End-to-end pipeline (hierarchy → scope → sizing → generation → export) |
| `MAX_CONTROL_TARGET` | int | **⚠️ Duplicate of `core/constants.py`** |
| `TYPE_CODE_MAP` | dict | **⚠️ Duplicate (24 entries vs. 13 in constants.py)** |
| `FREQUENCY_ORDERED_RULES` | list | **⚠️ Duplicate of `core/constants.py`** |
| `_derive_frequency_from_when()` | Function | **⚠️ Duplicate of `core/constants.py`** |

### `controlnexus.tools` (5 files, 800 lines)

| Symbol | Location | Description |
|--------|----------|-------------|
| `TOOL_SCHEMAS` / individual schemas | `schemas.py` | 8 OpenAI-format tool schemas |
| `taxonomy_validator()` etc. | `implementations.py` | 5 pure Python tool functions |
| `dc_taxonomy_validator()` etc. | `domain_tools.py` | 5 DomainConfig-aware tool functions |
| `build_domain_tool_executor()` | `domain_tools.py` | Closure factory for agent use |
| `execute_tool_call()` | `nodes.py` | Single tool dispatch |
| `tool_node()` | `nodes.py` | LangGraph ToolNode wrapper |
| `parse_xml_tool_calls()` | `xml_tool_parser.py` | ICA XML tool-call extraction |
| `format_tool_results()` | `xml_tool_parser.py` | XML tool result formatting |
| `strip_tool_calls()` | `xml_tool_parser.py` | Strip XML blocks from text |

### `controlnexus.validation.validator` (233 lines)

| Symbol | Type | Description |
|--------|------|-------------|
| `VAGUE_WHEN_TERMS` | set | Trigger words for vague-when rule |
| `RISK_MARKERS` | set | Risk-indicating words for why-missing-risk rule |
| `MIN_WORDS` / `MAX_WORDS` | int | 30 / 80 default word count bounds |
| `validate()` | Function | 6-rule narrative validator → ValidationResult |
| `build_retry_appendix()` | Function | Failure-specific retry guidance |

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
| `OPENAI_MODEL_ID` | `core/transport.py` | `gpt-4o` | OpenAI model name |
| `ANTHROPIC_API_KEY` | `core/transport.py` | — | Anthropic API key |
| `.env` file | `ui/app.py` | — | Loaded via `python-dotenv` at app startup |

### 4.2 YAML Configuration

| File | Purpose | Key Settings |
|------|---------|-------------|
| `config/taxonomy.yaml` | 25 control types + 17 business units | Type definitions, BU mappings |
| `config/placement_methods.yaml` | 3 placements, 3 methods, control taxonomy tree | Preventive/Detective/Contingency |
| `config/standards.yaml` | Five-W rules, phrase bank, quality ratings | Narrative standards |
| `config/sections/section_*.yaml` | 13 section profiles | Domain, risk profile, affinity, registry, exemplars |
| `config/profiles/banking_standard.yaml` | Full banking org config | 25 types, 17 BUs, 13 sections |
| `config/profiles/community_bank_demo.yaml` | Minimal demo config | 3 types, 2 BUs, 2 sections |

### 4.3 Pydantic Config Models

| Model | Source | Purpose |
|-------|--------|---------|
| `RunConfig` | `core/models.py` | Orchestrator pipeline config (scope, sizing, transport, output) |
| `DomainConfig` | `core/domain_config.py` | ControlForge Modular config (single-YAML source of truth) |
| `TaxonomyCatalog` | `core/models.py` | Taxonomy reference (control types + business units) |

---

## 5. External Dependencies

### 5.1 Runtime Dependencies (from pyproject.toml)

| Package | Version | Used by | How |
|---------|---------|---------|-----|
| `pydantic` | ≥2.0 | `core/*.py`, `agents/base.py` | Frozen models, field validators |
| `httpx` | ≥0.25 | `core/transport.py` | Async HTTP client for LLM APIs |
| `openpyxl` | ≥3.1 | `analysis/ingest.py`, `export/excel.py`, `hierarchy/parser.py` | Excel I/O |
| `pyyaml` | ≥6.0 | `core/config.py`, `core/domain_config.py` | YAML config loading |
| `python-dotenv` | ≥1.0 | `ui/app.py` | `.env` file loading |
| `langgraph` | ≥0.2 | `graphs/*.py` | StateGraph, END, START |
| `langchain-core` | ≥0.3 | **⚠️ Never directly imported** | Transitive dep of langgraph |
| `streamlit` | ≥1.35 | `ui/*.py` | Entire UI framework |
| `chromadb` | ≥0.5 | `memory/store.py` | Vector similarity search |
| `sentence-transformers` | ≥3.0 | `memory/embedder.py` | Embedding generation (deferred import) |

### 5.2 Dev Dependencies

| Package | Version | Used by |
|---------|---------|---------|
| `pytest` | ≥8.0 | Test runner |
| `pytest-asyncio` | ≥0.23 | `asyncio_mode = "auto"` in pyproject.toml — enables async test fixtures |
| `ruff` | ≥0.5 | Linter/formatter |
| `mypy` | ≥1.10 | Type checker |

### 5.3 Potentially Unused Dependencies

| Package | Status |
|---------|--------|
| `langchain-core` | ⚠️ Never directly imported. Transitive dep of langgraph. |

---

## 6. File Sizes and Complexity

### Files over 150 lines (ordered by size)

| File | Lines | Functions | Classes | Notes |
|------|-------|-----------|---------|-------|
| `pipeline/orchestrator.py` | **1,055** | ~30 | 2 | **⚠️ Largest file. Legacy monolith. Duplicates constants.** |
| `graphs/forge_modular_graph.py` | **770** | ~20 | 1 (ForgeState) | Largest graph. 8 nodes, event infra, tool calling. |
| `graphs/forge_modular_helpers.py` | **739** | ~20 | 0 | Assignment matrix, prompts, deterministic builders. |
| `ui/controlforge_tab.py` | **587** | ~15 | 0 | Legacy ControlForge UI. |
| `ui/components/remediation_runner.py` | **521** | ~15 | 0 | Remediation UI panel. |
| `agents/base.py` | **409** | 10 | 3 | Agent framework. Acceptable — clear responsibilities. |
| `ui/components/data_table.py` | **371** | ~8 | 0 | Rich data table. |
| `core/domain_config.py` | **363** | 3 | 9 | Pydantic models. Acceptable — pure data definitions. |
| `ui/modular_tab.py` | **348** | ~8 | 0 | ControlForge Modular UI. |
| `analysis/scanners.py` | **344** | 8 | 0 | 4 independent scanners. |
| `ui/playground.py` | **319** | ~10 | 0 | Agent testing UI. |
| `ui/styles.py` | **306** | ~12 | 0 | CSS/styling. |
| `tools/domain_tools.py` | **286** | 7 | 0 | DomainConfig tool wrappers. |
| `core/state.py` | **274** | 1 | 10 | Pipeline state models. Acceptable. |
| `hierarchy/parser.py` | **272** | 10 | 0 | Excel/CSV loader. |
| `graphs/remediation_graph.py` | **269** | 11 | 0 | 11-node graph. |
| `validation/validator.py` | **233** | 2 | 0 | 6 validation rules + retry appendix. |
| `memory/store.py` | **214** | 8 | 1 | ChromaDB wrapper. |
| `core/transport.py` | **205** | 5 | 1 | Async HTTP client. Complex retry logic. |
| `core/models.py` | **194** | 0 | 16 | Pure Pydantic models. |
| `graphs/analysis_graph.py` | **187** | 8 | 0 | 8-node graph. |
| `tools/schemas.py` | **181** | 0 | 0 | Pure schema definitions. |
| `ui/renderers/gap_dashboard.py` | **168** | ~6 | 0 | Gap analysis charts. |
| `tools/implementations.py` | **157** | 7 | 0 | Tool functions + module-level state. |

---

## 7. Dead Code and Unused Symbols

### 7.1 Unused Functions

| Symbol | Location | Evidence |
|--------|----------|----------|
| `cli_listener()` | `core/events.py:117` | Never imported anywhere. Grep confirms 0 imports. |

### 7.2 Duplicate Definitions (should be single-sourced)

| Symbol | Primary Location | Duplicate Location | Issue |
|--------|-----------------|-------------------|-------|
| `TYPE_CODE_MAP` | `core/constants.py:14` (13 entries) | `pipeline/orchestrator.py:46` (24 entries) | **Constants.py is incomplete**; orchestrator has 11 extra entries |
| `MAX_CONTROL_TARGET` | `core/constants.py:12` | `pipeline/orchestrator.py:44` | Identical value (10000) |
| `FREQUENCY_ORDERED_RULES` | `core/constants.py:30` | `pipeline/orchestrator.py:73` | Identical rules |
| `derive_frequency_from_when()` | `core/constants.py:53` | `pipeline/orchestrator.py:96` | Identical implementation (private in orchestrator) |
| `type_to_code()` | `core/constants.py:73` | `pipeline/orchestrator.py:1030` | Same logic, different approach |
| `build_control_id()` | `core/constants.py:86` | `pipeline/orchestrator.py:1040` | Different signatures |
| `add()` reducer | `graphs/state.py:12` | `graphs/forge_modular_graph.py:146` (`_add()`) | Identical logic, different names |

### 7.3 Duplicate Infrastructure Patterns

| Pattern | Location 1 | Location 2 | Lines Duplicated |
|---------|-----------|-----------|-----------------|
| `_emitter` + `set_emitter()` + `_emit()` | `graphs/forge_modular_graph.py:106–122` | `graphs/control_builder_helpers.py:39–48` (feature branch) | ~30 lines |
| `_event_loop` + `_get_loop()` + `_run_async()` | `graphs/forge_modular_graph.py:269–279` | `graphs/control_builder_helpers.py:56–64` (feature branch) | ~15 lines |
| `_agent_cache` + `_get_agent()` | `graphs/forge_modular_graph.py:289` | `graphs/control_builder_helpers.py:67` (feature branch) | ~10 lines |

**Note:** `control_builder_helpers.py` and `control_builder_graph.py` exist only on the feature branch, not yet on main. The duplication exists in the feature branch where both files share the same emitter/async/agent patterns.

### 7.4 Potentially Unused Pydantic Models

All models in `core/models.py` and `core/state.py` are actively used by the pipeline or tests. No orphaned models detected on main.

### 7.5 Unused Imports

No significant unused imports detected on main after the ICA tool-calling merge. All imports are consumed.

---

## 8. Code Quality Observations

### 8.1 Error Handling

#### Well-handled (12 instances with proper logging):

| File | Line | Logging | Pattern |
|------|------|---------|---------|
| `agents/spec.py` | 86 | `logger.exception()` | Re-raises |
| `agents/narrative.py` | 69 | `logger.exception()` | Re-raises |
| `agents/enricher.py` | 67 | `logger.exception()` | Re-raises |
| `analysis/ingest.py` | 135 | `logger.warning(exc_info=True)` | Skips row |
| `tools/domain_tools.py` | 282 | `logger.error()` | Returns error dict |
| `tools/nodes.py` | 43 | `logger.error()` | Returns error dict |
| `pipeline/orchestrator.py` | 929 | `logger.exception()` | Structured logging |
| `ui/components/upload.py` | 62 | `logger.exception()` | Logs + UI error |
| `ui/components/remediation_runner.py` | 428 | `logger.exception()` | Logs + UI error |
| `ui/playground.py` | 282 | `logger.exception()` | Logs + UI error |
| `ui/components/analysis_runner.py` | 71 | `logger.exception()` | Logs |
| `memory/store.py` | 213 | `logger.debug()` | Handles missing collection |

#### Problematic — UI-only error handling, no logging (9 instances):

| File | Lines | Issue |
|------|-------|-------|
| `ui/controlforge_tab.py` | 92, 226, 242, 267, 294, 453, 511 | **7 `except Exception` with `st.error()` but no logger** |
| `ui/modular_tab.py` | 153 | **1 `except Exception` with `st.error()` but no logger** |
| `ui/components/analysis_runner.py` | 30 | **1 `except Exception` — silent swallow** |

#### Missing logger definitions:

| File | Issue |
|------|-------|
| `ui/controlforge_tab.py` | No `logger = logging.getLogger(__name__)` — 7 except blocks use only `st.error()` |
| `ui/modular_tab.py` | No `logger = logging.getLogger(__name__)` — 1 except block uses only `st.error()` |

### 8.2 Magic Strings

#### Model names:
- `core/transport.py:179`: `"gpt-4o"` hardcoded as OPENAI_MODEL_ID default

#### Quality rating strings (repeated as bare strings across 6+ files):
- `"Strong"`, `"Effective"`, `"Satisfactory"`, `"Needs Improvement"`, `"Weak"`
- Found in: `graphs/remediation_graph.py`, `graphs/forge_modular_helpers.py`, `pipeline/orchestrator.py`, `ui/components/remediation_runner.py`, `ui/playground.py`, `agents/adversarial.py`

#### Affinity level strings (repeated as bare strings across 4+ files):
- `"HIGH"`, `"MEDIUM"`, `"LOW"`, `"NONE"`
- Found in: `analysis/scanners.py`, `core/domain_config.py`, `ui/controlforge_tab.py`

#### Severity level strings:
- `"medium"`, `"low"` used as bare strings in `remediation/planner.py`, `ui/components/remediation_runner.py`

### 8.3 Print Statements

| File | Line | Content |
|------|------|---------|
| `core/events.py` | 119 | `print(f"[controlnexus] {event.message}")` in `cli_listener()` — dead function regardless |

### 8.4 DRY Violations

| Issue | Files Affected | Lines Duplicated |
|-------|---------------|-----------------|
| Constants duplication (TYPE_CODE_MAP, FREQUENCY rules, etc.) | `core/constants.py`, `pipeline/orchestrator.py` | ~70 lines |
| Quality rating strings not centralized | 6+ files | Scattered |
| Affinity level strings not centralized | 4+ files | Scattered |
| `add()` / `_add()` reducer duplication | `graphs/state.py`, `graphs/forge_modular_graph.py` | ~5 lines |
| Emitter/async/agent pattern duplication (feature branch) | `forge_modular_graph.py`, `control_builder_helpers.py` | ~55 lines |

### 8.5 Naming Issues

| Current | Suggested | Location |
|---------|-----------|----------|
| `_get_loop()` | `_get_or_create_event_loop()` | `graphs/forge_modular_graph.py` |
| `_emit()` | `_emit_event()` | `graphs/forge_modular_graph.py` |
| `_run_async()` | `_run_async_in_loop()` | `graphs/forge_modular_graph.py` |

### 8.6 Module-Level Mutable State

| File | Variables | Risk |
|------|-----------|------|
| `graphs/forge_modular_graph.py` | `_emitter`, `_llm_client_cache`, `_event_loop` | Shared across graph invocations; has `reset_caches()` |
| `tools/implementations.py` | `_placement_config`, `_section_profiles`, `_memory`, `_bank_id` | Set by `configure_tools()` — hidden coupling |

### 8.7 Mutable Default Arguments

None detected. ✅

### 8.8 `__import__()` Hacks

None detected. ✅

---

## 9. Architecture Observations

### 9.1 Clean Separations

✅ **Core layer** is pure data — no LLM calls, no side effects.
✅ **Agents** follow consistent ABC pattern with deterministic fallbacks.
✅ **Validation** is stateless and deterministic (6 rules, no LLM).
✅ **Analysis scanners** are pure Python — no LLM calls.
✅ **No circular dependencies** in the import graph.
✅ **Config** is cleanly separated (YAML + env vars + Pydantic).
✅ **Memory/embedding** cleanly abstracted behind Embedder ABC.
✅ **Tool system** uses closure factory pattern for DomainConfig injection.

### 9.2 Layer Violations

| Issue | Severity |
|-------|----------|
| `ui/controlforge_tab.py` directly instantiates `Orchestrator` and calls it — bypasses the graph layer. This is intentional (legacy tab) but couples UI tightly to pipeline internals. | Medium |
| `tools/implementations.py` uses module-level mutable state set by `configure_tools()` — any module that calls a tool function must have previously called `configure_tools()`. | Medium |

### 9.3 Module Placement Issues

| Issue | Suggestion |
|-------|-----------|
| `build_control_id()` and `type_to_code()` are in `core/constants.py` — they're utility functions, not constants. | Consider `core/utils.py` or leave with clear documentation. |
| `add()` reducer in `graphs/state.py` is duplicated as `_add()` in `forge_modular_graph.py`. | Share from `graphs/state.py`. |

### 9.4 Large File Analysis

#### `pipeline/orchestrator.py` (1,055 lines)
Handles: hierarchy loading, scope selection, target sizing, deterministic defaults, 3-phase LLM enrichment (Spec → Narrative → Enrich), validator retry, export. Contains **duplicated constants** from `core/constants.py`. This is the legacy monolith that `forge_modular_graph.py` is replacing.

#### `graphs/forge_modular_graph.py` (770 lines)
The modern replacement for the orchestrator. 8-node graph with tool calling, event emission, provider-aware prompting. Well-structured but contains emitter/async infrastructure that should be shared.

#### `ui/controlforge_tab.py` (587 lines)
Legacy UI tab. Tightly coupled to `pipeline/orchestrator.py`. Contains 7 bare `except Exception` blocks without logging.

#### `ui/components/remediation_runner.py` (521 lines)
Remediation UI panel. Large but cohesive — renders gap analysis results and remediation controls.

### 9.5 Three Pipeline Architectures

ControlNexus currently has **three distinct pipeline architectures**:

1. **Pipeline Orchestrator** (`pipeline/orchestrator.py`) — Legacy monolith. Direct async execution. Used by legacy ControlForge tab.
2. **ControlForge Modular Graph** (`graphs/forge_modular_graph.py`) — LangGraph StateGraph. 8 nodes with tool calling. Used by Modular tab.
3. **Analysis + Remediation Graphs** (`graphs/analysis_graph.py` + `graphs/remediation_graph.py`) — LangGraph StateGraphs. Used by Analysis tab.

Pipeline #1 and #2 do similar work (control generation) but with different approaches. The orchestrator is the older version; the modular graph is the replacement. Both should coexist until the orchestrator is deprecated.

---

## 10. Testing Coverage Map

### Test Count by Module

| Module | Test File | Tests | Coverage Notes |
|--------|-----------|-------|---------------|
| `agents/base.py` | `test_agents.py` | 26 | ✅ Registry, context, parse_json, call_llm, call_llm_with_xml_tools, spec/narrative/enricher |
| `core/config.py` | `test_config.py` | 19 | ✅ All loaders tested (taxonomy, sections, standards, placements) |
| `core/constants.py` | `test_constants.py` | 14 | ✅ derive_frequency, type_to_code, build_control_id |
| `core/domain_config.py` | `test_domain_config.py` | 28 | ✅ DomainConfig validation, computed properties, parity with legacy constants |
| `core/events.py` | — | 0 | ❌ **No tests.** EventEmitter, PipelineEvent untested. |
| `core/models.py` | `test_models.py` | 23 | ✅ All 16 models tested. |
| `core/state.py` | `test_models.py` | — | ✅ State models tested within test_models.py. |
| `core/transport.py` | `test_transport.py` | 16 | ✅ Client, retry, URL caching, provider detection. |
| `exceptions.py` | — | 0 | ❌ No tests. (Trivial — low priority.) |
| `analysis/ingest.py` | `test_ingest.py` | 11 | ✅ Excel parsing, type coercion, multi-sheet. |
| `analysis/pipeline.py` | `test_pipeline.py` | 5 | ⚠️ Basic — empty controls, score range. No isolated scanner testing. |
| `analysis/scanners.py` | `test_scanners.py` | 17 | ✅ All 4 scanners tested. |
| `analysis/register_analyzer.py` | `test_register_analyzer.py` | — | Exists on feature branch. |
| `export/excel.py` | `test_export.py` | 5 | ✅ Round-trip test. |
| `graphs/state.py` | `test_graphs.py` | — | ✅ State definitions tested. |
| `graphs/analysis_graph.py` | `test_graphs.py` | 14 | ✅ Node functions and routing. |
| `graphs/remediation_graph.py` | `test_graphs.py` | — | ✅ Planner, router, should_retry. |
| `graphs/forge_modular_graph.py` | `test_forge_modular_graph.py` | 83 | ✅ Comprehensive — deterministic + LLM mocks. |
| `graphs/forge_modular_helpers.py` | `test_forge_modular_graph.py` | — | ✅ Covered in forge graph tests. |
| `hierarchy/parser.py` | — | 0 | ❌ **No direct tests.** Tested indirectly via e2e. |
| `hierarchy/scope.py` | — | 0 | ❌ **No direct tests.** |
| `memory/store.py` | `test_memory.py` | 14 | ✅ Index, query, dedup, compare_runs, clear. |
| `memory/embedder.py` | `test_memory.py` | — | ✅ MockEmbedder tested. |
| `pipeline/orchestrator.py` | — | 0 | ❌ **No direct tests.** Only tested indirectly via UI. |
| `remediation/paths.py` | `test_remediation.py` | 15 | ✅ All path functions + routing. |
| `remediation/planner.py` | `test_remediation.py` | — | ✅ plan_assignments tested. |
| `tools/implementations.py` | `test_tools.py` | 29 | ✅ All 5 tools + dispatcher. |
| `tools/domain_tools.py` | `test_domain_tools.py` | 23 | ✅ All domain tools + executor. |
| `tools/nodes.py` | `test_tools.py` | — | ✅ execute_tool_call, tool_node. |
| `tools/schemas.py` | `test_tools.py` | — | ✅ Schema validation. |
| `tools/xml_tool_parser.py` | `test_xml_tool_parser.py` | 14 | ✅ Parse, format, strip. |
| `validation/validator.py` | `test_validator.py` | 36 | ✅ All 6 rules + retry appendix. |
| `ui/*.py` | — | 0 | ❌ **No UI tests.** (Streamlit testing is complex — acceptable gap.) |
| **E2E** | `test_e2e.py` | 13 | ✅ Full pipeline: ingest → analysis → remediation → export. |

**Total: 405 tests across 21 test files.**

### Priority Testing Gaps

1. **`pipeline/orchestrator.py`** (1,055 lines, 0 tests) — Sizing logic, deterministic defaults, ID generation all untested directly. Highest-risk untested module.
2. **`core/events.py`** (119 lines, 0 tests) — EventEmitter fan-out, error isolation in listeners.
3. **`hierarchy/parser.py`** (272 lines, 0 tests) — Only tested indirectly via e2e.
4. **`hierarchy/scope.py`** (61 lines, 0 tests) — Only tested indirectly.
5. **`analysis/pipeline.py`** (136 lines, 5 tests) — Basic tests only; individual scanner contribution not isolated.

---

## 11. Cross-Module Analysis

### 11.1 Shared Patterns That Should Be Extracted

| Pattern | Current Locations | Extraction Target |
|---------|------------------|------------------|
| Event emitter + `set_emitter()` / `_emit()` | `forge_modular_graph.py`, `control_builder_helpers.py` (feature) | `graphs/graph_infra.py` |
| Async event loop + `_get_loop()` / `_run_async()` | Same as above | `graphs/graph_infra.py` |
| Agent cache + `_get_agent()` | Same as above | `graphs/graph_infra.py` |
| `add()` / `_add()` list reducer | `graphs/state.py`, `forge_modular_graph.py` | Single `add()` in `graphs/state.py` |
| TYPE_CODE_MAP (full 24 entries) | `core/constants.py` (13), `pipeline/orchestrator.py` (24) | Expand `core/constants.py` |
| FREQUENCY_ORDERED_RULES | `core/constants.py`, `pipeline/orchestrator.py` | Single source in `core/constants.py` |
| frequency/ID builder functions | `core/constants.py`, `pipeline/orchestrator.py` | Single source in `core/constants.py` |
| Quality rating strings | 6+ files | `core/constants.py` → `QUALITY_RATINGS` |
| Affinity level strings | 4+ files | `core/constants.py` → `AFFINITY_LEVELS` |

### 11.2 Inconsistencies Between Modules

| Aspect | Forge Modular | Orchestrator (Legacy) | Analysis/Remediation |
|--------|-------------|---------------------|---------------------|
| Config model | `DomainConfig` (single YAML) | `RunConfig` (multi-config loaders) | `SectionProfile` via config loaders |
| Event emission | `EventEmitter` + `PipelineEvent` | None (prints/logging only) | None |
| Graph framework | LangGraph StateGraph | Direct asyncio | LangGraph StateGraph |
| Agent instantiation | Via `_get_agent()` cache | Direct instantiation | No agents (pure scanners) |
| Tool calling | XML or OpenAI function calling | None | None |
| Deterministic fallback | All agents | All agents | Scanners are fully deterministic |
| Transport | `build_client_from_env()` | `build_client_from_env()` | Not applicable |

### 11.3 ControlForge Modular vs. Legacy Orchestrator

The modular graph (`forge_modular_graph.py`) is the evolution of the legacy orchestrator. Key differences:

- **Modular:** Config-driven via `DomainConfig`, tool-calling, event emission, graph-native retry via `should_retry()` conditional edge.
- **Legacy:** Multi-config loading, direct async execution, no events, manual retry loop.
- **Overlap:** Both call `SpecAgent`, `NarrativeAgent`, `EnricherAgent`. Both use `validate()` + `build_retry_appendix()`.
- **Duplication:** Constants, frequency rules, type codes are duplicated because the orchestrator doesn't import from the shared constants module.

---

## 12. Cross-Cutting Findings

### 12.1 Skeleton Pattern Adoption

The `langgraph-multiagent-skeleton/` defines canonical patterns. Assessment of adoption in ControlNexus:

| Pattern | Skeleton | ControlNexus Status |
|---------|----------|-------------------|
| BaseAgent ABC + AgentContext | ✅ | ✅ Adopted. `agents/base.py` extends skeleton pattern with `call_llm_with_xml_tools()`. |
| @register_agent + AGENT_REGISTRY | ✅ | ✅ Adopted. Consumed by playground UI. |
| Deterministic fallbacks | ✅ | ✅ Adopted. All agents have fallback paths. |
| EventType enum + EventEmitter | ✅ | ✅ Adopted. Extended with 17 event types. |
| EventListener Protocol | ✅ | ✅ Adopted. |
| PipelineEvent frozen dataclass | ✅ | ✅ Adopted. |
| AsyncTransportClient | ✅ | ✅ Adopted. Extended with Anthropic provider. |
| build_client_from_env() | ✅ | ✅ Adopted. ICA → OpenAI → Anthropic. |
| Frozen Pydantic models | ✅ | ✅ Adopted extensively. |
| LangGraph StateGraph + TypedDict | ✅ | ✅ Adopted. 3 graphs. |
| Annotated[list, add] reducer | ✅ | ✅ Adopted (with duplicate `_add()`). |
| Module-level caching | ✅ | ✅ Adopted (with duplication). |
| Tool executor closure | ✅ | ✅ Adopted via `build_domain_tool_executor()`. |
| Validation module | ✅ | ✅ Extended. 6 rules vs. skeleton's 3. |
| Exception hierarchy | ✅ | ✅ Adopted. Different exception names but same pattern. |

### 12.2 Patterns Not Yet Shared

- **Graph infrastructure** (emitter, cache, async loop) is duplicated rather than shared.
- **Event system** is used by Forge Modular but not by Analysis or Remediation graphs.
- **Constants** are not fully centralized (orchestrator maintains its own copy).

### 12.3 `core/` as Shared Foundation

`controlnexus.core` already serves as a shared package with: config loaders, constants, domain_config, events, models, state, transport. All modules import from it. **This is the right pattern.** The gap is that constants are incomplete and some infrastructure (events, transport) isn't used by all pipelines.

---

## Summary of Phase 2 Targets (Dead Code Removal)

1. Remove `cli_listener()` from `core/events.py`
2. Expand `core/constants.py` TYPE_CODE_MAP to include all 24 entries from orchestrator.py
3. Remove duplicate `TYPE_CODE_MAP` from `pipeline/orchestrator.py` → import from constants
4. Remove duplicate `MAX_CONTROL_TARGET` from `pipeline/orchestrator.py` → import from constants
5. Remove duplicate `FREQUENCY_ORDERED_RULES` from `pipeline/orchestrator.py` → import from constants
6. Remove duplicate `_derive_frequency_from_when()` from `pipeline/orchestrator.py` → import from constants
7. Remove/reconcile duplicate `type_to_code()` and `build_control_id()` from orchestrator → import from constants (may need signature alignment)
8. Replace duplicate `_add()` in `forge_modular_graph.py` → import `add` from `graphs/state.py`
9. Flag `langchain-core` in pyproject.toml as transitive-only dependency

## Summary of Phase 3 Targets (Code Quality)

1. Add docstrings to all public functions/classes (priority: 23 files over 150 lines)
2. Complete type annotations on all signatures
3. Extract quality rating, affinity level, and default model constants to `core/constants.py`
4. Extract graph infrastructure to shared `graphs/graph_infra.py`
5. Add `logger = logging.getLogger(__name__)` to `ui/controlforge_tab.py` and `ui/modular_tab.py`
6. Fix 9 bare `except Exception` blocks in UI modules (add logging alongside `st.error()`)
7. Add section separators to all files over 150 lines
8. Rename `_get_loop()` → `_get_or_create_event_loop()`

## Summary of Phase 4 Targets (Architecture)

1. Populate empty `core/__init__.py` and `graphs/__init__.py` with re-exports
2. Verify no circular dependencies after Phase 3 changes
3. Document the three pipeline architectures and their intended lifecycle
4. Evaluate whether `DomainConfig` and `RunConfig` should converge

---

*End of Phase 1 audit. Awaiting approval to proceed to Phase 2.*
