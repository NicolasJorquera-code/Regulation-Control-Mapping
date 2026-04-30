# ControlForge Modular: "Build from Form" — Deep Dive

> **Audience**: Engineers, product stakeholders, and compliance domain experts who need a complete understanding of what the Build from Form wizard does today, how every screen and backend component works, what data it draws on, and where the feature can be expanded based on the existing codebase, data assets, and architectural direction.

---

## Table of Contents

- [1. System Context — Where Build from Form Lives](#1-system-context--where-build-from-form-lives)
  - [1.1 The Four-Tab Dashboard](#11-the-four-tab-dashboard)
  - [1.2 The Three Config Input Paths](#12-the-three-config-input-paths)
  - [1.3 The Central Data Object: DomainConfig](#13-the-central-data-object-domainconfig)
- [2. Build from Form — Step-by-Step Frontend Detail](#2-build-from-form--step-by-step-frontend-detail)
  - [2.1 Wizard Architecture and State Management](#21-wizard-architecture-and-state-management)
  - [2.2 Step 1: Basics](#22-step-1-basics)
  - [2.3 Step 2: Control Types](#23-step-2-control-types)
  - [2.4 Step 3: Business Units](#24-step-3-business-units)
  - [2.5 Step 4: Process Areas](#25-step-4-process-areas)
  - [2.6 Step 5: Narrative & Quality Settings](#26-step-5-narrative--quality-settings)
  - [2.7 Step 6: Review & Export](#27-step-6-review--export)
- [3. Backend Flow — What Happens After Config Activation](#3-backend-flow--what-happens-after-config-activation)
  - [3.1 The Modular Tab: Generation Settings](#31-the-modular-tab-generation-settings)
  - [3.2 Assignment Matrix Builder](#32-assignment-matrix-builder)
  - [3.3 The 8-Node LangGraph StateGraph](#33-the-8-node-langgraph-stategraph)
  - [3.4 Dual-Mode Prompt Architecture](#34-dual-mode-prompt-architecture)
  - [3.5 Tool Calling — 9 Domain-Aware Tools](#35-tool-calling--9-domain-aware-tools)
  - [3.6 Deterministic Fallback Builders](#36-deterministic-fallback-builders)
  - [3.7 The 6-Rule Validator](#37-the-6-rule-validator)
  - [3.8 Control ID Assignment](#38-control-id-assignment)
  - [3.9 Real-Time Event Streaming](#39-real-time-event-streaming)
- [4. The Agent System](#4-the-agent-system)
  - [4.1 BaseAgent and the Agent Registry](#41-baseagent-and-the-agent-registry)
  - [4.2 ConfigProposerAgent (Wizard AI)](#42-configproposeragent-wizard-ai)
  - [4.3 SpecAgent, NarrativeAgent, EnricherAgent (Generation Agents)](#43-specagent-narrativeagent-enricheragent-generation-agents)
  - [4.4 AdversarialReviewer and DifferentiationAgent (Unused in Wizard)](#44-adversarialreviewer-and-differentiationagent-unused-in-wizard)
- [5. Data Assets — YAML Configs the System Ships With](#5-data-assets--yaml-configs-the-system-ships-with)
  - [5.1 Profile Configs](#51-profile-configs)
  - [5.2 Section YAMLs](#52-section-yamls)
  - [5.3 Legacy Config Files](#53-legacy-config-files)
- [6. Infrastructure Already Built but Not Yet Wired](#6-infrastructure-already-built-but-not-yet-wired)
  - [6.1 ChromaDB Memory Store](#61-chromadb-memory-store)
  - [6.2 Register Analyzer (Excel Import)](#62-register-analyzer-excel-import)
  - [6.3 Analysis Tab and Gap Scanners](#63-analysis-tab-and-gap-scanners)
  - [6.4 Remediation Graph and Planner](#64-remediation-graph-and-planner)
- [7. Frontend Improvements — Detailed Proposals](#7-frontend-improvements--detailed-proposals)
  - [7.1 Template Library and Starter Configs](#71-template-library-and-starter-configs)
  - [7.2 Import from Section YAMLs](#72-import-from-section-yamls)
  - [7.3 AI-Assisted Section Discovery](#73-ai-assisted-section-discovery)
  - [7.4 Drag-and-Drop Affinity Grid](#74-drag-and-drop-affinity-grid)
  - [7.5 Visual Risk Heat Map / Radar Chart](#75-visual-risk-heat-map--radar-chart)
  - [7.6 Inline Validation and Completeness Indicators](#76-inline-validation-and-completeness-indicators)
  - [7.7 Undo History and Config Snapshots](#77-undo-history-and-config-snapshots)
  - [7.8 Side-by-Side Config Comparison](#78-side-by-side-config-comparison)
  - [7.9 Rich Exemplar Editor with AI Generation](#79-rich-exemplar-editor-with-ai-generation)
  - [7.10 Config Quality Scorer](#710-config-quality-scorer)
  - [7.11 Collaborative Config Building](#711-collaborative-config-building)
  - [7.12 Full-Screen Section Editor](#712-full-screen-section-editor)
- [8. Backend and Pipeline Expansions](#8-backend-and-pipeline-expansions)
  - [8.1 Wire the ChromaDB Memory Store](#81-wire-the-chromadb-memory-store)
  - [8.2 Adversarial Review Pass](#82-adversarial-review-pass)
  - [8.3 Differentiation Agent Integration](#83-differentiation-agent-integration)
  - [8.4 Analysis Tab Cross-Feed](#84-analysis-tab-cross-feed)
  - [8.5 Multi-LLM Provider Strategy](#85-multi-llm-provider-strategy)
  - [8.6 Parallel / Batch Generation](#86-parallel--batch-generation)
  - [8.7 Custom Validation Rules from DomainConfig](#87-custom-validation-rules-from-domainconfig)
  - [8.8 Export Format Expansion](#88-export-format-expansion)
  - [8.9 Config Versioning and Diff](#89-config-versioning-and-diff)
- [9. Data and Ecosystem Expansions](#9-data-and-ecosystem-expansions)
  - [9.1 Industry Config Packs](#91-industry-config-packs)
  - [9.2 Regulatory Framework Catalog](#92-regulatory-framework-catalog)
  - [9.3 APQC Process Framework Mapping](#93-apqc-process-framework-mapping)
  - [9.4 Multi-Language and Multi-Jurisdiction Support](#94-multi-language-and-multi-jurisdiction-support)
- [10. Future Architecture Directions](#10-future-architecture-directions)
  - [10.1 Multi-Bank Federated Control Intelligence](#101-multi-bank-federated-control-intelligence)
  - [10.2 Regulatory Horizon Scanning](#102-regulatory-horizon-scanning)
  - [10.3 Autonomous Control Lifecycle Management](#103-autonomous-control-lifecycle-management)
  - [10.4 Adversarial Stress Testing as a Service](#104-adversarial-stress-testing-as-a-service)
  - [10.5 Cross-Framework Harmonization Engine](#105-cross-framework-harmonization-engine)
- [11. Summary Matrix — Current vs. Expansion Potential](#11-summary-matrix--current-vs-expansion-potential)

---

## 1. System Context — Where Build from Form Lives

### 1.1 The Four-Tab Dashboard

The ControlNexus application is a Streamlit dashboard launched via `streamlit run src/controlnexus/ui/app.py`. It presents four main tabs:

| Tab | Purpose | Key Module |
|---|---|---|
| **ControlForge** | Original (legacy) configuration explorer and monolithic orchestrator pipeline | `ui/controlforge_tab.py`, `pipeline/orchestrator.py` |
| **ControlForge Modular** | **The new, config-driven system** — select/build/import a DomainConfig, then generate controls via LangGraph | `ui/modular_tab.py`, `graphs/forge_modular_graph.py` |
| **Analysis** | Upload existing controls (Excel), run gap analysis scanners, view a gap dashboard, trigger remediation | `ui/components/analysis_runner.py`, `analysis/scanners.py` |
| **Playground** | Interactive environment for testing individual agents in isolation | `ui/playground.py` |

The **ControlForge Modular** tab is where "Build from Form" lives. The tab is rendered by `render_modular_tab()` in `ui/modular_tab.py`, which immediately calls `render_config_input()` from `ui/config_input.py` to present the three config input sub-tabs.

### 1.2 The Three Config Input Paths

The Organization Config section at the top of the Modular tab presents three Streamlit sub-tabs:

| Sub-Tab | Label | Implementation | UX Flow |
|---|---|---|---|
| 📁 **Select Profile** | Pick a pre-built YAML | `ui/config_input.py::_render_select_profile()` | Dropdown of `.yaml` files from `config/profiles/`, or drag-and-drop upload of a custom YAML. Loaded via `load_domain_config()`, cached with `@st.cache_data`. |
| 📝 **Build from Form** | 6-step guided wizard | `ui/config_wizard.py::render_config_wizard()` | The focus of this document. A multi-step form that constructs a `DomainConfig` interactively with optional AI assistance at every step. |
| 📤 **Import from Excel** | Upload a register, AI proposes config | `ui/excel_import.py::render_excel_import()` | Upload `.xlsx` → `RegisterAnalyzer` extracts a summary (control types, BUs, sections, roles, systems, frequencies, regulatory mentions) → `ConfigProposerAgent` (full mode) proposes a `DomainConfig` → user reviews, downloads, or activates. |

All three paths converge on the same result: a validated `DomainConfig` Pydantic model stored in `st.session_state["wizard_active_config"]`. Once activated, the rest of the Modular tab (generation settings, distribution sliders, generate button, results table) becomes available.

### 1.3 The Central Data Object: DomainConfig

The `DomainConfig` class (defined in `core/domain_config.py`, ~370 lines) is a Pydantic `BaseModel` that serves as the **single source of truth** for an organization's control domain. Every value the generation pipeline needs comes from this one object — no hardcoded constants, no scattered YAML files.

**Top-level structure:**

```python
class DomainConfig(BaseModel):
    name: str = "default"
    description: str = ""
    control_types: list[ControlTypeConfig]        # min_length=1
    business_units: list[BusinessUnitConfig] = []
    process_areas: list[ProcessAreaConfig] = []
    placements: list[PlacementConfig] = [...]      # default: Preventive, Detective, Contingency Planning
    methods: list[MethodConfig] = [...]            # default: Automated, Manual, Automated with Manual Component
    frequency_tiers: list[FrequencyTier] = [...]   # default: Daily through Annual with keyword lists
    narrative: NarrativeConstraints = ...           # fields, word_count_min, word_count_max
    quality_ratings: list[str] = [...]             # default: Strong, Effective, Satisfactory, Needs Improvement
```

**Nested models in detail:**

| Model | Fields | Purpose |
|---|---|---|
| `ControlTypeConfig` | `name`, `definition`, `code` (3 letters), `min_frequency_tier`, `placement_categories[]`, `evidence_criteria[]` | Defines one control type (e.g., "Authorization") with its taxonomy rules |
| `BusinessUnitConfig` | `id`, `name`, `description`, `primary_sections[]`, `key_control_types[]`, `regulatory_exposure[]` | Defines one BU with cross-references to sections and types |
| `ProcessAreaConfig` | `id`, `name`, `domain`, `risk_profile`, `affinity`, `registry`, `exemplars[]` | Defines one process area with all its domain knowledge |
| `RiskProfileConfig` | `inherent_risk` (1-5), `regulatory_intensity` (1-5), `control_density` (1-5), `multiplier` (float), `rationale` | Risk scoring that drives control distribution |
| `AffinityConfig` | `HIGH[]`, `MEDIUM[]`, `LOW[]`, `NONE[]` | Maps control types to relevance levels for this section |
| `RegistryConfig` | `roles[]`, `systems[]`, `data_objects[]`, `evidence_artifacts[]`, `event_triggers[]`, `regulatory_frameworks[]` | Domain vocabulary used by LLM and deterministic builders |
| `ExemplarConfig` | `control_type`, `placement`, `method`, `full_description`, `word_count`, `quality_rating` | Style reference controls for the LLM |
| `FrequencyTier` | `label`, `rank` (int), `keywords[]` | Frequency levels with keyword-matching rules for auto-derivation |
| `NarrativeConstraints` | `fields[]` (NarrativeField), `word_count_min`, `word_count_max` | Defines the 5W output schema and word limits |

**Cross-reference validation**: On instantiation, a `@model_validator(mode="after")` runs `_validate_cross_references()` which checks:
- Every control type name referenced in `business_units[].key_control_types` exists in `control_types[].name`
- Every section ID in `business_units[].primary_sections` exists in `process_areas[].id`
- Every placement in `control_types[].placement_categories` exists in `placements[].name`
- Every `min_frequency_tier` label exists in `frequency_tiers[].label`
- Every control type name in `process_areas[].affinity.{HIGH,MEDIUM,LOW,NONE}` exists in `control_types[].name`

If any reference is broken, a `ValueError` is raised with all errors listed. This validation is what Step 6 of the wizard triggers.

**Computed properties** on `DomainConfig`:
- `type_code_map()` → `dict[str, str]` mapping type name to 3-letter code
- `frequency_tier_rank(label)` → `int | None`
- `min_frequency_types(at_or_better_than)` → `set[str]` of types needing that frequency or tighter
- `section_ids()` → `list[str]`
- `get_process_area(section_id)` → `ProcessAreaConfig | None`
- `placement_names()` → `list[str]`
- `method_names()` → `list[str]`

---

## 2. Build from Form — Step-by-Step Frontend Detail

### 2.1 Wizard Architecture and State Management

The wizard is implemented in `ui/config_wizard.py` (~870 lines). It uses **two session state keys**:

- `st.session_state["wizard_form"]` — A plain `dict[str, Any]` holding all form data across all 6 steps. Initialized once with sensible defaults (empty lists for types/BUs/process areas, default placements/methods/tiers).
- `st.session_state["wizard_step"]` — An integer (1-6) tracking the current step.

**Layout**: The wizard renders as a two-column layout:
- **Left column (1/5 width)**: Sidebar showing step progress. Completed steps have a ✅ icon and are clickable (navigate back). Current step has a ● icon. Future steps are greyed out (○ icon, not clickable). Navigation uses `_set_step(i)` + `st.rerun()`.
- **Right column (4/5 width)**: The main content area showing the current step's form.

**Navigation**: Each step has "← Back" and "Next →" buttons. The "Next →" button on each step validates that step's minimum requirements before advancing. Going back never loses data — everything is stored in the `wizard_form` dict.

**Default values pre-populated in `wizard_form`**:

```python
{
    "name": "",
    "description": "",
    "control_types": [],
    "business_units": [],
    "process_areas": [],
    "placements": [
        {"name": "Preventive", "description": ""},
        {"name": "Detective", "description": ""},
        {"name": "Contingency Planning", "description": ""},
    ],
    "methods": [
        {"name": "Automated", "description": ""},
        {"name": "Manual", "description": ""},
        {"name": "Automated with Manual Component", "description": ""},
    ],
    "frequency_tiers": [
        {"label": "Daily", "rank": 1, "keywords": ["daily", "every day", "eod"]},
        {"label": "Weekly", "rank": 2, "keywords": ["weekly", "every week"]},
        {"label": "Monthly", "rank": 3, "keywords": ["monthly", "every month", "month-end"]},
        {"label": "Quarterly", "rank": 4, "keywords": ["quarterly", "every quarter"]},
        {"label": "Semi-Annual", "rank": 5, "keywords": ["semi-annual", "twice a year"]},
        {"label": "Annual", "rank": 6, "keywords": ["annual", "annually", "yearly"]},
    ],
    "quality_ratings": ["Strong", "Effective", "Satisfactory", "Needs Improvement"],
    "narrative": {
        "fields": [
            {"name": "who", "definition": "The specific role responsible for performing the control", "required": True},
            {"name": "what", "definition": "The specific action performed", "required": True},
            {"name": "when", "definition": "The timing or trigger for the control", "required": True},
            {"name": "where", "definition": "The system or location where the control is performed", "required": True},
            {"name": "why", "definition": "The risk or objective the control addresses", "required": True},
            {"name": "full_description", "definition": "Prose narrative incorporating all fields", "required": True},
        ],
        "word_count_min": 30,
        "word_count_max": 80,
    },
}
```

### 2.2 Step 1: Basics

**What the user sees**: Two input fields:
- **Config Name** (`st.text_input`) — Placeholder: "e.g. community-bank-demo". This becomes `DomainConfig.name`.
- **Description** (`st.text_area`, 100px height) — Placeholder: "Brief description of the organization and control domain." This becomes `DomainConfig.description`.

**Validation on "Next →"**: Config name must be non-empty (`.strip()` check). If empty, `st.error("Config name is required.")`.

**What gets stored**: `form["name"]` and `form["description"]`.

**Possible interactions**: None — this is the simplest step. No AI, no dynamic content.

### 2.3 Step 2: Control Types

**What the user sees**: A dynamic list of control type entries, with two action buttons at the top side by side:

**Button: "➕ Add Control Type"**
- Appends a blank entry `{"name": "", "definition": "", "code": "", "min_frequency_tier": None, "placement_categories": [], "evidence_criteria": []}` to the list.
- Triggers `st.rerun()` to re-render.

**Button: "🤖 Auto-fill Definitions with AI"**
- Collects all non-empty names from the current type list.
- If no names exist, shows `st.warning("Add at least one control type name first.")`.
- Otherwise, shows a `st.status("Enriching control types…")` spinner and calls `_run_enrich(names)`.
- This function:
  1. Creates an `AsyncTransportClient` via `build_client_from_env()` (checks `ICA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` env vars).
  2. Creates an `AgentContext` with `temperature=0.2`, `max_tokens=2048`, `timeout_seconds=120`.
  3. Creates a `ConfigProposerAgent` instance.
  4. Calls `agent.execute(mode="enrich", type_names=names)` which sends the LLM a system prompt asking it to propose definitions, codes, evidence criteria, frequency tiers, and placement categories.
  5. Returns the enriched types as a dict.
- Merges LLM results into the form **without overwriting fields the user has already filled in**. For each type, it only fills in `definition`, `code`, `evidence_criteria`, `min_frequency_tier`, and `placement_categories` if they are currently empty/None.
- If the LLM fails, shows `st.error()` with the error message and the status shows ❌.
- If the LLM is not configured (no API keys), the call to `build_client_from_env()` returns `None`, and the agent uses a **deterministic fallback** that generates minimal entries: `"Controls related to {name.lower()}."` as definition, auto-code from consonants, `["Detective"]` as placement, empty evidence.

**Each control type entry** is rendered inside an `st.expander` titled "Control Type {i+1}: {name or '(unnamed)'}". When name is empty, the expander starts expanded.

| Widget | Key | Details |
|---|---|---|
| `st.text_input("Name")` | `wiz_ct_name_{i}` | e.g., "Authorization" |
| `st.text_area("Definition", height=80)` | `wiz_ct_def_{i}` | 1-2 sentence description of the control type |
| `st.text_input("Code", max_chars=3)` | `wiz_ct_code_{i}` | Pre-filled with `_auto_code(name)` if blank. `_auto_code()` strips vowels and spaces from the name, takes first 3 consonants uppercase. E.g., "Authorization" → "THR", "Reconciliation" → "RCN" |
| `st.selectbox("Min Frequency Tier")` | `wiz_ct_freq_{i}` | Options: `[None, "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual"]`. Display uses `format_func=lambda x: x or "None"`. |
| `st.multiselect("Placement Categories")` | `wiz_ct_place_{i}` | Options drawn from `form["placements"]` names (defaults: Preventive, Detective, Contingency Planning). Already-selected values are preserved in `default`. |
| `st.text_area("Evidence Criteria", height=80)` | `wiz_ct_evid_{i}` | One criterion per line. Parsed by `[line.strip() for line in text.split("\n") if line.strip()]`. |
| `st.button("🗑 Remove")` | `wiz_ct_rm_{i}` | Marks for removal; actual removal happens after the loop in reverse order to avoid index shifting. |

**Validation on "Next →"**: At least one control type with a non-empty `.strip()` name is required. Invalid (empty-name) entries are filtered out before storing.

### 2.4 Step 3: Business Units

**What the user sees**: A dynamic list of business unit entries. This step is **explicitly optional** — the user can proceed with zero BUs.

**Button: "➕ Add Business Unit"**
- Appends a blank entry with auto-generated ID `"BU-{n:03d}"` where n is the next sequential number.

**Each BU entry** is rendered in an `st.expander`:

| Widget | Key | Details |
|---|---|---|
| `st.text_input("ID")` | `wiz_bu_id_{i}` | Pre-filled as "BU-001", "BU-002", etc. Editable. |
| `st.text_input("Name")` | `wiz_bu_name_{i}` | e.g., "Retail Banking" |
| `st.text_area("Description", height=60)` | `wiz_bu_desc_{i}` | Role of this BU |
| `st.multiselect("Primary Sections")` OR `st.text_input("Primary Sections (comma-separated)")` | `wiz_bu_sec_{i}` or `wiz_bu_sec_txt_{i}` | **Conditional**: if process areas have been defined (in `form["process_areas"]`), shows a multiselect of their IDs. Otherwise shows a free-text comma-separated input. This handles the ordering issue — BUs are defined in Step 3 before Process Areas in Step 4. Users can come back and refine. |
| `st.multiselect("Key Control Types")` | `wiz_bu_types_{i}` | Options: control type names from Step 2 |
| `st.text_input("Regulatory Exposure (comma-separated)")` | `wiz_bu_reg_{i}` | Parsed into `list[str]`. E.g., "SOX, OCC, BSA/AML" |
| `st.button("🗑 Remove")` | `wiz_bu_rm_{i}` | |

**No validation on "Next →"** — zero BUs is valid.

### 2.5 Step 4: Process Areas

This is **the most complex step** in the wizard, with 5 sub-sections per process area and AI auto-fill capability.

**Button: "➕ Add Process Area"**
- Appends a blank entry with auto-generated ID `"{n}.0"` (e.g., "1.0", "2.0"), empty risk profile (all defaults of 3/3/3/1.0), empty affinity, empty registry, and empty exemplars list.

**Each process area** is rendered in an `st.expander` titled "Section {id}: {name or '(unnamed)'}".

#### Sub-section 4a: Basic Fields (3 columns)

| Widget | Key | Details |
|---|---|---|
| `st.text_input("ID")` | `wiz_pa_id_{i}` | e.g., "1.0" |
| `st.text_input("Name")` | `wiz_pa_name_{i}` | e.g., "Lending Operations" |
| `st.text_input("Domain")` | `wiz_pa_domain_{i}` | Auto-generated as snake_case of Name: `re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")`. E.g., "Lending Operations" → "lending_operations". User can override. |

#### Sub-section 4b: AI Auto-Fill

**Button: "🤖 Auto-fill with AI"** (one per section)
- Requires the section name to be non-empty; otherwise shows `st.warning("Enter a section name first.")`.
- Calls `_run_section_autofill(section_name, type_names, config_context)` which:
  1. Creates a transport client and `ConfigProposerAgent`.
  2. Calls `agent.execute(mode="section_autofill", section_name="...", control_type_names=[...], config_context={"name": ..., "description": ...})`.
  3. The LLM receives `SYSTEM_PROMPT_SECTION` which asks it to propose `risk_profile`, `affinity`, `registry`, and `exemplars` for this specific process area, constrained to only use control type names from the provided list.
  4. Returns a dict with those keys.
- Merges only the keys the LLM returned (`risk_profile`, `affinity`, `registry`, `exemplars`) into the section's form data.
- If the LLM is not configured, deterministic fallback: risk profile all 3s with multiplier 1.0, affinity split evenly into HIGH/MEDIUM/LOW thirds, registry with generic `"{Name} Manager"` and `"{Name} Analyst"` roles, empty exemplars.

#### Sub-section 4c: Risk Profile (4 columns + text area)

| Widget | Key | Default | Details |
|---|---|---|---|
| `st.slider("Inherent Risk", 1, 5)` | `wiz_rp_ir_{i}` | 3 | Probability and magnitude of risk in this area |
| `st.slider("Regulatory Intensity", 1, 5)` | `wiz_rp_ri_{i}` | 3 | How heavily regulated this area is |
| `st.slider("Control Density", 1, 5)` | `wiz_rp_cd_{i}` | 3 | How control-intensive the process is |
| `st.number_input("Multiplier", 0.1-5.0, step=0.1)` | `wiz_rp_mul_{i}` | 1.0 | The **critical number** — directly controls how many generated controls this section receives relative to other sections. Higher multiplier = more controls. The banking_standard's "Financial Management" section uses 3.2; the "Vision and Strategy" section uses 1.8. |
| `st.text_area("Rationale", height=60)` | `wiz_rp_rat_{i}` | "" | Explains why these risk scores were assigned. Used for documentation/audit trail. |

#### Sub-section 4d: Affinity Grid

Rendered **only if** control types have been defined in Step 2. Shows a header "**Affinity Grid**" with a caption explaining the concept.

For each control type name, renders a `st.selectbox` with options `["HIGH", "MEDIUM", "LOW", "NONE"]`. These are arranged in columns (up to 3 per row).

The code maintains a reverse lookup `current_assignment: dict[str, str]` (type name → affinity level) computed from the current `pa["affinity"]` dict. This ensures that revisiting the step shows the correct current assignments.

Output: `pa["affinity"]` is rebuilt as `{"HIGH": [...], "MEDIUM": [...], "LOW": [...], "NONE": [...]}` from all the selectbox values.

**What this means for generation**: Control types in HIGH affinity are strongly preferred for this section during assignment. The `build_assignment_matrix()` function uses affinity data indirectly through the round-robin allocation that distributes types across sections.

#### Sub-section 4e: Domain Registry (2-column layout)

Six text areas, each accepting one item per line:

| Field | Key | What It Feeds |
|---|---|---|
| **Roles** | `wiz_reg_{i}_roles` | Spec agent's `who` field — the person performing the control |
| **Systems** | `wiz_reg_{i}_systems` | Spec agent's `where_system` field — where the control executes |
| **Data Objects** | `wiz_reg_{i}_data_objects` | Contextual grounding for control descriptions |
| **Evidence Artifacts** | `wiz_reg_{i}_evidence_artifacts` | Spec agent's `evidence` field — audit-grade documentation |
| **Event Triggers** | `wiz_reg_{i}_event_triggers` | Spec agent's `when` field — timing/frequency trigger text |
| **Regulatory Frameworks** | `wiz_reg_{i}_regulatory_frameworks` | Regulatory context for LLM prompts, and `regulatory_lookup` tool |

The registry is the **most important domain knowledge** for generation quality. With rich registries (8+ roles, 5+ systems, 5+ triggers, 5+ evidence artifacts), the deterministic builder and LLM both produce highly specific, realistic controls. With empty registries, output becomes generic.

For reference, the banking_standard's section_1.yaml ("Vision and Strategy") registry includes:
- 9 roles: CEO, COO, CFO, CRO, Chief Strategy Officer, Head of Corporate Development, Strategic Planning Analyst, Board of Directors, Board Committee Chairs
- 3 systems: Enterprise Performance Management Platform, Board Portal and Governance Platform, Strategic Planning and Forecasting Tool
- 5 data objects: strategic plan documents, risk appetite statements, board meeting minutes, capital allocation plans, enterprise performance scorecards
- 4 evidence artifacts: board-approved strategic plan with sign-off, risk appetite framework approval documentation, capital plan review log, strategic initiative prioritization matrix
- 5 event triggers: at each annual strategic planning cycle, at each quarterly board meeting, on material change to risk appetite, on M&A decision, at each capital planning cycle
- 5 regulatory frameworks: OCC Heightened Standards, Regulation YY, CCAR/DFAST, SEC Corporate Governance, Federal Reserve SR Letters

#### Sub-section 4f: Exemplars

**Button: "➕ Add Exemplar"** — Adds a blank exemplar entry pre-filled with the first control type, first placement, first method.

Each exemplar entry:

| Widget | Key | Details |
|---|---|---|
| `st.selectbox("Control Type")` | `wiz_ex_ct_{i}_{ei}` | Dropdown from Step 2 types |
| `st.selectbox("Placement")` | `wiz_ex_pl_{i}_{ei}` | Preventive / Detective / Contingency Planning |
| `st.selectbox("Method")` | `wiz_ex_mt_{i}_{ei}` | Automated / Manual / Automated with Manual Component |
| `st.text_area("Narrative (30-80 words)", height=80)` | `wiz_ex_desc_{i}_{ei}` | The sample control description. A caption below shows `"Word count: {wc}"` live. |
| `st.selectbox("Quality Rating")` | `wiz_ex_qr_{i}_{ei}` | Strong / Effective / Satisfactory / Needs Improvement |
| `st.button("🗑 Remove Exemplar")` | `wiz_ex_rm_{i}_{ei}` | |

Exemplars serve as **few-shot examples** for the LLM. When the NarrativeAgent generates prose for a section, exemplars from that section are included in its prompt (either inline in fat-prompt mode or via the `exemplar_lookup` tool in slim mode). Well-written exemplars dramatically improve output quality.

The banking_standard's section_1.yaml ships with a detailed exemplar:
> "Prior to execution of any strategic initiative requiring capital expenditure exceeding the materiality threshold, the Chief Strategy Officer presents the initiative business case, risk assessment, and projected ROI to the Board Risk Committee for review and formal approval, ensuring alignment with the board-approved risk appetite statement and strategic plan."

### 2.6 Step 5: Narrative & Quality Settings

This step has **sensible defaults pre-filled** — most users will not need to modify anything. It configures the output format and quality standards.

**Narrative Fields**: 6 rows showing the 5W framework fields. Each row has two inputs:
- **Field Name** (`st.text_input`) — e.g., "who", "what", "when", "where", "why", "full_description"
- **Definition** (`st.text_input`) — e.g., "The specific role responsible for performing the control"

These field definitions are embedded into the NarrativeAgent's system prompt and used to teach the LLM what each output key means.

**Word Count** (2 columns):
- **Min Word Count** (`st.number_input`, range 1-500, default 30) — Minimum words for `full_description`.
- **Max Word Count** (`st.number_input`, range 1-500, default 80) — Maximum words.
- These are enforced by the validator's `WORD_COUNT_OUT_OF_RANGE` rule and communicated to the LLM in prompts.

**Quality Ratings** (`st.text_area`, one per line):
- Default: "Strong", "Effective", "Satisfactory", "Needs Improvement"
- Used by the EnricherAgent when assigning a quality rating to each control.
- The labels are embedded in the enricher system prompt: `"assign one quality rating from: Strong, Effective, Satisfactory, Needs Improvement"`.

**Placements** (`st.text_area`, one per line):
- Default: "Preventive", "Detective", "Contingency Planning"
- These define the allowed placement categories for the taxonomy.
- Parsed into `[{"name": n.strip(), "description": ""} for n in lines]`.

**Methods** (`st.text_area`, one per line):
- Default: "Automated", "Manual", "Automated with Manual Component"
- Defines the allowed control execution methods.

**Frequency Tiers** (`st.text_area`, one per line, ranked top = most frequent):
- Default: "Daily", "Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual"
- Each tier is stored with a rank (position in list) and keywords. If a label matches an existing tier from the defaults, its keywords are preserved. New labels get `[label.lower()]` as keywords.
- Keywords power the `_derive_frequency()` function which parses the `when` text to auto-assign a frequency label.

### 2.7 Step 6: Review & Export

**Validation**: The form dict is passed to `DomainConfig(**form)`. Pydantic validates the schema and runs cross-reference checking. If validation fails, the user sees:
- A red `st.error()` box with the full error message (e.g., "DomainConfig cross-reference errors: BU 'BU-001' references unknown section: '3.0'")
- A blue `st.info("Go back to the relevant step and fix the issues listed above.")`
- A "← Back to Edit" button

**If validation passes**, the user sees:
- A green `st.success()` banner: "**community-bank-demo** is valid! 3 types, 2 BUs, 2 sections."
- A **config preview** (rendered by `render_config_preview()` from `config_input.py`) showing:
  - 3 metric cards: Control Types count, Business Units count, Process Areas count
  - An expandable "Config Details" section with three DataFrames:
    - Control Types table: Name, Code, Min Frequency
    - Business Units table: ID, Name, Key Types (first 3)
    - Process Areas table: ID, Name, Risk Multiplier

**Three action buttons** in 3 columns:

| Button | Key | What It Does |
|---|---|---|
| **"Download as YAML"** | `wiz_download` | `st.download_button` that exports the form dict as YAML via `yaml.dump()`. File name: `{config.name}.yaml`. |
| **"Use this config"** | `wiz_use` | Stores the config in `st.session_state["wizard_active_config"]` and `st.session_state["wizard_built_config"]`, shows a success message, and returns the `DomainConfig` object to the parent `render_config_input()`. This activates the rest of the Modular tab. |
| **"Save to profiles"** | `wiz_save` | Writes the YAML to `config/profiles/{config.name}.yaml` so it appears in the Select Profile dropdown on next load. Creates the directory if needed. |

---

## 3. Backend Flow — What Happens After Config Activation

### 3.1 The Modular Tab: Generation Settings

Once a `DomainConfig` is activated (from any of the three sub-tabs), the rest of `render_modular_tab()` renders:

**Config path resolution**: If the config came from Select Profile, its file path is used directly. If it came from Build from Form or Import from Excel, the config is serialized to a temp file (`/tmp/controlforge_{name}.yaml`) because the LangGraph nodes expect to load from a file path.

**Number of controls** (`st.number_input`): Range 1-500, default 10. This is the `target_count` passed to `init_node`.

**Enable LLM Generation** (`st.toggle`): Default off. When enabled:
- Checks `build_client_from_env()` for configured API keys.
- If no keys found, shows a warning but still allows proceeding (will fall back to deterministic).
- When LLM is enabled, the graph uses three specialized agents (SpecAgent, NarrativeAgent, EnricherAgent) with tool calling.
- When disabled, the graph uses template-based deterministic builders that produce output instantly with no API calls.

**Customize Distribution** (`st.expander`, collapsed by default):

*Control Type Weight Sliders*: One `st.slider` per control type. Range 0.0-10.0, default 1.0, step 0.5. These are **relative weights**, not absolute counts:

```
controls_for_type_X = (weight_X / sum_of_all_weights) × target_count
```

Practical example with 3 types (Authorization, Reconciliation, Exception Reporting) and target 10:
- All at 1.0 → ~3, ~4, ~3 (even split with remainder)
- Authorization at 5.0, others at 1.0 → ~7, ~1-2, ~1-2
- Exception Reporting at 0.0 → 0 controls of that type

*Section Emphasis Sliders*: One `st.slider` per process area. Range 0.0-10.0, step 0.5. **Default is NOT 1.0** — it's the section's `risk_profile.multiplier` from the config. This means the defaults already encode domain knowledge: Settlement & Clearing (2.4) gets more controls than Lending (1.8).

If any slider value differs from the default (1.0 for types, multiplier for sections), a `distribution_config` dict is passed to the graph. Otherwise `None` (use defaults).

### 3.2 Assignment Matrix Builder

The function `build_assignment_matrix()` in `graphs/forge_modular_helpers.py` takes the `DomainConfig`, `target_count`, and optional `distribution_config`, and produces a list of assignment dicts:

```python
[
    {
        "section_id": "2.0",
        "section_name": "Settlement and Clearing",
        "domain": "settlement_and_clearing",
        "control_type": "Reconciliation",
        "business_unit_id": "BU-002",
        "business_unit_name": "Operations",
        "leaf_name": "Settlement and Clearing – Reconciliation",
        "hierarchy_id": "2.0.1.1",
    },
    # ... one per control to generate
]
```

**The allocation algorithm**:

1. **Type distribution**: `_distribute_by_weight(type_names, target_count, type_weights)` — splits the target count across types proportionally to weights. Uses floor-and-remainder method to handle rounding (largest fractional parts get the extra controls).

2. **Section distribution**: `_distribute_by_weight(section_ids, target_count, section_weights)` — same logic but for sections. Default weights come from `risk_profile.multiplier`.

3. **BU assignment**: For each section, builds a `itertools.cycle` of business units whose `primary_sections` include that section. If no BU explicitly claims a section, cycles through all BUs.

4. **Round-robin allocation**: Cycles through sections and types, checking `section_remaining[s] > 0` and `type_remaining[t] > 0`, allocating one control at a time. Safety cap of `max(target * 10, sections * types * 2)` iterations prevents infinite loops.

5. **No-sections fallback**: If the config has zero process areas, all controls are assigned to a synthetic "General" section (ID "0.0").

### 3.3 The 8-Node LangGraph StateGraph

Implemented in `graphs/forge_modular_graph.py`. The `ForgeState` TypedDict carries all data between nodes:

```
init → select → spec → narrative → validate
    → [enrich | narrative (retry, up to 3x)]
    → merge → [select (loop) | finalize] → END
```

**Node 1: `init_node`**
- Loads the `DomainConfig` from the YAML file path.
- Calls `build_assignment_matrix()` with target count and distribution config.
- Detects the LLM provider by inspecting the transport client's `.provider` attribute ("ica", "openai", "anthropic", or "none").
- Detects whether ICA XML tool-call simulation is enabled (`client.ica_tool_calling`).
- Emits `PIPELINE_STARTED` event.
- Returns: `domain_config` (as dict), `llm_enabled`, `provider`, `ica_tool_calling`, `assignments`, `current_idx=0`, empty `generated_records` and `tool_calls_log`.

**Node 2: `select_node`**
- Reads `assignments[current_idx]`.
- Emits `CONTROL_STARTED` with index and total count.
- Returns: `current_assignment`, `retry_count=0`, `validation_passed=False`.

**Node 3: `spec_node`**
- If `llm_enabled` is False: calls `build_deterministic_spec()` and returns immediately.
- If LLM enabled: constructs system and user prompts using the dual-mode architecture (see Section 3.4), calls the SpecAgent via `call_llm_with_tools()` or `call_llm_with_xml_tools()`, parses the JSON result.
- On any exception: falls back to `build_deterministic_spec()` and emits `AGENT_FAILED`.
- Returns: `current_spec`, `tool_calls_log` (accumulated tool call telemetry).

**Node 4: `narrative_node`**
- Same dual-mode prompt architecture as spec.
- Injects `retry_appendix` from previous validation failures (if retrying).
- Tools: `frequency_lookup`, `regulatory_lookup`, `exemplar_lookup` (slim mode) or just `frequency_lookup`, `regulatory_lookup` (fat mode).
- Fallback: `build_deterministic_narrative()`.

**Node 5: `validate_node`**
- If `llm_enabled` is False: returns `validation_passed=True` (deterministic output is trusted).
- If LLM enabled: calls `validate(narrative, spec, min_words=..., max_words=...)` which runs 6 rules.
- On pass: returns `validation_passed=True`.
- On fail with retries < 3: calls `build_retry_appendix()` to generate fix instructions, returns `validation_passed=False`, `retry_count+=1`, routes back to `narrative_node`.
- On fail with retries >= 3: accepts as-is, returns `validation_passed=True` with `accepted_with_failures=True`.

**Node 6: `enrich_node`**
- Calls `build_deterministic_enriched()` to merge spec + narrative into a full record.
- If LLM enabled: additionally calls the EnricherAgent which may refine `full_description` and assign `quality_rating`.
- LLM quality rating overrides the default "Effective" if provided.

**Node 7: `merge_node`**
- Appends the enriched record to `generated_records` (using LangGraph's reducer annotation `Annotated[list, _add]`).
- Increments `current_idx`.
- Emits `CONTROL_COMPLETED`.

**Node 8: `finalize_node`**
- Calls `assign_control_ids()` on all records.
- Builds the final `plan_payload` dict with `config_name`, `total_controls`, `control_types_used`, `final_records`.
- Emits `PIPELINE_COMPLETED`.

**Routing edges:**
- `after_init`: if no assignments → skip to `finalize`; else → `select`
- `after_validate`: if passed → `enrich`; if failed → `narrative` (retry)
- `has_more`: if `current_idx < len(assignments)` → `select` (loop); else → `finalize`

### 3.4 Dual-Mode Prompt Architecture

The system uses two fundamentally different prompting strategies depending on the LLM provider:

**Fat-prompt mode (ICA/Granite or plain mode)**:
- System prompt includes all domain data inline: placements, methods, evidence rules, registry.
- User prompt includes the complete assignment context with taxonomy constraints, diversity context, etc.
- Tools are offered as optional hints (`_TOOL_HINT`: "Use them when helpful").
- Token usage: ~4-5 KB per prompt.

**Slim-prompt mode (OpenAI/Anthropic)**:
- System prompt contains only the output schema and instructions to call tools.
- User prompt contains only the minimal assignment info (leaf, control type, BU suggestion).
- Tools are **required** (`tool_choice="required"` on first round, then `"auto"`), forcing the LLM to call `placement_lookup`, `method_lookup`, `evidence_rules_lookup`, etc. before generating its answer.
- After the first round of tool calls, `tool_choice` relaxes to `"auto"` so the LLM can produce the final content response.
- Token reduction: ~55-60% compared to fat prompts.

**ICA XML mode** (hybrid):
- Uses slim-prompt content but without the `tools` API parameter.
- Instead, appends `build_xml_tool_instructions()` to the system prompt, teaching the LLM to emit `<tool_call>` XML blocks.
- The `call_llm_with_xml_tools()` method parses XML tool calls from the text response, executes them, formats results as `<tool_result>` XML, and re-sends.
- Max 5 tool-call rounds.

### 3.5 Tool Calling — 9 Domain-Aware Tools

All tools are implemented in `tools/domain_tools.py` and dispatched by `build_domain_tool_executor(config)`, which returns a `(name, args) -> dict` closure. Every tool reads from the active `DomainConfig`.

| Tool | Schema Module | Arguments | Returns | Used By |
|---|---|---|---|---|
| `taxonomy_validator` | `TAXONOMY_VALIDATOR_SCHEMA` | `level_1`, `level_2` | `{valid, suggestion}` — validates placement × control type | SpecAgent, EnricherAgent |
| `hierarchy_search` | `HIERARCHY_SEARCH_SCHEMA` | `section_id`, `keyword` | Registry roles, systems, evidence filtered by keyword | SpecAgent |
| `regulatory_lookup` | `REGULATORY_LOOKUP_SCHEMA` | `framework`, `section_id` | Matching frameworks, applicable types, domain | SpecAgent, NarrativeAgent |
| `frequency_lookup` | `FREQUENCY_LOOKUP_SCHEMA` | `control_type`, `trigger` | Derived + expected frequency, reasoning | NarrativeAgent, EnricherAgent |
| `placement_lookup` | `PLACEMENT_LOOKUP_SCHEMA` | `control_type` | Allowed placements with `allowed_for_type` flag | SpecAgent (slim) |
| `method_lookup` | `METHOD_LOOKUP_SCHEMA` | (none) | All methods with descriptions | SpecAgent (slim) |
| `evidence_rules_lookup` | `EVIDENCE_RULES_LOOKUP_SCHEMA` | `control_type` | Evidence quality criteria from config | SpecAgent (slim) |
| `exemplar_lookup` | `EXEMPLAR_LOOKUP_SCHEMA` | `section_id` | Exemplar narratives for the section | NarrativeAgent (slim) |
| `memory_retrieval` | `MEMORY_RETRIEVAL_SCHEMA` | `query_text`, `section_id?`, `n?` | Similar controls from ChromaDB | EnricherAgent (**not wired**) |

Tool calls are wrapped by `_emitting_tool_executor()` which emits `TOOL_CALLED` and `TOOL_COMPLETED` events with timing data and logs each call to `tool_calls_log` for the UI summary.

### 3.6 Deterministic Fallback Builders

Three functions in `graphs/forge_modular_helpers.py` that produce output without any LLM calls:

**`build_deterministic_spec(assignment, config)`**:
- Selects `who`, `where_system`, `when`, `evidence` from the section's registry using modular indexing: `idx = hash(f"{section_id}-{ct_name}") % len(roles)`. This is deterministic (same input → same output) but provides variety across assignments.
- Determines `placement` from the control type's `placement_categories[0]`.
- Picks `method`: "Automated" for Preventive, "Manual" for others.
- Constructs `what_action` as `"performs {type.lower()} control activities"`.
- Sets `why_risk` to `"to mitigate risk of control failures in {section_name}"`.

**`build_deterministic_narrative(spec, config)`**:
- Composes a `full_description` from a template:
  ```
  "{when}, the {who} {what_action} within the {where_system} {why_risk},
  with results documented via {evidence}."
  ```
- Derives `frequency` by matching the `when` text against `config.frequency_tiers` keywords using `_derive_frequency()`.

**`build_deterministic_enriched(spec, narrative, config)`**:
- Merges all fields from spec and narrative into a single record dict with 22 keys.
- Assigns `quality_rating` = `DEFAULT_QUALITY_RATING` ("Effective").
- Sets `validator_passed=True`, `validator_retries=0`, `validator_failures=[]`.

### 3.7 The 6-Rule Validator

Implemented in `validation/validator.py`. Pure Python, no LLM. Returns a `ValidationResult(passed: bool, failures: list[str], word_count: int)`.

| Rule | Code | What It Checks | How It Checks |
|---|---|---|---|
| 1 | `MULTIPLE_WHATS` | >2 distinct action verbs in `what` | Uses a curated list of ~50 control-domain verb roots (`_ACTION_VERB_ROOTS`: perform, review, validat, reconcil, authoriz, monitor, verif, approv...). Matches with regex `\b(?:root1|root2|...)[a-z]*\b`. Filters out noun forms (words ending in -tion, -ment, -ance, etc.). Counts unique root matches. |
| 2 | `VAGUE_WHEN` | `when` contains vague temporal terms | Checks for: "periodic", "ad hoc", "as needed", "various", "as required", "on occasion" |
| 3 | `WHO_EQUALS_WHERE` | `who` and `where` are substrings of each other | `who_lower in where_lower or where_lower in who_lower` |
| 4 | `WHY_MISSING_RISK` | `why` lacks risk-related words | Checks for 16 markers: risk, prevent, mitigate, reduce, ensure, compliance, violation, failure, loss, exposure, threat, safeguard, protect, detect, deter, avoid |
| 5 | `WORD_COUNT_OUT_OF_RANGE` | `full_description` outside word limits | `len(full_desc.split())` compared to config's `word_count_min` and `word_count_max` |
| 6 | `SPEC_MISMATCH` | `who` or `where` differs from locked spec | Compares `narrative["who"]` to `spec["who"]` and `narrative["where"]` to `spec["where_system"]`. Deduplicated (counts as one failure even if both mismatch). |

**`build_retry_appendix()`**: When validation fails, generates a targeted instruction string for the NarrativeAgent's next attempt, e.g.:
```
--- RETRY ATTEMPT 2/3 ---
Your previous attempt had these validation failures: VAGUE_WHEN, WORD_COUNT_OUT_OF_RANGE
- VAGUE_WHEN: Your 'when' field contained a vague term. Replace with a specific frequency.
- WORD_COUNT_OUT_OF_RANGE: Your full_description had 25 words. Target: 30-80 words.
Fix all issues while preserving the locked spec constraints.
```

### 3.8 Control ID Assignment

`assign_control_ids()` in `forge_modular_helpers.py`:
- Iterates over all records.
- Looks up the 3-letter type code from `config.type_code_map()`.
- Maintains per-type-code sequential counters.
- Builds IDs in format: `CTRL-{L1:02d}{L2:02d}-{TYPE}-{SEQ:03d}`
  - L1, L2 extracted from `hierarchy_id` (e.g., "2.0" → L1=2, L2=0)
  - Example: `CTRL-0200-REC-001` (first Reconciliation control in section 2.0)

### 3.9 Real-Time Event Streaming

The pipeline uses `EventEmitter` (from `core/events.py`) to emit `PipelineEvent` objects. The Modular tab creates a `StreamlitEventListener` that maps events to `st.status()` updates:

| Event | Icon | Display |
|---|---|---|
| `PIPELINE_STARTED` | 🚀 | "Pipeline started: community-bank-demo, target=10" |
| `CONTROL_STARTED` | 📋 | "Control 3/10: Reconciliation in 2.0" |
| `AGENT_STARTED` | ⏳ | "SpecAgent started" |
| `AGENT_COMPLETED` | ✓ | "SpecAgent (1.2s, 3 tool calls)" |
| `AGENT_FAILED` | ✗ | "SpecAgent failed (0.8s) — deterministic fallback" |
| `VALIDATION_PASSED` | ✓ | "Validation passed" |
| `VALIDATION_FAILED` | ✗ | "Validation failed (retry 1/3): ['VAGUE_WHEN']" |
| `AGENT_RETRY` | ⟳ | "NarrativeAgent retry 1/3" |
| `TOOL_CALLED` | 🔧 | "taxonomy_validator({'level_1': 'Preventive', 'level_2': 'Authorization'})" |
| `CONTROL_COMPLETED` | ✔️ | "Control 3 completed — Effective" |
| `PIPELINE_COMPLETED` | ✅ | "Generated 10 controls for community-bank-demo" |

---

## 4. The Agent System

### 4.1 BaseAgent and the Agent Registry

`BaseAgent` in `agents/base.py` is the abstract base class for all agents. Key features:

- **`@register_agent` decorator**: Registers the agent class in `AGENT_REGISTRY: dict[str, type[BaseAgent]]`. The graph's `_get_agent()` helper instantiates agents from this registry.
- **`AgentContext` dataclass**: Shared runtime context holding `client`, `model`, `temperature`, `max_tokens`, `timeout_seconds`.
- **Token tracking**: `total_input_tokens`, `total_output_tokens` accumulated across calls.
- **`call_llm(system_prompt, user_prompt)`**: Simple single-turn LLM call, returns text.
- **`call_llm_with_tools(messages, tools, tool_executor, ...)`**: Multi-turn tool-calling loop. Sends messages with `tools` parameter, executes any `tool_calls` in the response via `tool_executor`, appends tool results as `role: "tool"` messages, re-sends. Up to `max_tool_rounds=5` iterations. After the first round with `tool_choice="required"`, relaxes to `"auto"`.
- **`call_llm_with_xml_tools(messages, tool_executor, ...)`**: XML-based tool simulation for providers that don't support native function calling. Parses `<tool_call>` XML from text, executes tools, formats results as `<tool_result>` XML, re-sends.
- **`parse_json(text)`**: Robust JSON extraction from LLM output. Tries: raw parse → strip markdown fences → extract first ```json``` block → find first top-level `{...}` in text.

### 4.2 ConfigProposerAgent (Wizard AI)

Used by Build from Form for two AI-assist features:

**Mode: `enrich`** (Step 2 — "Auto-fill Definitions with AI"):
- Input: list of control type names.
- System prompt: `SYSTEM_PROMPT_ENRICH` — "propose definitions, 3-letter codes, evidence criteria, min frequency tiers, and placement categories".
- Output schema: `{"control_types": [{"name": "...", "definition": "...", "code": "...", "min_frequency_tier": "...", "placement_categories": [...], "evidence_criteria": [...]}]}`.
- Deterministic fallback: `_build_deterministic_enrichment()` — generic definitions, auto-codes from consonants, `["Detective"]` placement.

**Mode: `section_autofill`** (Step 4 — "Auto-fill with AI" per section):
- Input: section name, control type names, config context (name + description).
- System prompt: `SYSTEM_PROMPT_SECTION` — "propose registry, affinity, risk profile, and exemplar".
- Output schema: `{"risk_profile": {...}, "affinity": {...}, "registry": {...}, "exemplars": [...]}`.
- Constraint: "Only use control type names that appear in the provided control_types list."
- Deterministic fallback: `_build_deterministic_section()` — split types into thirds for HIGH/MEDIUM/LOW, generic roles.

**Mode: `full`** (Excel Import tab):
- Input: `RegisterSummary` dict.
- System prompt: `SYSTEM_PROMPT_FULL` — "analyze register summary and propose complete DomainConfig".
- Has a retry mechanism: if the first LLM output fails `DomainConfig` validation, sends a retry prompt with the error message. If retry also fails, falls back to `_build_deterministic_config()`.

### 4.3 SpecAgent, NarrativeAgent, EnricherAgent (Generation Agents)

These agents exist in two forms:

1. **Legacy standalone agents** (`agents/spec.py`, `agents/narrative.py`, `agents/enricher.py`) — used by the original ControlForge orchestrator with fat prompts and direct `execute()` calls.

2. **Modular graph integration** — the modular graph doesn't use the standalone agents' `execute()` methods. Instead, it uses `_get_agent("SpecAgent")` to get a `BaseAgent` instance and calls `call_llm_with_tools()` or `call_llm_with_xml_tools()` directly with config-aware prompts built by the helper functions (`build_spec_system_prompt()`, `build_slim_spec_user_prompt()`, etc.). This allows the modular graph to use the dual-mode prompt architecture.

### 4.4 AdversarialReviewer and DifferentiationAgent (Unused in Wizard)

**`AdversarialReviewer`** (`agents/adversarial.py`):
- Prompts: "You are a senior internal audit reviewer. Critically evaluate a generated control and identify weaknesses."
- Returns: `{"weaknesses": [{"issue": "...", "suggestion": "..."}], "overall_assessment": "Weak|Needs Improvement|Satisfactory", "rewrite_guidance": "..."}`
- **Currently not wired into the modular graph.** Exists as infrastructure for future adversarial review passes.

**`DifferentiationAgent`** (`agents/differentiator.py`):
- Prompts: "A generated control has been flagged as too similar to an existing one. Rewrite to be semantically distinct while preserving who/where/type/risk."
- **Currently not wired.** Designed to work with the ChromaDB memory store's `check_duplicate()` method.

---

## 5. Data Assets — YAML Configs the System Ships With

### 5.1 Profile Configs

| File | Scale | Details |
|---|---|---|
| `config/profiles/community_bank_demo.yaml` | 3 types, 2 BUs, 2 process areas | Minimal but complete. Authorization (Preventive, min Quarterly), Reconciliation (Detective, min Monthly), Exception Reporting (Detective, min Monthly). BUs: Retail Banking, Operations. Sections: Lending Operations (multiplier 1.8), Settlement and Clearing (multiplier 2.4). Rich registries with 3+ roles, 2+ systems, 2+ triggers, 2+ evidence artifacts each. |
| `config/profiles/banking_standard.yaml` | 25 types, 17 BUs, 13 process areas | Full banking profile equivalent to the legacy system. 25 control types from Reconciliation to Third Party Due Diligence, each with expert definitions, 3-letter codes, and placement categories. 17 BUs from Retail Banking to Legal & Compliance. 13 process areas covering the full APQC banking framework. |

### 5.2 Section YAMLs

`config/sections/section_1.yaml` through `section_13.yaml` — 13 files providing **deep domain knowledge** per process area. Each contains:

- `section_id` and `domain` name
- `risk_profile` with detailed rationale (multi-sentence)
- Full `affinity` grid mapping all 25 control types to HIGH/MEDIUM/LOW/NONE
- `registry` with 5-15 items per field (roles, systems, data objects, evidence artifacts, event triggers, regulatory frameworks)
- At least 1 `exemplar` narrative (50+ word prose with quality rating)

These section YAMLs represent the **richest data assets** in the repo. They encode deep banking domain expertise that took significant effort to curate. They are used by the legacy orchestrator but **not yet directly importable into the Build from Form wizard**.

Example from section_1.yaml (Vision and Strategy):
- **Roles**: CEO, COO, CFO, CRO, Chief Strategy Officer, Head of Corporate Development, Strategic Planning Analyst, Board of Directors, Board Committee Chairs
- **Regulatory Frameworks**: OCC Heightened Standards (Governance), Regulation YY (Enhanced Prudential Standards), CCAR/DFAST Capital Planning, SEC Corporate Governance Requirements, Federal Reserve SR Letters (Board Effectiveness)
- **Exemplar**: A 50-word Authorization/Preventive control about the Chief Strategy Officer presenting initiative business cases to the Board Risk Committee.

### 5.3 Legacy Config Files

| File | Content | Relationship to DomainConfig |
|---|---|---|
| `config/taxonomy.yaml` | 25 control type definitions + 17 BU definitions | Superseded by `DomainConfig.control_types` and `.business_units` |
| `config/standards.yaml` | 5W definitions, phrase bank (action verbs, timing phrases), quality ratings | Partially superseded by `DomainConfig.narrative` and `.quality_ratings`. The phrase bank is not in DomainConfig. |
| `config/placement_methods.yaml` | Placements, methods, and `level_2_by_level_1` taxonomy mapping | Superseded by `DomainConfig.placements`, `.methods`, and `.control_types[].placement_categories` |

---

## 6. Infrastructure Already Built but Not Yet Wired

### 6.1 ChromaDB Memory Store

**Module**: `memory/store.py` (ControlMemory class), `memory/embedder.py` (SentenceTransformerEmbedder).

**What it does**:
- Uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim) for embedding control descriptions.
- Stores controls in ChromaDB collections named `controls_{bank_id}` with cosine similarity.
- **`index_controls(bank_id, records, run_id)`**: Upserts control full_descriptions with metadata (section_id, control_type, business_unit_id, run_id, hierarchy_id).
- **`query_similar(bank_id, text, n=5, section_filter=None)`**: Returns top-N similar controls with cosine similarity scores.
- **`check_duplicate(bank_id, text, threshold=0.92)`**: Returns `(is_duplicate, existing_control_id)` if any existing control has ≥92% similarity.
- **`compare_runs(bank_id, run_id_a, run_id_b)`**: Counts controls per run and measures overlap.

**Current state**: The `memory_retrieval` tool schema exists, and `dc_memory_retrieval()` is in the tool executor dispatch table, but `memory=None` is always passed (no `ControlMemory` instance is created or injected).

### 6.2 Register Analyzer (Excel Import)

**Module**: `analysis/register_analyzer.py`.

**What it does**: Parses any Excel control register using flexible header matching. The `HEADER_SYNONYMS` dict maps canonical field names to 8-12 known header variations each (e.g., `"control_type"` matches "control_type", "control type", "selected_level_2", "type", "type of control", "control category", etc.).

**Output**: A `RegisterSummary` Pydantic model with: `row_count`, `unique_control_types[]`, `unique_business_units[]`, `unique_sections[]`, `unique_placements[]`, `unique_methods[]`, `frequency_values[]`, `role_mentions`, `system_mentions`, `regulatory_mentions`, `header_mapping{}`, `sample_descriptions[]`.

### 6.3 Analysis Tab and Gap Scanners

**Module**: `analysis/scanners.py`, `analysis/pipeline.py`.

The Analysis tab supports uploading existing controls, running gap analysis scanners, and displaying a gap dashboard. This is a separate flow from Build from Form but shares the same taxonomy and standards data. The gap report could be used to inform config building.

### 6.4 Remediation Graph and Planner

**Module**: `graphs/remediation_graph.py`, `remediation/planner.py`, `remediation/paths.py`.

A LangGraph StateGraph for generating remediation controls to fill identified gaps. Currently exists as infrastructure but the modular graph doesn't connect to it.

---

## 7. Frontend Improvements — Detailed Proposals

### 7.1 Template Library and Starter Configs

**What**: Add a "Start from Template" button/selector at the beginning of the wizard (Step 1 or a new Step 0) that pre-populates the entire form from an industry template.

**Why**: Building a config from scratch is the slowest path. The system already has two detailed profiles (`community_bank_demo.yaml`, `banking_standard.yaml`). Users should be able to start from one and customize rather than build from zero.

**Implementation sketch**:
- Add a dropdown in Step 1: "Start from template: (blank) | Community Bank | Full Banking Standard | Insurance (coming soon) | Healthcare (coming soon)".
- On selection, deep-copy the profile data into `wizard_form`, preserving any user edits made before selection.
- The 13 section YAMLs provide additional depth that could be merged into the banking template.

### 7.2 Import from Section YAMLs

**What**: A "📥 Import Sections" button in Step 4 that lets users cherry-pick from the existing 13 section YAML files.

**Why**: The section YAMLs contain curated domain knowledge (9 roles, 5 regulatory frameworks, detailed exemplars per section) that took significant effort to create. Currently this data is only accessible to the legacy orchestrator.

**Implementation sketch**:
- List all files in `config/sections/` in a multiselect.
- On import, load each selected section YAML, convert to the `ProcessAreaConfig` format, and append to `form["process_areas"]`.
- User can then customize the imported sections.

### 7.3 AI-Assisted Section Discovery

**What**: A "🤖 Suggest Process Areas" button in Step 4 that takes the org name, description, and control types, then proposes relevant process areas.

**Why**: A compliance officer knows their organization but may not know how to decompose it into APQC-aligned process areas. The ConfigProposerAgent already has the domain expertise to do this.

**Implementation sketch**:
- New `ConfigProposerAgent` mode: `"suggest_sections"`.
- System prompt: "Given this organization description and control types, propose 5-8 relevant process areas with IDs, names, and brief descriptions."
- User reviews the suggestions and accepts/edits/rejects each one.

### 7.4 Drag-and-Drop Affinity Grid

**What**: Replace the per-type selectbox affinity grid with a visual kanban-style board.

**Why**: With 25 control types (as in the banking_standard), clicking 25 individual selectboxes is tedious. A drag-and-drop board with four columns (HIGH, MEDIUM, LOW, NONE) where type pills can be dragged between columns would be faster and more intuitive.

**Implementation sketch**:
- Use a Streamlit custom component or the `streamlit-sortables` package.
- Four columns, each containing draggable chips showing control type names.
- Default all types to MEDIUM; the AI auto-fill or import would set initial positions.

### 7.5 Visual Risk Heat Map / Radar Chart

**What**: Replace or augment the four risk profile sliders with a radar chart or heat map visualization.

**Why**: When building multiple process areas, it's hard to compare risk profiles using sliders alone. A radar chart showing inherent risk, regulatory intensity, control density, and multiplier as a 4-axis polygon would make cross-section comparison instant.

**Implementation sketch**:
- Use `plotly.express.line_polar()` or `matplotlib` radar chart.
- Show a mini radar chart next to each section's risk profile.
- Optionally, a comparison view showing all sections overlaid on one radar.

### 7.6 Inline Validation and Completeness Indicators

**What**: Step-by-step validation warnings and a completeness progress bar.

**Why**: Currently validation only runs at Step 6. A user who referenced a non-existent section in Step 3's BU primary_sections doesn't find out until Step 6. Inline warnings would catch issues early.

**Implementation sketch**:
- After each step, run a lightweight validation pass: check that BU references resolve, types have placements, sections have at least one affinity assignment.
- Show warnings (yellow boxes) at the top of each step for issues inherited from previous steps.
- Add a top-bar progress indicator: "Config completeness: 65% — missing: section registries, exemplars".

### 7.7 Undo History and Config Snapshots

**What**: An undo stack and a "Save Snapshot" feature.

**Why**: The wizard stores all state in a single mutable dict. One wrong click can destroy work. An undo button and the ability to save named snapshots ("before adding compliance section") would protect users.

**Implementation sketch**:
- Maintain a list of `wizard_form` deep-copies in `st.session_state["wizard_history"]`.
- Push a copy before every navigation or AI fill action.
- "↩ Undo" button pops the last entry and restores it.

### 7.8 Side-by-Side Config Comparison

**What**: Compare the user's config against a reference (e.g., `banking_standard.yaml`) to identify gaps.

**Why**: Helps users understand whether their config is comprehensive. "You have 8 control types vs. the standard 25", "Your section 2.0 is missing NONE affinity assignments."

**Implementation sketch**:
- Add a "Compare to Reference" button in Step 6.
- Load a reference profile, diff the two configs, and display a comparison table.
- The Analysis tab's scanner infrastructure already does gap detection — could be adapted.

### 7.9 Rich Exemplar Editor with AI Generation

**What**: A "🤖 Generate Exemplars" button per section that asks the LLM to produce 2-3 high-quality sample narratives.

**Why**: The `section_autofill` mode already returns exemplars, but users may want more targeted control. A dedicated button that generates exemplars using the section's completed registry would produce higher-quality samples.

**Implementation sketch**:
- New `ConfigProposerAgent` mode or a dedicated prompt.
- Input: section name, registry, affinity (HIGH types), narrative constraints.
- Output: 2-3 exemplar dicts with type, placement, method, 30-80 word narrative, quality rating.

### 7.10 Config Quality Scorer

**What**: A real-time "Config Quality Score" displayed in the sidebar showing how complete and internally consistent the config is.

**Why**: Guides users toward better configs. Empty registries → lower generation quality. No exemplars → generic LLM output. The scorer would surface these gaps.

**Implementation sketch**:
- Score dimensions: Types (have definitions? codes? evidence criteria?), BUs (have primary sections? regulatory exposure?), Sections (have registries with ≥3 items each? affinity ≠ all MEDIUM? exemplars?).
- Display as a letter grade (A-F) or percentage with drill-down.

### 7.11 Collaborative Config Building

**What**: Multi-user collaborative config editing where different teams contribute different sections.

**Why**: In a large org, the IT team knows the Technology section registry while Compliance knows the Regulatory Reporting section. Assigning sections to contributors avoids knowledge bottlenecks.

**Implementation sketch**: This is a longer-term feature requiring persistent storage and user management. Possible approach: export partial configs, import and merge.

### 7.12 Full-Screen Section Editor

**What**: A dedicated full-page editor for a single process area, accessible from the Step 4 expander.

**Why**: The current expander-within-expander layout gets cramped for sections with many registry items and exemplars. A full-screen mode would give more space for the registry text areas and affinity grid.

---

## 8. Backend and Pipeline Expansions

### 8.1 Wire the ChromaDB Memory Store

**What**: Create a `ControlMemory` instance in `init_node` and pass it to the tool executor.

**Impact**:
- **Deduplication**: Before generating each control, `check_duplicate()` against the memory store. If a near-duplicate (≥92% cosine similarity) exists, invoke the `DifferentiationAgent` to rewrite.
- **Style consistency**: The `memory_retrieval` tool (already in the schema) would return the highest-rated similar controls as additional context for the NarrativeAgent.
- **Cross-run learning**: After each generation run, `index_controls()` saves all generated controls. Future runs benefit from this accumulated library.
- **Run comparison**: `compare_runs()` lets users see how their latest generation differs from previous ones.

**Implementation sketch**:
- In `init_node`: instantiate `SentenceTransformerEmbedder()` and `ControlMemory(embedder)`.
- Pass `memory` and `bank_id` (from config name) to `build_domain_tool_executor()`.
- In `merge_node` or `finalize_node`: call `memory.index_controls()`.
- In `spec_node` or `enrich_node`: optionally call `memory.check_duplicate()`.

### 8.2 Adversarial Review Pass

**What**: Add an optional "adversarial_review" node between `enrich_node` and `merge_node`.

**Impact**: Each generated control gets stress-tested by the `AdversarialReviewer` agent, which identifies weaknesses (vague language, missing risk coverage, specification violations). Weaknesses are surfaced in the results table as a new "adversarial_findings" column.

**Implementation sketch**:
- New toggle in the UI: "Enable Adversarial Review" (default off due to cost).
- New graph node that calls `AdversarialReviewer.execute(control=enriched, spec=spec)`.
- If the assessment is "Weak", optionally route back to narrative for a guided rewrite using the `rewrite_guidance`.

### 8.3 Differentiation Agent Integration

**What**: Wire the existing `DifferentiationAgent` into the pipeline when the memory store detects a near-duplicate.

**Impact**: Ensures generated controls are semantically distinct. When `check_duplicate()` returns true, the `DifferentiationAgent` rewrites the control to vary the WHAT and WHEN while preserving WHO, WHERE, type, and risk coverage.

### 8.4 Analysis Tab Cross-Feed

**What**: Connect the Analysis tab's gap detection to the Build from Form wizard.

**Impact**: Users upload their existing controls → gap analysis identifies missing control types and sections → one click auto-populates a new DomainConfig targeting those gaps → generation produces only the missing controls.

**Implementation sketch**:
- Add a "Build Config from Gap Report" button in the Analysis tab.
- The gap report already identifies missing control types per section. Convert this into a `DomainConfig` (similar to what `ConfigProposerAgent` full mode does).
- Pre-populate `wizard_form` and redirect to the wizard.

### 8.5 Multi-LLM Provider Strategy

**What**: Route different agents to different LLM providers/models based on cost-quality tradeoffs.

**Current state**: All agents use the same `build_client_from_env()` client. The system detects "ica", "openai", or "anthropic" but uses one provider for everything.

**Expansion**:
- **Model-per-agent routing**: Use a cheaper/faster model (e.g., GPT-4o-mini) for SpecAgent (structured output), a more capable model (GPT-4o, Claude) for NarrativeAgent (prose quality).
- **Quality-driven fallback chains**: Try the best model first, fall back to cheaper model on failure, then deterministic.
- **Cost tracking UI**: The `BaseAgent` already tracks `total_input_tokens` and `total_output_tokens`. Surface cumulative cost estimates in the results panel.

### 8.6 Parallel / Batch Generation

**What**: Generate multiple controls simultaneously instead of sequentially.

**Current state**: The LangGraph loop processes one control at a time (select → spec → narrative → validate → enrich → merge → next).

**Expansion**:
- Use LangGraph's `map` primitive to fan out multiple controls in parallel.
- Borrow the `asyncio.gather() + Semaphore` pattern from the legacy `pipeline/orchestrator.py` which already implements bounded concurrency (`max_parallel_controls`).
- For large runs (100-500 controls), this would dramatically reduce end-to-end time.

### 8.7 Custom Validation Rules from DomainConfig

**What**: Allow the `DomainConfig` to specify per-organization validation rules beyond the 6 hardcoded ones.

**Example**: "All Authorization controls must mention 'approval threshold'", "Reconciliation controls must reference the General Ledger System", "No control should mention 'manual' if the method is 'Automated'".

**Implementation sketch**:
- Add a `custom_validation_rules` field to `DomainConfig`.
- Each rule is a dict: `{"name": "AUTH_THRESHOLD", "field": "what", "contains": "approval threshold", "applies_to_types": ["Authorization"]}`.
- The validator dynamically applies these rules alongside the 6 built-in ones.

### 8.8 Export Format Expansion

**Current state**: CSV and JSON download in the UI. `export/excel.py` supports Excel export with 19 columns.

**Expansion**:
- **PDF Reports**: Professional PDF with cover page, summary stats, controls grouped by section, risk distribution charts.
- **Regulatory filing formats**: Specific formats required by regulators (OCC, SEC, FINRA) for control register submissions.
- **Import-ready formats**: Excel formatted to match common GRC tools (ServiceNow GRC, Archer, MetricStream) import templates.
- **YAML re-export**: Export the generated controls as a YAML file that can be imported back as exemplars in a future config.

### 8.9 Config Versioning and Diff

**What**: Track config evolution with version numbers and provide a diff tool.

**Why**: As organizations evolve (new business lines, new regulations), their configs change. Understanding what changed between versions is critical for audit trails.

**Implementation sketch**:
- Add a `version: int` field to `DomainConfig`.
- Store version history in `config/profiles/{name}/v1.yaml`, `v2.yaml`, etc.
- A "Compare Versions" UI showing added/removed/modified types, BUs, sections.
- Migration guidance: "You added 3 new control types — these need affinity assignments in all 13 sections."

---

## 9. Data and Ecosystem Expansions

### 9.1 Industry Config Packs

**What**: Pre-packaged config templates for industries beyond banking.

**Available starting point**: The 13 section YAMLs + banking_standard profile provide a mature banking template. Similar packs could be created for:

| Industry | Process Areas | Key Control Types | Regulatory Frameworks |
|---|---|---|---|
| **Insurance** | Underwriting, Claims Processing, Policy Administration, Actuarial, Reinsurance | Claims Authorization, Underwriting Review, Reserve Validation, Policy Reconciliation | NAIC Model Laws, Solvency II, ORSA |
| **Healthcare** | Clinical Operations, Patient Data, Billing & Coding, Clinical Trials, Pharmacy | PHI Access Control, Billing Reconciliation, Clinical Protocol Monitoring, Adverse Event Reporting | HIPAA, HITECH, FDA 21 CFR Part 11 |
| **Technology** | SDLC, Incident Management, Access Management, Change Management, Data Governance | Access Review, Change Authorization, Incident Escalation, Code Review, Data Classification | SOC 2, ISO 27001, NIST CSF, PCI DSS |
| **Fintech** | Digital Payments, Lending Platform, Compliance Automation, Customer Onboarding | Transaction Monitoring, AML Screening, Identity Verification, Consent Management | BSA/AML, PSD2, GDPR, State Licensing |

### 9.2 Regulatory Framework Catalog

**What**: A structured `regulatory_catalog.yaml` mapping frameworks to specific control requirements.

**Impact**: Auto-validate that generated controls cover all required regulatory themes. The `regulatory_lookup` tool already exists — a catalog would make it much richer.

### 9.3 APQC Process Framework Mapping

**What**: Include the full APQC hierarchy data (currently partially parsed by `hierarchy/parser.py` and `hierarchy/scope.py`) so process areas auto-map to standardized industry processes.

**Impact**: Users selecting "Financial Management" as a process area would see it mapped to APQC 8.0 (Manage Financial Resources) with pre-populated sub-processes.

### 9.4 Multi-Language and Multi-Jurisdiction Support

**What**: Generate controls in languages other than English, with jurisdiction-specific regulatory frameworks.

**Implementation**: Add `language` and `jurisdiction` fields to `DomainConfig`. Localized phrase banks and regulatory frameworks per jurisdiction. The `NarrativeAgent` prompt would include language instructions.

---

## 10. Future Architecture Directions

(Based on the vision documented in `docs/future-architecture-and-tool-vision.md`)

### 10.1 Multi-Bank Federated Control Intelligence

Multiple organizations share anonymized control patterns through a federated learning approach. Each bank's ChromaDB memory contributes to aggregate "best practice" embeddings without exposing proprietary control text. The `memory/store.py` infrastructure provides the foundation — each org gets its own collection (`controls_{bank_id}`), and cross-org queries could use averaged embeddings.

### 10.2 Regulatory Horizon Scanning

An agent that monitors regulatory publications (Federal Register, OCC bulletins, FINRA notices) and proposes config updates. For example: "New OCC guidance on third-party risk management — recommend increasing the multiplier for section 10.0 (Third Party Management) from 2.0 to 3.0 and adding 'OCC Bulletin 2025-XX' to the regulatory frameworks list."

### 10.3 Autonomous Control Lifecycle Management

Controls don't just get generated — they get tested, rated, remediated, and retired. The full lifecycle:

```
Generate → Test (adversarial) → Deploy → Monitor → Remediate → Retire
```

Each phase modeled as a LangGraph subgraph. The `DomainConfig` evolves based on lifecycle feedback (e.g., controls that consistently fail adversarial review trigger a config update to add better exemplars).

### 10.4 Adversarial Stress Testing as a Service

Run the `AdversarialReviewer` against all controls in an existing register (uploaded via the Analysis tab), producing:
- Per-control weakness report
- Aggregate "control population health" score
- Priority list of controls needing remediation
- Auto-generated remediation controls via the remediation graph

### 10.5 Cross-Framework Harmonization Engine

Map controls across multiple frameworks (SOX, COSO, Basel III, NIST CSF, ISO 27001) to identify overlaps and gaps. Produce a unified control-to-framework mapping matrix showing which controls satisfy which framework requirements. Uses the `regulatory_frameworks` data already in each section's registry.

---

## 11. Summary Matrix — Current vs. Expansion Potential

| Dimension | Current State | Available Infrastructure | Expansion Potential |
|---|---|---|---|
| **Config input** | 3 paths: Select Profile, Build from Form, Import from Excel | Profiles dir, RegisterAnalyzer, ConfigProposerAgent | Template library, industry packs, collaborative editing, gap-driven config |
| **Control types** | User-defined + AI enrichment (definitions, codes, evidence) | 25 banking types with expert definitions in banking_standard | Auto-suggest from org description, import from regulatory catalogs, custom type hierarchies |
| **Process areas** | User-defined + AI auto-fill (risk, affinity, registry, exemplars) | 13 detailed section YAMLs with deep domain knowledge | Import from sections, APQC mapping, AI discovery, section templates per industry |
| **Affinity grid** | Per-type selectbox (HIGH/MEDIUM/LOW/NONE) | Full config model, 13 curated affinity grids | Drag-and-drop kanban, auto-suggest from section description |
| **Domain registries** | 6 text areas (roles, systems, etc.) | 13 section YAMLs with 5-15 items per field | Auto-populate from templates, AI-suggest from section+industry context |
| **Exemplars** | Manual entry per section | AI auto-fill returns exemplars, 13 sections have curated ones | Dedicated AI exemplar generator, exemplar library, import from existing controls |
| **Generation engine** | 8-node LangGraph, sequential, 1 LLM provider | Dual-mode prompts, 9 tools, 3 agent types, XML tool simulation | Parallel generation, multi-model routing, cost tracking |
| **Validation** | 6 deterministic rules + 3-retry loop | Configurable word counts, curated verb roots, risk markers | Custom rules from DomainConfig, adversarial review, configurable thresholds |
| **Memory** | Tool schema + dispatch stub (not wired) | ChromaDB store, SentenceTransformer embedder, duplicate detection, run comparison | Full wiring: dedup, style consistency, cross-run learning, differentiation agent |
| **Export** | CSV, JSON download | Excel export (19 columns) | PDF reports, GRC tool formats, regulatory filing formats, YAML re-export |
| **Analysis cross-feed** | Separate tab, no connection | RegisterAnalyzer, gap scanners, remediation graph | Gap → auto-config, comparison to reference, remediation pipeline |
| **Adversarial testing** | Agent exists but not wired | AdversarialReviewer, DifferentiationAgent | Post-generation review pass, stress testing as a service |
| **Multi-org** | Single config at a time | Per-bank ChromaDB collections | Federated intelligence, config marketplace, multi-tenant |
| **Regulatory** | Section-level framework lists | regulatory_lookup tool, section yamls with 5+ frameworks each | Framework catalog, horizon scanning, cross-framework harmonization |
| **Language/jurisdiction** | English only, US banking focus | Configurable narrative fields and constraints | Multi-language generation, jurisdiction-specific frameworks |
