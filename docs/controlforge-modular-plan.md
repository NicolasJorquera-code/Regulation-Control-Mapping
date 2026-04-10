# ControlForge Modular — Build Plan

> **What is this?** A step-by-step plan for building a new, simplified control generation system that is **modular from day one** — any organization can plug in their own business units, control types, sections, and register fields. It borrows ideas from the [future architecture vision](future-architecture-and-tool-vision.md) but starts fresh with a clean, minimal implementation.
>
> **Who is this for?** You, a junior SWE, building this incrementally. Each step explains *why* before *how*.

---

## Table of Contents

- [ControlForge Modular — Build Plan](#controlforge-modular--build-plan)
  - [Table of Contents](#table-of-contents)
  - [1. The Problem We're Solving](#1-the-problem-were-solving)
  - [2. Key Concepts (First Principles)](#2-key-concepts-first-principles)
    - [2.1 What is a "Domain Config"?](#21-what-is-a-domain-config)
    - [2.2 What is a StateGraph?](#22-what-is-a-stategraph)
    - [2.3 What is Tool Calling?](#23-what-is-tool-calling)
    - [2.4 What is a "Self-Describing" Config?](#24-what-is-a-self-describing-config)
  - [3. Architecture Overview](#3-architecture-overview)
  - [4. Step 1 — The DomainConfig Model](#4-step-1--the-domainconfig-model)
    - [4.1 Why a Pydantic Model?](#41-why-a-pydantic-model)
    - [4.2 The DomainConfig Schema](#42-the-domainconfig-schema)
    - [4.3 Loading a DomainConfig from YAML](#43-loading-a-domainconfig-from-yaml)
    - [4.4 Writing a Minimal domain\_config.yaml](#44-writing-a-minimal-domain_configyaml)
    - [4.5 Validation Rules](#45-validation-rules)
    - [4.6 Tests to Write](#46-tests-to-write)
  - [5. Step 2 — The Minimal StateGraph](#5-step-2--the-minimal-stategraph)
    - [5.1 Why a Graph Instead of a Class?](#51-why-a-graph-instead-of-a-class)
    - [5.2 The State TypedDict](#52-the-state-typeddict)
    - [5.3 Graph Topology (5 Nodes)](#53-graph-topology-5-nodes)
    - [5.4 Node Implementations](#54-node-implementations)
    - [5.5 The Assignment Loop](#55-the-assignment-loop)
    - [5.6 Tests to Write](#56-tests-to-write)
  - [6. Step 3 — The Streamlit Tab](#6-step-3--the-streamlit-tab)
    - [6.1 Config Selection UI](#61-config-selection-ui)
    - [6.2 Running the Graph](#62-running-the-graph)
    - [6.3 Displaying Results](#63-displaying-results)
  - [7. File Layout](#7-file-layout)
  - [8. Future Work](#8-future-work)

---

## 1. The Problem We're Solving

The current ControlForge system generates controls for a **fixed** domain model:

- **25 control types** (Reconciliation, Authorization, etc.) — names and codes hardcoded in Python
- **17 business units** (Retail Banking, Commercial Banking, etc.) — defined in `taxonomy.yaml`
- **13 APQC sections** — hardcoded as `range(1, 14)` in Python source code
- **3 placements** (Preventive, Detective, Contingency Planning) — in YAML and agent prompts
- **3 methods** (Automated, Manual, Automated with Manual Component) — same
- **Specific frequency expectations** (Reconciliation must be monthly, Authorization must be quarterly) — hardcoded Python sets

This works perfectly for one banking org that uses this exact taxonomy. But what if:

- A **community bank** has 5 business units, not 17?
- An org uses **15 control types** instead of 25, with different names?
- An org's control register has a **"Key Report"** column that our system doesn't know about?
- An org follows **8 process areas** (not 13 APQC sections)?

Today, changing any of this requires editing Python source code and YAML files by hand. A compliance officer can't do that. Even a developer has to hunt through multiple files to find every reference.

**The goal of ControlForge Modular is:** a user uploads or selects a **configuration file** that describes *their* domain model, and the pipeline adapts automatically. No code changes. The config is the single source of truth.

---

## 2. Key Concepts (First Principles)

Before we build anything, here are the core ideas you need to understand.

### 2.1 What is a "Domain Config"?

A **domain config** is a data structure that describes everything the pipeline needs to know about an organization's control environment. Think of it as a blueprint:

```
"Here are my control types. Here are my business units. Here are my process areas.
 Here are the rules for how they relate to each other. Now generate controls."
```

In code, this is a Python class (a Pydantic `BaseModel`) with fields for:
- Control types (list of names + definitions)
- Business units (list of names + metadata)
- Process areas / sections (list of names + domain registries)
- Placements and methods (the allowed values)
- Narrative constraints (word count, required fields)
- Frequency expectations (which types need which minimum frequency)

The key insight: **everything the pipeline needs comes from this one object.** No hardcoded constants, no scattered YAML files. One config → one pipeline behavior.

### 2.2 What is a StateGraph?

A **StateGraph** (from the [LangGraph](https://langchain-ai.github.io/langgraph/) library) is a way to model a workflow as a directed graph:

- **Nodes** are Python functions that do work (e.g., "generate a spec", "validate the narrative").
- **Edges** connect nodes in order (e.g., "after spec, run narrative").
- **Conditional edges** let you branch (e.g., "if validation failed and retries < 3, go back to narrative; otherwise proceed").
- **State** is a shared dictionary that every node can read and write. It flows through the graph.

Why use this instead of a regular Python class?

1. **Visibility.** Each node is a named step you can inspect, log, and test independently.
2. **Looping.** Conditional edges make retry loops declarative — "go back to narrative" is an edge, not a `while` loop buried inside a 950-line class.
3. **Parallelism later.** LangGraph has a `Send()` API that dispatches work to multiple copies of a subgraph in parallel. A class would need `asyncio.gather()` wired manually.
4. **Composition.** You can embed one graph inside another. The control generation graph could be embedded inside a larger analysis graph.

Here's the mental model:

```
START → [load config] → [pick assignment] → [generate spec] → [generate narrative]
                              ↑                                        |
                              |                                  [validate]
                              |                                    |     |
                              +---------- [merge record] ←--- pass    fail (retry)
                                               |                        ↓
                                           more? ──yes──→ [pick assignment]
                                               |
                                              no
                                               ↓
                                          [finalize] → END
```

Each box is a **node**. Each arrow is an **edge**. The state dictionary carries all the data between nodes.

### 2.3 What is Tool Calling?

**Tool calling** is a protocol where the LLM can request your code to execute a function during a conversation.

Normal LLM call:
```
You send:  "Generate a control for Reconciliation"
LLM says:  "WHO: Accountant, WHAT: Reconciles accounts..."
```

Tool-calling LLM call:
```
You send:  "Generate a control for this leaf node" + [available tools: taxonomy_validator, frequency_lookup]
LLM says:  "I want to call taxonomy_validator(level_1='Detective', level_2='Reconciliation')"
You run:   taxonomy_validator("Detective", "Reconciliation") → {valid: true}
You send:  {tool result: valid: true}
LLM says:  "Great, now I want to call frequency_lookup(control_type='Reconciliation')"
You run:   frequency_lookup("Reconciliation") → {expected: "Monthly"}
You send:  {tool result: expected: "Monthly"}
LLM says:  "WHO: Senior Accountant, WHAT: Reconciles..., WHEN: Monthly..."
```

The LLM **decides** which tools to call and when. Your code just executes the tool and returns the result. This is powerful because:

1. **The LLM only fetches what it needs.** Instead of a 4 KB fat prompt with all possible data, the LLM calls `frequency_lookup` only when it needs frequency information.
2. **The LLM can self-verify.** It can call `score_completeness` on its own output before returning — catching its own mistakes.
3. **The tools are config-driven.** A `taxonomy_validator` tool reads from the DomainConfig. Different config → different validation rules → same tool code.

We won't implement tool calling in Step 1, but we'll **design the architecture to support it later** without rewrites.

### 2.4 What is a "Self-Describing" Config?

A self-describing config includes not just *data* but also *rules about that data*.

**Regular config (data only):**
```yaml
control_types:
  - name: Reconciliation
    definition: "Comparison of records..."
```

**Self-describing config (data + rules):**
```yaml
control_types:
  - name: Reconciliation
    definition: "Comparison of records..."
    code: REC                          # ← used for control IDs
    min_frequency_tier: Monthly        # ← the pipeline enforces this
    placement_categories: [Detective]  # ← only valid under Detective
    evidence_criteria:                 # ← what constitutes good evidence for this type
      - "Names specific reconciliation report"
      - "Identifies preparer and reviewer"
```

The difference: with the self-describing config, the pipeline doesn't need a hardcoded Python set that says "Reconciliation must be monthly." That rule **lives in the config**. Change the config → change the rule. No code edits.

This is the pattern we'll use in ControlForge Modular: the YAML file is the single source of truth for data, rules, and constraints.

---

## 3. Architecture Overview

Here's the high-level picture of what we're building:

```
┌─────────────────────────────────────────────────┐
│  domain_config.yaml  (THE SINGLE SOURCE OF TRUTH)│
│  - control_types (names, codes, rules)           │
│  - business_units (names, sections, exposure)    │
│  - process_areas (registries, affinities)        │
│  - placements, methods                           │
│  - narrative_constraints (word count, fields)    │
│  - frequency_tiers                               │
└──────────────────────┬──────────────────────────┘
                       │ loaded at startup
                       ▼
┌──────────────────────────────────────────────────┐
│  DomainConfig  (Pydantic model in Python)        │
│  Validates all cross-references on load          │
│  Provides helper methods:                        │
│    .type_code_map()                              │
│    .monthly_or_better_types()                    │
│    .section_ids()                                │
│    .get_section_profile(id)                      │
└──────────────────────┬───────────────────────────┘
                       │ passed into the graph
                       ▼
┌──────────────────────────────────────────────────┐
│  LangGraph StateGraph                            │
│  Nodes read from DomainConfig, not constants.py  │
│  init → select → spec → narr → validate →        │
│  enrich → merge → (loop or finalize)             │
└──────────────────────┬───────────────────────────┘
                       │ output
                       ▼
┌──────────────────────────────────────────────────┐
│  Generated Controls (Excel / JSON)               │
│  Columns are config-driven (custom fields OK)    │
└──────────────────────────────────────────────────┘
```

**Three layers:**
1. **Config layer** — YAML file(s) that non-technical users can edit (or a UI generates for them).
2. **Model layer** — Python `DomainConfig` that validates the config and provides computed properties.
3. **Graph layer** — LangGraph `StateGraph` that uses `DomainConfig` to generate controls.

We build these bottom-up: model first, then graph, then UI.

### 3.1 Original ControlForge vs ControlForge Modular — Architecture Comparison

The diagrams below show the full information flow for both systems side-by-side. The original system is a monolithic orchestrator with fat prompts and no tool calling. The new system is a LangGraph StateGraph with config-driven tools, event emission, and a multi-layer fallback chain.

---

#### Original ControlForge (Orchestrator-Based)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CONFIG LAYER                                │
│                                                                     │
│  taxonomy.yaml ─┐                                                   │
│  standards.yaml ─┤  13× section_N.yaml                              │
│  placement_methods.yaml  ┘                                          │
│  + Hardcoded Python constants (TYPE_CODE_MAP, MONTHLY_OR_BETTER...) │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ loaded piecemeal
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Orchestrator Class (~950 lines)                   │
│                    pipeline/orchestrator.py                          │
│                                                                     │
│  Phase 1: Deterministic Defaults (sequential)                       │
│  ┌────────────────────────────────────────────┐                     │
│  │ for each assignment:                       │                     │
│  │   load YAML → extract registry → build     │                     │
│  │   baseline spec + narrative + enriched     │                     │
│  └────────────────────┬───────────────────────┘                     │
│                       │                                             │
│  Phase 2: LLM Enrichment (parallel via asyncio.gather + Semaphore)  │
│  ┌────────────────────┴───────────────────────┐                     │
│  │ for each assignment (bounded concurrency): │                     │
│  │                                            │                     │
│  │  ┌──────────┐   FAT      ┌──────────────┐ │                     │
│  │  │SpecAgent │◄──PROMPT──►│ LLM Provider │ │  All context        │
│  │  └────┬─────┘  (2-5 KB)  └──────────────┘ │  pre-computed       │
│  │       │                                    │  and dumped         │
│  │       ▼                                    │  into one           │
│  │  ┌──────────────┐  FAT    ┌──────────────┐│  giant JSON         │
│  │  │NarrativeAgent│◄─PROMPT►│ LLM Provider ││  payload.           │
│  │  └────┬─────────┘         └──────────────┘│                     │
│  │       │                                    │  No tool calling.   │
│  │       ▼  (retry for loop, up to 3×)        │  No events.        │
│  │  ┌──────────┐                              │  No on-demand       │
│  │  │Validator │  6 deterministic rules       │  context.           │
│  │  └────┬─────┘                              │                     │
│  │       │                                    │                     │
│  │       ▼                                    │                     │
│  │  ┌───────────┐    FAT     ┌──────────────┐│                     │
│  │  │EnricherAg.│◄──PROMPT──►│ LLM Provider ││                     │
│  │  └───────────┘            └──────────────┘│                     │
│  └────────────────────────────────────────────┘                     │
│                                                                     │
│  Phase 3: Finalization (sequential)                                 │
│  ┌────────────────────────────────────────────┐                     │
│  │ merge results → assign CTRL IDs → export   │                     │
│  └────────────────────────────────────────────┘                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Streamlit UI                                    │
│                     st.spinner("Generating...")                     │
│                     ← blocking, no progress feedback →              │
│                     Results dumped to table when done                │
└─────────────────────────────────────────────────────────────────────┘
```

**Key limitations:**
- Config scattered across 16+ files + Python constants
- All context dumped into every agent prompt (2–5 KB fat JSON)
- No tool calling — agents can't validate or look up data mid-generation
- No events — UI shows a blocking spinner with no progress
- Retry logic buried inside nested `for` loop within 950-line class
- `EventEmitter`, `AdversarialReviewer`, `DifferentiationAgent`, 5 tools, ChromaDB memory — all built but **completely unwired**

---

#### ControlForge Modular (StateGraph + Tool Calling + Events)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       CONFIG LAYER                                  │
│                                                                     │
│              domain_config.yaml                                     │
│              (SINGLE FILE — all types, BUs, sections,               │
│               placements, methods, frequencies, narrative           │
│               constraints, evidence criteria, affinities)           │
│                                                                     │
│              Validated on load via Pydantic cross-ref checks        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DomainConfig (Pydantic Model)                    │
│                    core/domain_config.py                            │
│                                                                     │
│  .type_code_map()   .min_frequency_types()   .section_ids()        │
│  .get_process_area()  .placement_names()  .narrative_field_names()  │
└───────────┬─────────────────────────────────┬───────────────────────┘
            │ drives graph nodes              │ drives tool behavior
            ▼                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│              LangGraph StateGraph (8 nodes)                         │
│              graphs/forge_modular_graph.py                          │
│                                                                     │
│  ┌──────┐   ┌────────┐   ┌──────┐   ┌───────────┐   ┌──────────┐  │
│  │ init │──►│ select │──►│ spec │──►│ narrative │──►│ validate │  │
│  └──────┘   └────────┘   └──┬───┘   └─────┬─────┘   └────┬─────┘  │
│                             │              │              │         │
│       Events:               │              │        ┌─────┴──────┐ │
│       PIPELINE_STARTED      │              │        │  passed?   │ │
│       CONTROL_STARTED       │              │        └──┬──────┬──┘ │
│       AGENT_STARTED         │              │     yes   │      │ no │
│       AGENT_COMPLETED       │              │           ▼      │    │
│       VALIDATION_PASSED     │              │      ┌────────┐  │    │
│       VALIDATION_FAILED     │              │      │ enrich │  │    │
│       AGENT_RETRY           │              │      └───┬────┘  │    │
│       TOOL_CALLED           │              │          │       │    │
│       TOOL_COMPLETED        │         ◄────┘   ◄──retry (≤3) ┘    │
│       CONTROL_COMPLETED     │              │          │            │
│       PIPELINE_COMPLETED    │              │          ▼            │
│                             │              │     ┌─────────┐      │
│                             │              │     │  merge  │      │
│                             │              │     └────┬────┘      │
│                             │              │     ┌────┴────┐      │
│                             │              │     │ more?   │      │
│                             │              │     └──┬───┬──┘      │
│                             │              │   yes  │   │ no      │
│                             │              │        │   ▼         │
│                             │              │   (loop)  ┌────────┐ │
│                             │              │    back   │finalize│ │
│                             │              │    to     └────┬───┘ │
│                             │              │   select       │     │
│                             │              │                ▼     │
│                             │              │              END     │
│                                                                     │
│  ─────────── TOOL CALLING (per agent node) ──────────────────────  │
│                                                                     │
│  Each agent node:                                                   │
│    1. Builds tool executor from DomainConfig                        │
│    2. Calls LLM with call_llm_with_tools() + tool schemas          │
│    3. LLM may invoke 0+ tools per turn (multi-round loop)          │
│    4. Falls back: tools fail → plain call_llm → deterministic      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ spec_node tools:                                            │   │
│  │   taxonomy_validator  — validate placement/type pair        │   │
│  │   hierarchy_search    — look up domain roles/systems        │   │
│  │   regulatory_lookup   — check regulatory applicability      │   │
│  │                                                             │   │
│  │ narrative_node tools:                                       │   │
│  │   frequency_lookup    — derive + validate timing            │   │
│  │   regulatory_lookup   — check regulatory context            │   │
│  │                                                             │   │
│  │ enrich_node tools:                                          │   │
│  │   taxonomy_validator  — validate final placement            │   │
│  │   frequency_lookup    — verify frequency alignment          │   │
│  │   memory_retrieval    — find similar controls (ChromaDB)    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  All tools read from DomainConfig — different config =              │
│  different tool behavior, automatically.                            │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ events stream in real time
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Streamlit UI (modular_tab.py)                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ st.status("Generating controls...", expanded=True)            │  │
│  │                                                               │  │
│  │ 📋 Control 1/10: Authorization in Lending Operations          │  │
│  │   ⏳ SpecAgent started...                                     │  │
│  │   🔧 taxonomy_validator({Preventive, Authorization})          │  │
│  │   ✓ SpecAgent completed (1.2s, 1 tool call)                  │  │
│  │   ⏳ NarrativeAgent started...                                │  │
│  │   🔧 frequency_lookup({Authorization, quarterly review})      │  │
│  │   ✓ NarrativeAgent completed (0.9s, 1 tool call)             │  │
│  │   ✓ Validation passed                                        │  │
│  │   ⏳ EnricherAgent started...                                 │  │
│  │   ✓ EnricherAgent completed (0.6s) — Effective               │  │
│  │   ✔️ Control 1 completed — Effective                          │  │
│  │                                                               │  │
│  │ 📋 Control 2/10: Reconciliation in Settlement                 │  │
│  │   ...                                                         │  │
│  │                                                               │  │
│  │ ✅ Generated 10 controls for community-bank-demo              │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Results table, CSV export, config preview                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

#### Side-by-Side Comparison

```
                ORIGINAL CONTROLFORGE           CONTROLFORGE MODULAR
                ─────────────────────           ────────────────────

Config          16+ files + Python constants    1 YAML file (DomainConfig)
                Scattered, hard to modify       Validated on load, self-describing

Orchestration   Python class (950 lines)        LangGraph StateGraph (8 nodes)
                for-loops + asyncio.gather      Declarative edges + conditional routing

Agent Prompts   Fat prompts (2-5 KB JSON)       Fat prompts + tool-calling extras
                All context pre-computed         LLM can self-verify via tools

Tool Calling    5 tools built, 0 used           5 tools wired, LLM invokes on-demand
                                                 taxonomy_validator
                                                 hierarchy_search
                                                 regulatory_lookup
                                                 frequency_lookup
                                                 memory_retrieval

Validation      for-loop inside method           Graph conditional edge (validate → narrative)
                Hidden retry logic               Visible, testable, event-emitting

Events          EventEmitter built, unwired      19 event types, every node emits
                No progress feedback             Real-time st.status() feed

Fallback        LLM fail → deterministic         LLM+tools fail → plain LLM → deterministic
Chain           (1 level)                        (3 levels, always produces output)

UI              st.spinner() → dump results      st.status() with live activity feed
                No insight into pipeline         Shows per-control agent/tool/validation detail

Extensibility   Edit Python + YAML everywhere    Edit 1 YAML file → pipeline adapts
                                                 New org = new config, zero code changes
```

---

## 4. Step 1 — The DomainConfig Model

This is where we start. The goal: define a Python class that can load a YAML config file and make all domain data available to the rest of the system, with validation to catch mistakes early.

### 4.1 Why a Pydantic Model?

[Pydantic](https://docs.pydantic.dev/) is a Python library that lets you define data structures with type validation. You define a class with typed fields, and Pydantic checks every value when you create an instance.

```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

p = Person(name="Alice", age=30)    # ✅ works
p = Person(name="Alice", age="abc") # ❌ raises ValidationError
```

We already use Pydantic in the current codebase (`TaxonomyItem`, `SectionProfile`, `RunConfig`, etc.). `DomainConfig` follows the same pattern but consolidates everything into one model.

**Why one model instead of many files?**

Today, the pipeline loads 4+ separate YAML files (`taxonomy.yaml`, `standards.yaml`, `placement_methods.yaml`, `sections/section_N.yaml` × 13). Each file is loaded by a different function. Cross-references between files are validated ad-hoc (e.g., "does this BU reference a known control type?"). If you rename a control type in `taxonomy.yaml` but forget to update `placement_methods.yaml`, you get a runtime error deep inside the pipeline.

With `DomainConfig`, **all cross-references are validated at load time**. If a business unit references a control type that doesn't exist, Pydantic catches it before the pipeline starts.

### 4.2 The DomainConfig Schema

Here's the complete model. Each inner class is a Pydantic `BaseModel` that describes one part of the domain:

```python
from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
import re


class FrequencyTier(BaseModel):
    """One frequency level (e.g., Daily, Weekly, Monthly).

    Keywords are lowercase strings that, if found in a control's 'when' field,
    indicate this frequency. Rank is used for ordering: 1 = most frequent.
    """
    label: str                                  # "Monthly"
    rank: int                                   # 3  (Daily=1, Weekly=2, Monthly=3, ...)
    keywords: list[str]                         # ["monthly", "every month", "month-end"]


class ControlTypeConfig(BaseModel):
    """One control type in the taxonomy.

    This replaces the current TaxonomyItem + the hardcoded TYPE_CODE_MAP +
    the hardcoded MONTHLY_OR_BETTER_TYPES + the hardcoded evidence criteria.
    Everything about a control type lives here.
    """
    name: str                                   # "Reconciliation"
    definition: str                             # "Comparison of features..."
    code: str = ""                              # "REC" — auto-generated if blank
    min_frequency_tier: str | None = None       # "Monthly" — must match a FrequencyTier.label
    placement_categories: list[str] = Field(default_factory=list)  # ["Detective"]
    evidence_criteria: list[str] = Field(default_factory=list)     # ["Names specific report", ...]


class BusinessUnitConfig(BaseModel):
    """One business unit."""
    id: str                                     # "BU-001"
    name: str                                   # "Retail Banking"
    description: str = ""
    primary_sections: list[str] = Field(default_factory=list)      # ["5.0", "3.0"]
    key_control_types: list[str] = Field(default_factory=list)     # ["Authorization", ...]
    regulatory_exposure: list[str] = Field(default_factory=list)   # ["SOX", "OCC"]


class AffinityConfig(BaseModel):
    """Control type affinity buckets for a section."""
    HIGH: list[str] = Field(default_factory=list)
    MEDIUM: list[str] = Field(default_factory=list)
    LOW: list[str] = Field(default_factory=list)
    NONE: list[str] = Field(default_factory=list)


class RegistryConfig(BaseModel):
    """Domain-specific vocabulary for one process area.

    This is intentionally flexible — extra keys are allowed so orgs can add
    custom fields (e.g., 'key_reports', 'testing_procedures').
    """
    model_config = {"extra": "allow"}       # ← allows arbitrary extra fields

    roles: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    data_objects: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    event_triggers: list[str] = Field(default_factory=list)
    regulatory_frameworks: list[str] = Field(default_factory=list)


class ExemplarConfig(BaseModel):
    """A sample control used as a style reference."""
    control_type: str
    placement: str
    method: str
    full_description: str
    word_count: int = 0
    quality_rating: str = "Effective"


class RiskProfileConfig(BaseModel):
    """Risk scoring for a process area."""
    inherent_risk: int = 3
    regulatory_intensity: int = 3
    control_density: int = 3
    multiplier: float = 1.0
    rationale: str = ""


class ProcessAreaConfig(BaseModel):
    """One process area / section.

    Replaces the current SectionProfile + the per-section YAML files.
    """
    id: str                                     # "1.0"
    name: str                                   # "Vision and Strategy"
    domain: str = ""                            # "vision_and_strategy"
    risk_profile: RiskProfileConfig = Field(default_factory=RiskProfileConfig)
    affinity: AffinityConfig = Field(default_factory=AffinityConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    exemplars: list[ExemplarConfig] = Field(default_factory=list)


class NarrativeField(BaseModel):
    """One field in the narrative output schema (e.g., 'who', 'what', 'when')."""
    name: str                                   # "who"
    definition: str = ""                        # "The specific role responsible..."
    required: bool = True


class NarrativeConstraints(BaseModel):
    """Rules for the narrative agent's output."""
    fields: list[NarrativeField] = Field(default_factory=lambda: [
        NarrativeField(name="who", definition="The specific role responsible for performing the control"),
        NarrativeField(name="what", definition="The specific action performed"),
        NarrativeField(name="when", definition="The timing or trigger for the control"),
        NarrativeField(name="where", definition="The system or location where the control is performed"),
        NarrativeField(name="why", definition="The risk or objective the control addresses"),
        NarrativeField(name="full_description", definition="Prose narrative incorporating all fields"),
    ])
    word_count_min: int = 30
    word_count_max: int = 80


class PlacementConfig(BaseModel):
    """One placement category (e.g., Preventive, Detective)."""
    name: str
    description: str = ""


class MethodConfig(BaseModel):
    """One control method (e.g., Automated, Manual)."""
    name: str
    description: str = ""


class DomainConfig(BaseModel):
    """The single source of truth for an organization's control domain.

    Everything the pipeline needs to know about control types, business units,
    process areas, placements, methods, frequencies, and narrative structure
    is defined here. No hardcoded constants elsewhere.
    """
    name: str = "default"                       # config profile name
    description: str = ""

    control_types: list[ControlTypeConfig]
    business_units: list[BusinessUnitConfig] = Field(default_factory=list)
    process_areas: list[ProcessAreaConfig] = Field(default_factory=list)

    placements: list[PlacementConfig] = Field(default_factory=lambda: [
        PlacementConfig(name="Preventive"),
        PlacementConfig(name="Detective"),
        PlacementConfig(name="Contingency Planning"),
    ])
    methods: list[MethodConfig] = Field(default_factory=lambda: [
        MethodConfig(name="Automated"),
        MethodConfig(name="Manual"),
        MethodConfig(name="Automated with Manual Component"),
    ])

    frequency_tiers: list[FrequencyTier] = Field(default_factory=lambda: [
        FrequencyTier(label="Daily", rank=1, keywords=["daily", "every day", "each day", "eod"]),
        FrequencyTier(label="Weekly", rank=2, keywords=["weekly", "every week", "biweekly"]),
        FrequencyTier(label="Monthly", rank=3, keywords=["monthly", "every month", "month-end"]),
        FrequencyTier(label="Quarterly", rank=4, keywords=["quarterly", "every quarter"]),
        FrequencyTier(label="Semi-Annual", rank=5, keywords=["semi-annual", "twice a year"]),
        FrequencyTier(label="Annual", rank=6, keywords=["annual", "annually", "yearly"]),
    ])

    narrative: NarrativeConstraints = Field(default_factory=NarrativeConstraints)

    quality_ratings: list[str] = Field(
        default_factory=lambda: ["Strong", "Effective", "Satisfactory", "Needs Improvement"]
    )

    # ── Cross-reference validation ──────────────────────────────────────

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "DomainConfig":
        """Ensure all cross-references are valid."""
        known_types = {ct.name for ct in self.control_types}
        known_sections = {pa.id for pa in self.process_areas}
        known_placements = {p.name for p in self.placements}
        known_freq_tiers = {ft.label for ft in self.frequency_tiers}
        errors: list[str] = []

        # BU key_control_types must reference known control types
        for bu in self.business_units:
            for ct in bu.key_control_types:
                if ct not in known_types:
                    errors.append(f"BU '{bu.id}' references unknown control type: '{ct}'")
            for sec in bu.primary_sections:
                if known_sections and sec not in known_sections:
                    errors.append(f"BU '{bu.id}' references unknown section: '{sec}'")

        # Control type placement_categories must reference known placements
        for ct in self.control_types:
            for pc in ct.placement_categories:
                if pc not in known_placements:
                    errors.append(f"Control type '{ct.name}' references unknown placement: '{pc}'")
            if ct.min_frequency_tier and ct.min_frequency_tier not in known_freq_tiers:
                errors.append(
                    f"Control type '{ct.name}' references unknown frequency tier: '{ct.min_frequency_tier}'"
                )

        # Section affinity types must reference known control types
        for pa in self.process_areas:
            for level in ["HIGH", "MEDIUM", "LOW", "NONE"]:
                for ct_name in getattr(pa.affinity, level, []):
                    if ct_name not in known_types:
                        errors.append(
                            f"Section '{pa.id}' affinity.{level} references unknown type: '{ct_name}'"
                        )

        if errors:
            raise ValueError(
                f"DomainConfig cross-reference errors:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        return self

    # ── Computed properties (replace hardcoded constants) ────────────────

    def type_code_map(self) -> dict[str, str]:
        """Build the control type → 3-letter code mapping.

        Uses the 'code' field from config, or auto-generates from consonants.
        Replaces the hardcoded TYPE_CODE_MAP in constants.py.
        """
        result: dict[str, str] = {}
        for ct in self.control_types:
            if ct.code:
                result[ct.name] = ct.code
            else:
                consonants = re.sub(r"[aeiouAEIOU\s\-]", "", ct.name)
                result[ct.name] = consonants[:3].upper() or "UNK"
        return result

    def frequency_tier_rank(self, label: str) -> int | None:
        """Get the rank for a frequency tier label, or None if unknown."""
        for ft in self.frequency_tiers:
            if ft.label == label:
                return ft.rank
        return None

    def min_frequency_types(self, at_or_better_than: str) -> set[str]:
        """Get control types that require at least the given frequency.

        Example: min_frequency_types("Monthly") returns all types where
        min_frequency_tier rank ≤ Monthly's rank (i.e., Daily, Weekly, Monthly).

        Replaces MONTHLY_OR_BETTER_TYPES and QUARTERLY_OR_BETTER_TYPES.
        """
        threshold = self.frequency_tier_rank(at_or_better_than)
        if threshold is None:
            return set()
        return {
            ct.name
            for ct in self.control_types
            if ct.min_frequency_tier
            and (self.frequency_tier_rank(ct.min_frequency_tier) or 999) <= threshold
        }

    def section_ids(self) -> list[str]:
        """Return all process area IDs. Replaces range(1, 14)."""
        return [pa.id for pa in self.process_areas]

    def get_process_area(self, section_id: str) -> ProcessAreaConfig | None:
        """Look up a process area by ID."""
        for pa in self.process_areas:
            if pa.id == section_id:
                return pa
        return None

    def placement_names(self) -> list[str]:
        """Return all placement category names."""
        return [p.name for p in self.placements]

    def method_names(self) -> list[str]:
        """Return all method names."""
        return [m.name for m in self.methods]

    def narrative_field_names(self) -> list[str]:
        """Return the ordered list of narrative output field names."""
        return [f.name for f in self.narrative.fields]
```

**What each piece replaces:**

| DomainConfig feature | Replaces | File(s) it eliminates |
|---------------------|----------|-----------------------|
| `control_types[].code` | `TYPE_CODE_MAP` dict | `constants.py` line 14–27 |
| `control_types[].min_frequency_tier` | `MONTHLY_OR_BETTER_TYPES`, `QUARTERLY_OR_BETTER_TYPES` | `scanners.py` line 177–190 |
| `control_types[].placement_categories` | `control_taxonomy.level_2_by_level_1` | `placement_methods.yaml` |
| `control_types[].evidence_criteria` | Hardcoded 3-point scale in SpecAgent prompt | `agents/spec.py` |
| `process_areas[]` | 13 separate `section_N.yaml` files + `range(1, 14)` | `config.py`, `parser.py` |
| `narrative.word_count_min/max` | Hardcoded `30–80` in NarrativeAgent prompt | `agents/narrative.py` |
| `frequency_tiers[]` | `FREQUENCY_ORDERED_RULES` list | `constants.py` line 31–47 |
| `placements[]` / `methods[]` | `placements` / `methods` lists in `placement_methods.yaml` | `placement_methods.yaml` |
| `quality_ratings[]` | `quality_ratings` list in `standards.yaml` | `standards.yaml` |
| Cross-reference validator | Ad-hoc checks scattered across `config.py` | `config.py` |

### 4.3 Loading a DomainConfig from YAML

The loader is a single function:

```python
import yaml
from pathlib import Path

def load_domain_config(path: Path) -> DomainConfig:
    """Load and validate a DomainConfig from a YAML file.

    Raises ValidationError if the YAML is malformed or cross-references are invalid.
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return DomainConfig(**raw)
```

That's it. Pydantic handles all the parsing, type coercion, default filling, and cross-reference validation. If the YAML is wrong, you get a clear error message like:

```
DomainConfig cross-reference errors:
  - BU 'BU-001' references unknown control type: 'Reconiliation'   ← typo caught!
  - Control type 'Authorization' references unknown placement: 'Proactive'  ← wrong name caught!
```

### 4.4 Writing a Minimal domain_config.yaml

Here's the smallest valid config — a tiny org with 3 control types, 2 BUs, and 2 sections:

```yaml
name: "community-bank-demo"
description: "Minimal config for a small community bank"

control_types:
  - name: Authorization
    definition: "Approval by authorized personnel before a transaction is processed"
    code: AUT
    min_frequency_tier: Quarterly
    placement_categories: [Preventive]
    evidence_criteria:
      - "Names the approval authority"
      - "References approval limits/thresholds"

  - name: Reconciliation
    definition: "Comparison of records to validate accuracy and completeness"
    code: REC
    min_frequency_tier: Monthly
    placement_categories: [Detective]
    evidence_criteria:
      - "Names specific reconciliation report"
      - "Identifies preparer and reviewer"

  - name: Exception Reporting
    definition: "Identification and reporting of items outside normal parameters"
    code: EXR
    min_frequency_tier: Monthly
    placement_categories: [Detective]

business_units:
  - id: "BU-001"
    name: "Retail Banking"
    description: "Consumer-facing banking products"
    primary_sections: ["1.0"]
    key_control_types: ["Authorization", "Reconciliation"]
    regulatory_exposure: ["SOX", "OCC"]

  - id: "BU-002"
    name: "Operations"
    description: "Back-office processing and settlement"
    primary_sections: ["1.0", "2.0"]
    key_control_types: ["Reconciliation", "Exception Reporting"]

process_areas:
  - id: "1.0"
    name: "Lending Operations"
    domain: "lending"
    risk_profile:
      inherent_risk: 3
      regulatory_intensity: 4
      control_density: 3
      multiplier: 1.2
      rationale: "High regulatory scrutiny on lending"
    affinity:
      HIGH: ["Authorization", "Reconciliation"]
      MEDIUM: ["Exception Reporting"]
    registry:
      roles: ["Loan Officer", "Credit Analyst", "Branch Manager"]
      systems: ["Loan Origination System", "Credit Bureau Platform"]
      evidence_artifacts: ["Loan approval form", "Credit decision report"]
      event_triggers: ["Loan application submitted", "Credit limit exceeded"]
      regulatory_frameworks: ["SOX", "OCC Lending Guidelines"]

  - id: "2.0"
    name: "Settlement and Clearing"
    domain: "operations"
    risk_profile:
      inherent_risk: 2
      regulatory_intensity: 2
      control_density: 2
      multiplier: 0.8
      rationale: "Standard operational risk"
    affinity:
      HIGH: ["Reconciliation"]
      MEDIUM: ["Exception Reporting"]
      LOW: ["Authorization"]
    registry:
      roles: ["Settlement Officer", "Operations Analyst"]
      systems: ["Core Banking Platform", "SWIFT Gateway"]
      evidence_artifacts: ["Settlement confirmation", "Reconciliation report"]
      event_triggers: ["End of day batch", "Failed transaction"]
      regulatory_frameworks: ["Basel III"]

# Placements, methods, frequency_tiers, narrative, quality_ratings all use
# the defaults defined in the DomainConfig model — no need to specify them
# unless you want to override.
```

Compare this to the current system which requires:
- `taxonomy.yaml` (25 types, 17 BUs)
- `placement_methods.yaml`
- `standards.yaml`
- 13 separate `section_N.yaml` files
- Hardcoded Python constants matching all of the above

**One file. Everything in one place. Validated on load.**

### 4.5 Validation Rules

The `@model_validator` on `DomainConfig` checks these cross-references:

| Rule | What it catches |
|------|----------------|
| BU `key_control_types` must exist in `control_types` | Typos in control type names |
| BU `primary_sections` must exist in `process_areas` | Referencing a section that doesn't exist |
| Control type `placement_categories` must exist in `placements` | Invalid placement name |
| Control type `min_frequency_tier` must exist in `frequency_tiers` | Invalid frequency label |
| Section affinity types must exist in `control_types` | Affinity matrix with typo'd type name |

If any check fails, you get a list of **all** errors at once (not just the first one), with clear messages pointing to the exact problem.

### 4.6 Tests to Write

These are the tests you'll need for Step 1. Write them **before** the implementation (test-driven development):

```python
class TestDomainConfigLoading:
    """Test YAML → DomainConfig parsing."""

    def test_minimal_config_loads(self):
        """The community bank demo config should load without errors."""

    def test_empty_control_types_raises(self):
        """At least one control type is required."""

    def test_unknown_bu_control_type_raises(self):
        """A BU referencing a non-existent control type should fail validation."""

    def test_unknown_placement_category_raises(self):
        """A control type referencing a non-existent placement should fail."""

    def test_unknown_frequency_tier_raises(self):
        """A min_frequency_tier that doesn't match any tier label should fail."""

    def test_defaults_filled(self):
        """A config with no placements/methods/frequency_tiers should get defaults."""

    def test_custom_narrative_fields(self):
        """Custom narrative fields (e.g., 'key_report') should be accepted."""


class TestDomainConfigHelpers:
    """Test computed properties that replace hardcoded constants."""

    def test_type_code_map_uses_config_codes(self):
        """type_code_map() should return {name: code} from config."""

    def test_type_code_map_auto_generates_missing_codes(self):
        """If code is blank, auto-generate from consonants."""

    def test_min_frequency_types_monthly(self):
        """min_frequency_types('Monthly') should return types with rank ≤ 3."""

    def test_min_frequency_types_quarterly(self):
        """min_frequency_types('Quarterly') should include monthly types too."""

    def test_section_ids(self):
        """section_ids() should return IDs from process_areas."""

    def test_get_process_area(self):
        """get_process_area('1.0') should return the matching ProcessAreaConfig."""

    def test_get_process_area_missing(self):
        """get_process_area('99.0') should return None."""

    def test_placement_names(self):
        """placement_names() returns list of placement name strings."""

    def test_narrative_field_names(self):
        """narrative_field_names() returns ['who', 'what', 'when', 'where', 'why', ...]."""
```

**Files to create in Step 1:**

| File | Purpose |
|------|---------|
| `src/controlnexus/core/domain_config.py` | The `DomainConfig` model + all inner models + `load_domain_config()` |
| `config/profiles/community_bank_demo.yaml` | The minimal example config from §4.4 |
| `tests/test_domain_config.py` | All tests from §4.6 |

---

## 5. Step 2 — The Minimal StateGraph

Once `DomainConfig` loads and validates, we can build the graph that uses it to generate controls.

### 5.1 Why a Graph Instead of a Class?

The current `Orchestrator` is a 950-line class with deeply nested methods. The control generation loop looks like this in pseudocode:

```python
# Inside Orchestrator.execute_planning():
for assignment in assignments:
    spec = await spec_agent.execute(**kwargs)   # or fallback
    for retry in range(3):
        narrative = await narrative_agent.execute(**kwargs)
        if validate(narrative, spec):
            break
    enriched = await enricher_agent.execute(**kwargs)
    records.append(enriched)
```

This is hard to modify because:
- The retry logic is a `for` loop inside a method — you can't add a step between validation and retry without touching the loop body.
- Adding a new agent (e.g., adversarial reviewer) means adding more code inside the same deeply nested method.
- Testing one step requires mocking everything.

A StateGraph makes each step a **separate function** connected by **declarative edges**:

```python
graph.add_node("spec", spec_node)
graph.add_node("narrative", narrative_node)
graph.add_node("validate", validate_node)
graph.add_node("enrich", enrich_node)
graph.add_node("merge", merge_node)

graph.add_edge("spec", "narrative")
graph.add_edge("narrative", "validate")
graph.add_conditional_edges("validate", should_retry, {
    "retry": "narrative",   # go back to narrative
    "pass": "enrich",       # proceed
})
graph.add_edge("enrich", "merge")
```

Now:
- Adding an adversarial reviewer = add a node + add an edge. No existing code changes.
- Testing `validate_node` = call it with a state dict. No orchestrator instance needed.
- The retry "loop" is a conditional edge — visible in the graph topology, not hidden inside a `for`.

### 5.2 The State TypedDict

LangGraph uses a Python `TypedDict` for the graph's state. Every node receives the entire state and returns a dict of updated fields.

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph import add  # reducer for parallel-safe list accumulation

class ForgeState(TypedDict, total=False):
    """State for the ControlForge Modular graph."""

    # ── Config (set once by init_node) ──
    domain_config: dict[str, Any]          # DomainConfig.model_dump()
    llm_enabled: bool

    # ── Assignment tracking ──
    assignments: list[dict[str, Any]]      # full matrix of assignments
    current_idx: int                       # index into assignments
    current_assignment: dict[str, Any]     # assignments[current_idx]

    # ── Per-control pipeline ──
    current_spec: dict[str, Any]           # SpecAgent output
    current_narrative: dict[str, Any]      # NarrativeAgent output
    current_enriched: dict[str, Any]       # EnricherAgent output
    retry_count: int                       # 0-3
    validation_passed: bool

    # ── Accumulated output ──
    generated_records: Annotated[list[dict[str, Any]], add]

    # ── Final ──
    plan_payload: dict[str, Any]
```

**Why `Annotated[list, add]`?** The `add` reducer tells LangGraph: "when a node returns `generated_records: [new_record]`, **append** it to the existing list instead of replacing it." This is critical for the loop — each iteration of merge_node adds one record without overwriting the previous ones. It also enables parallel accumulation in the future (Phase 4 of the vision doc).

**Why `total=False`?** This makes all fields optional. Nodes only need to return the fields they're updating. If `spec_node` only changes `current_spec`, it returns `{"current_spec": {...}}` and everything else stays unchanged.

### 5.3 Graph Topology (5 Nodes)

The minimal graph for Step 2 has 5 nodes. This is deliberately simpler than the 9-node graph described in the vision doc — we're building a working foundation first.

```
START → init → select → generate → merge → [more?]
                 ↑                            |
                 └────────── yes ─────────────┘
                                              |
                                             no
                                              ↓
                                          finalize → END
```

**Why only 5 nodes, not separate spec/narrative/enrich nodes?**

In Step 2, we're building **deterministic-only** generation (no LLM). The spec, narrative, and enrichment are all template-based and take <1ms each. Splitting them into separate nodes adds complexity without benefit yet. Once we add LLM agents in a later step, we split `generate_node` into `spec_node → narrative_node → validate_node → enrich_node`.

### 5.4 Node Implementations

Each node is a plain Python function:

```python
def init_node(state: ForgeState) -> dict[str, Any]:
    """Load DomainConfig, detect LLM, build assignment matrix."""
    config_path = state.get("config_path", "")
    domain_config = load_domain_config(Path(config_path))

    # Build assignment matrix: section × type × BU
    assignments = build_assignment_matrix(domain_config, target_count=state.get("target_count", 10))

    return {
        "domain_config": domain_config.model_dump(),
        "assignments": assignments,
        "llm_enabled": False,  # Step 2 is deterministic only
        "current_idx": 0,
        "generated_records": [],
    }
```

```python
def select_node(state: ForgeState) -> dict[str, Any]:
    """Pick the current assignment and reset per-control state."""
    idx = state["current_idx"]
    return {
        "current_assignment": state["assignments"][idx],
        "retry_count": 0,
        "validation_passed": False,
    }
```

```python
def generate_node(state: ForgeState) -> dict[str, Any]:
    """Generate a deterministic control from the assignment + config."""
    assignment = state["current_assignment"]
    config = DomainConfig(**state["domain_config"])  # reconstruct from dict

    # Build spec from assignment + registry
    spec = build_deterministic_spec(assignment, config)
    narrative = build_deterministic_narrative(spec, config)
    enriched = build_deterministic_enriched(narrative, config)

    return {
        "current_spec": spec,
        "current_narrative": narrative,
        "current_enriched": enriched,
        "validation_passed": True,
    }
```

```python
def merge_node(state: ForgeState) -> dict[str, Any]:
    """Append the current record and advance the index."""
    return {
        "generated_records": [state["current_enriched"]],  # appended via add reducer
        "current_idx": state["current_idx"] + 1,
    }
```

```python
def finalize_node(state: ForgeState) -> dict[str, Any]:
    """Assign control IDs and build the plan payload."""
    config = DomainConfig(**state["domain_config"])
    records = state["generated_records"]
    code_map = config.type_code_map()

    final_records = []
    for i, record in enumerate(records):
        type_code = code_map.get(record.get("control_type", ""), "UNK")
        record["control_id"] = build_control_id(record["hierarchy_id"], type_code, i + 1)
        final_records.append(record)

    return {
        "generated_records": [],  # clear via reducer (we replace with final)
        "plan_payload": {
            "total_controls": len(final_records),
            "config_name": config.name,
            "final_records": final_records,
        },
    }
```

### 5.5 The Assignment Loop

The conditional edge that makes the loop work:

```python
def has_more(state: ForgeState) -> str:
    """Route back to select or forward to finalize."""
    next_idx = state.get("current_idx", 0)
    total = len(state.get("assignments", []))
    if next_idx < total:
        return "select"
    return "finalize"
```

```python
# Graph construction:
from langgraph.graph import StateGraph, END

def build_forge_graph() -> StateGraph:
    graph = StateGraph(ForgeState)

    graph.add_node("init", init_node)
    graph.add_node("select", select_node)
    graph.add_node("generate", generate_node)
    graph.add_node("merge", merge_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("init")
    graph.add_edge("init", "select")
    graph.add_edge("select", "generate")
    graph.add_edge("generate", "merge")
    graph.add_conditional_edges("merge", has_more, {
        "select": "select",
        "finalize": "finalize",
    })
    graph.add_edge("finalize", END)

    return graph
```

This is the entire graph. Deploy it, run it, get controls. No LLM needed for Step 2.

### 5.6 Tests to Write

```python
class TestForgeGraph:
    """Test the minimal StateGraph execution."""

    def test_graph_produces_correct_count(self):
        """Graph with target_count=5 should produce 5 records."""

    def test_graph_assigns_control_ids(self):
        """Every final record should have a control_id field."""

    def test_graph_uses_config_type_codes(self):
        """Control IDs should use the code from DomainConfig, not hardcoded map."""

    def test_graph_loops_all_assignments(self):
        """current_idx at exit should equal len(assignments)."""

    def test_graph_with_custom_config(self):
        """A config with 2 types + 1 section should produce valid output."""

    def test_graph_deterministic_output(self):
        """Same config + same seed → identical output."""
```

**Files to create in Step 2:**

| File | Purpose |
|------|---------|
| `src/controlnexus/graphs/forge_modular_graph.py` | The StateGraph + all node functions + `build_forge_graph()` |
| `src/controlnexus/graphs/forge_modular_helpers.py` | `build_assignment_matrix()`, `build_deterministic_spec()`, etc. |
| `tests/test_forge_modular_graph.py` | All tests from §5.6 |

---

## 6. Step 3 — The Streamlit Tab

The final piece of Step 1's scope: a simple Streamlit tab where the user selects a config, runs the graph, and sees results.

### 6.1 Config Selection UI

```python
import streamlit as st
from pathlib import Path

def render_modular_tab():
    st.header("ControlForge Modular")

    # Config file selector
    profiles_dir = Path("config/profiles")
    config_files = sorted(profiles_dir.glob("*.yaml"))
    selected = st.selectbox(
        "Select organization config",
        options=config_files,
        format_func=lambda p: p.stem.replace("_", " ").title(),
    )

    # Target count
    target_count = st.number_input("Number of controls to generate", min_value=1, max_value=500, value=10)

    # Preview
    if selected:
        config = load_domain_config(selected)
        col1, col2, col3 = st.columns(3)
        col1.metric("Control Types", len(config.control_types))
        col2.metric("Business Units", len(config.business_units))
        col3.metric("Process Areas", len(config.process_areas))
```

This gives the user immediate feedback: "I selected the community bank config. It has 3 types, 2 BUs, and 2 sections."

### 6.2 Running the Graph

```python
    if st.button("Generate Controls"):
        with st.spinner("Generating..."):
            graph = build_forge_graph()
            compiled = graph.compile()
            result = compiled.invoke({
                "config_path": str(selected),
                "target_count": target_count,
            })

        st.success(f"Generated {result['plan_payload']['total_controls']} controls")
```

### 6.3 Displaying Results

```python
        # Show as table
        records = result["plan_payload"]["final_records"]
        st.dataframe(records)

        # Download as Excel
        # (use the existing export.excel module or pandas to_excel)
```

**Files to create in Step 3:**

| File | Purpose |
|------|---------|
| `src/controlnexus/ui/modular_tab.py` | `render_modular_tab()` function |
| Update: `src/controlnexus/ui/app.py` | Add the tab to the Streamlit sidebar |

---

## 7. File Layout

After completing Steps 1–3, the new files are:

```
src/controlnexus/
  core/
    domain_config.py          ← NEW: DomainConfig model + loader
  graphs/
    forge_modular_graph.py    ← NEW: StateGraph + nodes
    forge_modular_helpers.py  ← NEW: assignment matrix, deterministic builders
  ui/
    modular_tab.py            ← NEW: Streamlit tab
    app.py                    ← MODIFIED: add tab

config/
  profiles/
    community_bank_demo.yaml  ← NEW: example config
    banking_standard.yaml     ← NEW: config equivalent to current 25-type/17-BU/13-section setup

tests/
  test_domain_config.py       ← NEW: config model tests
  test_forge_modular_graph.py ← NEW: graph tests
```

No existing files are modified except `app.py` (to register the new tab).

---

## 8. Future Work

Once Steps 1–3 are complete and tested, here's the roadmap for what comes next. Each item builds on the foundation above:

1. **LLM Agent Integration**: Split `generate_node` into `spec_node → narrative_node → validate_node → enrich_node`. Wire the existing `SpecAgent`, `NarrativeAgent`, and `EnricherAgent` into these nodes. Add an `llm_enabled` toggle in the UI. Agent system prompts become **templates** that read placement options, methods, evidence criteria, and word count constraints from `DomainConfig` instead of being hardcoded strings. This is the single biggest unlock — the agents become config-aware.

2. **Tool Calling**: Wire the 5 foundation tools (`taxonomy_validator`, `regulatory_lookup`, `hierarchy_search`, `frequency_lookup`, `memory_retrieval`) into the agent nodes using the tool-calling loop described in the vision doc §6.2. Agent prompts are slimmed down because agents can look up what they need on-demand. The tools read from `DomainConfig` — a different config means different tool behavior, automatically.

3. **Validation & Quality Gates**: Add the `validator_node` with retry conditional edges (pass → enrich, fail → retry narrative, max 3 retries). Then implement quality gate scorer functions as quality gate nodes with config-driven thresholds.

4. **Event Backbone & Real-Time UI**: Wire `EventEmitter` into graph nodes so the UI shows a live activity feed instead of a spinner. Every agent turn, tool call, and quality score emits an event. The vision doc §8 describes the event → UI mapping.

5. **Memory Integration**: Connect ChromaDB `ControlMemory` to the graph so generated controls are indexed and queryable across runs. Enable `control_precedent_search` to find high-quality exemplars from previous runs. The vision doc §9.4 covers the quality-annotated memory schema.

6. **Config UI Wizard**: Build a guided Streamlit interface where non-technical users can create their own `domain_config.yaml` by filling in forms instead of editing YAML. Include an "Upload existing register" feature that analyzes an Excel file and proposes a config. This is the long-term goal for accessibility.

7. **Banking Standard Migration**: Create a `banking_standard.yaml` that exactly reproduces the current 25-type/17-BU/13-section setup. Run both the old `Orchestrator` and the new graph on the same inputs and verify field-by-field output parity. This is the migration path for existing users.
