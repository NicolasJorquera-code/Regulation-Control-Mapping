# ControlForge Tab Guide

A standalone reference for developers working on the ControlForge tab in the ControlNexus Streamlit dashboard. No prior knowledge of the codebase is assumed.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Key Concepts](#2-key-concepts)
3. [Configuration Files](#3-configuration-files)
4. [How Configs Produce a Control Taxonomy](#4-how-configs-produce-a-control-taxonomy)
5. [The ControlForge Tab](#5-the-controlforge-tab)
6. [Code Architecture](#6-code-architecture)
7. [Data Models](#7-data-models)
8. [Config Loader Functions](#8-config-loader-functions)
9. [CSS and Styling](#9-css-and-styling)
10. [How to Run the App](#10-how-to-run-the-app)
11. [Common Development Tasks](#11-common-development-tasks)
12. [End-to-End Walkthrough](#12-end-to-end-walkthrough) (8 steps including pipeline execution)

---

## 1. What This System Does

ControlNexus generates **internal control descriptions** for financial institutions. A control is a documented procedure that describes who does what, when, where, and why to manage operational, regulatory, or financial risk.

The ControlForge tab is the configuration explorer and pipeline runner. It lets users browse every YAML configuration file that feeds the control generation pipeline, understand how they relate, and run the full control generation pipeline directly from the UI.

---

## 2. Key Concepts

### What is a Control?

A control answers five questions (the **5W framework**):

| Field | Question | Example |
|-------|----------|---------|
| **Who** | Who performs this control? | Vendor Risk Analyst |
| **What** | What action do they take? | Completes vendor due diligence assessment |
| **When** | When or how often? | Upon initiation of new vendor engagement |
| **Where** | In which system/location? | Third Party Risk Assessment Tool |
| **Why** | What risk does it mitigate? | Prevents engagement with high-risk vendors |

A complete control record also includes:
- **Control Type** (e.g., Authorization, Reconciliation) -- one of 25 defined types
- **Placement** (Preventive, Detective, or Contingency Planning) -- when the control acts relative to the risk event
- **Method** (Automated, Manual, or Automated with Manual Component)
- **Business Unit** -- which organizational unit owns it (e.g., BU-015 Third Party Risk Management)
- **Evidence** -- the audit artifact proving the control operates (e.g., signed scorecard retained in the system)
- **Quality Rating** -- Strong, Effective, Satisfactory, or Needs Improvement

### What is the APQC Hierarchy?

APQC (Association for Professional and Process Classification) is a standardized taxonomy of business processes. It organizes processes into 13 top-level sections, each nested into sub-processes:

```
Section 4.0 — Source and Procure Materials and Services
  └── 4.1 — Develop sourcing strategies
      └── 4.1.1 — Develop procurement plan
          └── 4.1.1.1 — Develop procurement plan (leaf node)
          └── 4.1.1.2 — Clarify purchasing requirements (leaf node)
```

**Leaf nodes** are the deepest level. Controls attach to leaf nodes -- each leaf can have multiple controls.

### The 13 APQC Sections

| Section | Domain |
|---------|--------|
| 1.0 | Vision and Strategy |
| 2.0 | Products and Services |
| 3.0 | Marketing and Sales |
| 4.0 | Sourcing and Procurement |
| 5.0 | Delivery |
| 6.0 | Customer Service |
| 7.0 | Human Capital |
| 8.0 | Information Technology |
| 9.0 | Financial Resources |
| 10.0 | Assets |
| 11.0 | Enterprise Risk and Compliance |
| 12.0 | External Relationships |
| 13.0 | Business Capabilities |

### How Controls are Generated (Pipeline Overview)

```
Config Files (YAML)    +    APQC Hierarchy (Excel)
         │                          │
         ▼                          ▼
   ┌─────────────────────────────────────┐
   │  1. Load hierarchy, select scope     │
   │  2. Load taxonomy + section profiles │
   │  3. Calculate target count           │
   │  4. Distribute types across sections │
   │  5. Map: leaf × type × business unit │
   │  6. Build control records            │
   │     (deterministic defaults          │
   │      + optional LLM enrichment)      │
   │  7. Export to Excel                  │
   └─────────────────────────────────────┘
         │
         ▼
   controls.xlsx (19 columns × N controls)
```

The ControlForge tab displays steps 1-2 (the configuration inputs) in the Section Profiles and Global Config sub-tabs, and runs steps 3-7 (the full pipeline) in the Run Section sub-tab.

---

## 3. Configuration Files

All config files live in `/config/` at the project root. There are four groups:

### 3.1 taxonomy.yaml

**Location:** `config/taxonomy.yaml`

The master reference for control types and business units.

**Structure:**
```yaml
control_types:          # 25 items
  - control_type: "Reconciliation"
    definition: "Comparison of features, transactions..."
  - control_type: "Authorization"
    definition: "Approval or permission granted..."
  # ... 23 more

business_units:         # 17 items (BU-001 through BU-017)
  - business_unit_id: "BU-001"
    name: "Retail Banking"
    description: "Provides consumer deposit accounts..."
    primary_sections: ["5.0", "3.0", "6.0"]
    key_control_types:
      - "Authorization"
      - "Client Due Diligence and Transaction Monitoring"
      - "Segregation of Duties"
    regulatory_exposure:
      - "Regulation E"
      - "BSA/AML"
```

**Key relationships:**
- `key_control_types` must reference names that exist in `control_types`
- `primary_sections` maps BUs to the APQC sections they own (e.g., Retail Banking owns sections 5.0, 3.0, 6.0)

### 3.2 Section Profiles (section_1.yaml through section_13.yaml)

**Location:** `config/sections/section_N.yaml` (N = 1 to 13)

Each file defines the operational context for one APQC section. This is the richest config -- it drives realistic control generation.

**Structure (section_4.yaml as example):**
```yaml
section_id: "4.0"
domain: "sourcing_and_procurement"

risk_profile:
  inherent_risk: 3         # 1-5 scale
  regulatory_intensity: 4   # 1-5 scale
  control_density: 3        # 1-5 scale
  multiplier: 2.3           # allocation weight
  rationale: "Sourcing and procurement of materials..."

affinity:                   # Which control types are relevant here
  HIGH:
    - "Third Party Due Diligence"
    - "Authorization"
    - "Verification and Validation"
    - "Documentation, Data, and Activity Completeness..."
  MEDIUM:
    - "Risk and Compliance Assessments"
    - "Segregation of Duties"
  LOW:
    - "Reconciliation"
    - "Training and Awareness Programs"
  NONE:
    - "Surveillance"
    - "Physical Safeguards"

registry:                   # Domain vocabulary for control generation
  roles:
    - "Procurement Analyst"
    - "Vendor Risk Analyst"
    - "Contract Manager"
  systems:
    - "Vendor Management Platform"
    - "Third Party Risk Assessment Tool"
  data_objects:
    - "Vendor due diligence questionnaires"
    - "Risk assessment scorecards"
  evidence_artifacts:
    - "Risk assessments with sign-off"
    - "Contract approval logs"
  event_triggers:
    - "New vendor engagement"
    - "Annual risk reassessment"
  regulatory_frameworks:
    - "OCC 2023-17"
    - "Federal Reserve SR 13-19"

exemplars:                  # Sample controls showing desired style
  - control_type: "Third Party Due Diligence"
    placement: "Preventive"
    method: "Manual with System Support"
    full_description: "Prior to contract execution, the Vendor Risk Analyst..."
    word_count: 52
    quality_rating: "Strong"
```

**How each section is used:**
- **risk_profile.multiplier** -- higher-risk sections get more controls allocated to them
- **affinity** -- HIGH-affinity types are generated more frequently for this section
- **registry** -- provides domain-specific roles, systems, and vocabulary so controls sound realistic (e.g., section 4 controls mention "Vendor Risk Analyst" and "Third Party Risk Assessment Tool", not generic placeholders)
- **exemplars** -- sample controls the LLM uses as style references

### 3.3 placement_methods.yaml

**Location:** `config/placement_methods.yaml`

Defines the control classification taxonomy -- which control types can appear under which placement.

**Structure:**
```yaml
placements:
  - Preventive
  - Detective
  - Contingency Planning

methods:
  - Automated
  - Manual
  - Automated with Manual Component

control_taxonomy:
  level_1_options:
    - Preventive
    - Detective
    - Contingency Planning
  level_2_by_level_1:
    Preventive:             # 15 control types
      - "Authorization"
      - "Third Party Due Diligence"
      - "Data Security and Protection"
      # ...
    Detective:              # 6 control types
      - "Reconciliation"
      - "Exception Reporting"
      - "Surveillance"
      # ...
    Contingency Planning:   # 3 control types
      - "Business Continuity Planning and Awareness"
      - "Crisis Management"
      - "Technology Disaster Recovery"
```

**Why this matters:** This prevents invalid combinations. Reconciliation is always Detective, never Preventive. Authorization is always Preventive, never Detective.

### 3.4 standards.yaml

**Location:** `config/standards.yaml`

Narrative standards for writing control descriptions.

**Structure:**
```yaml
five_w:
  who: "Define accountable role"
  what: "Define specific action and control objective"
  when: "Define trigger, frequency, timing"
  where: "Define system/location/process"
  why: "Define risk prevented/detected and impact"

phrase_bank:
  action_verbs:
    - reviews
    - reconciles
    - validates
    - approves
    - investigates
  timing_phrases:
    - daily
    - weekly
    - monthly
    - at month-end close

quality_ratings:
  - Strong
  - Effective
  - Satisfactory
  - Needs Improvement
```

---

## 4. How Configs Produce a Control Taxonomy

Here is how all four config groups connect to produce one control record:

```
taxonomy.yaml
  └─ Defines "Third Party Due Diligence" (type) + "BU-015" (business unit)
       │
placement_methods.yaml
  └─ Says "Third Party Due Diligence" must be "Preventive" (placement)
       │
section_4.yaml
  └─ Says "Third Party Due Diligence" has HIGH affinity to section 4
  └─ Provides: who="Vendor Risk Analyst", where="Third Party Risk Assessment Tool"
  └─ Provides: when trigger="New vendor engagement"
  └─ Provides: exemplar showing desired writing style
       │
standards.yaml
  └─ Provides 5W framework + approved action verbs
       │
       ▼
GENERATED CONTROL:
  control_id:      CTRL-0401-THR-002
  hierarchy_id:    4.1.1.1 (from APQC hierarchy)
  leaf_name:       "Develop procurement plan"
  selected_level_1: Preventive (from placement_methods.yaml)
  selected_level_2: Third Party Due Diligence (from taxonomy.yaml)
  business_unit:   BU-015 Third Party Risk Management (from taxonomy.yaml)
  who:             Vendor Risk Analyst (from section_4.yaml registry)
  what:            Completes vendor due diligence assessment... (from LLM or template)
  when:            Upon initiation of new vendor engagement (from registry)
  where:           Third Party Risk Assessment Tool (from registry)
  why:             Mitigates third party operational risks... (from LLM or template)
  evidence:        Vendor risk assessment scorecard with sign-off... (from registry)
  quality_rating:  Effective (from LLM evaluation)
```

---

## 5. The ControlForge Tab

### Where It Lives in the App

The ControlForge tab is the fourth tab in the main dashboard (after Analysis, Playground, Evaluation). It contains three sub-tabs:

```
┌──────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐
│ Analysis │ │ Playground │ │ Evaluation │ │ ControlForge │  <-- you are here
└──────────┘ └────────────┘ └────────────┘ └──────────────┘
                                              │
                     ┌────────────────────┬────┴──────────┬──────────────┐
                     │ Section Profiles   │ Global Config │ Run Section  │
                     └────────────────────┴───────────────┴──────────────┘
```

### Sub-Tab 1: Section Profiles

Browse one section at a time. Select a section from the dropdown, then see:

1. **Risk Profile** -- four metric cards (Inherent Risk, Regulatory Intensity, Control Density, Multiplier) plus a rationale expander
2. **Affinity Matrix** -- control types grouped by relevance tier (HIGH/MEDIUM/LOW/NONE) as colored badges
3. **Domain Registry** -- six collapsible lists (Roles, Systems, Data Objects, Evidence Artifacts, Event Triggers, Regulatory Frameworks)
4. **Exemplar Controls** -- expandable cards showing sample controls with word count and quality rating

### Sub-Tab 2: Global Config

Cross-section configuration:

1. **Control Type Taxonomy** -- searchable/sortable table of all 25 control types with definitions
2. **Business Units** -- 17 expandable cards showing each BU's description, primary sections, control types, and regulatory exposure
3. **Placement & Method Taxonomy** -- lists the 3 placements and 3 methods, plus the Level 1 to Level 2 mapping tree
4. **Narrative Standards** -- 5W definitions, phrase bank (action verbs, timing phrases), quality rating scale

### Sub-Tab 3: Run Section

Runs the full control generation pipeline from the UI:

1. **APQC Data Loading** -- Auto-loads from `data/APQC_Template.xlsx` if present, or accepts file upload (`.xlsx` or `.csv`). Shows summary: total nodes, leaves, and available sections.
2. **Pipeline Configuration:**
   - `Target Sections` -- multiselect populated from loaded hierarchy's distinct sections
   - `Target Control Count` -- number of controls to generate (1-10,000)
   - `Dry Run Limit` -- cap on controls for quick testing (0 = no limit)
3. **Execution** -- "Run Pipeline" button triggers the async orchestrator with live progress updates via `st.status()`. Runs through 3 phases: deterministic defaults, optional LLM enrichment, merge + CTRL ID assignment.
4. **Results Display:**
   - 4 metric cards (Target, Generated, Leaves, LLM Enabled)
   - Section Allocation table
   - Section Breakdown table
   - Full Plan JSON viewer
   - Download buttons for Excel and Plan JSON

---

## 6. Code Architecture

### File Map

```
src/controlnexus/ui/
├── app.py                    # Main entry point, defines 4 tabs
├── controlforge_tab.py       # All ControlForge rendering logic (this guide)
├── styles.py                 # IBM Carbon CSS classes and design tokens
├── playground.py             # Playground tab (not relevant here)
├── components/
│   ├── upload.py             # Analysis tab upload widget
│   └── analysis_runner.py    # Analysis tab runner
└── renderers/
    ├── gap_dashboard.py      # Analysis tab results
    └── eval_dashboard.py     # Evaluation tab results

src/controlnexus/hierarchy/
├── __init__.py               # Exports: load_apqc_hierarchy, select_scope, build_section_breakdown
├── parser.py                 # APQC hierarchy parser (Excel/CSV → HierarchyNode[])
└── scope.py                  # Scope selection + section breakdown

src/controlnexus/pipeline/
├── __init__.py               # Exports: Orchestrator, PlanningResult, planning_result_to_dict
└── orchestrator.py           # Async 3-phase control generation orchestrator

src/controlnexus/core/
├── config.py                 # YAML loader functions
├── models.py                 # Pydantic data models (RunConfig, SectionProfile, etc.)
├── state.py                  # State models (HierarchyNode, FinalControlRecord, etc.)
└── transport.py              # AsyncTransportClient for LLM API calls

config/
├── taxonomy.yaml
├── standards.yaml
├── placement_methods.yaml
└── sections/
    ├── section_1.yaml
    ├── section_2.yaml
    └── ... through section_13.yaml
```

### How the Tab Is Wired In

**app.py** creates the tab and calls the entry point:

```python
# app.py lines 38-53
tab_analysis, tab_playground, tab_evaluation, tab_controlforge = st.tabs(
    ["Analysis", "Playground", "Evaluation", "ControlForge"]
)
with tab_controlforge:
    _render_controlforge_tab()

# app.py lines 111-115
def _render_controlforge_tab() -> None:
    from controlnexus.ui.controlforge_tab import render_controlforge  # lazy import
    render_controlforge()
```

The lazy import pattern (importing inside the function body) is used by all tabs. It prevents loading tab-specific code until the tab is clicked.

### controlforge_tab.py Structure

```
render_controlforge()                    # Entry point: title + 3 sub-tabs
├── _render_section_profiles_subtab()    # Sub-tab 1
│   ├── _render_risk_profile()           #   Risk metrics + rationale
│   ├── _render_affinity_matrix()        #   Colored badge groups
│   ├── _render_domain_registry()        #   6 expandable lists
│   └── _render_exemplar_controls()      #   Expandable control cards
├── _render_global_config_subtab()       # Sub-tab 2
│   ├── _render_taxonomy_table()         #   Dataframe of control types
│   ├── _render_business_units()         #   Expandable BU cards
│   ├── _render_placement_methods_tree() #   Placement/method tree
│   └── _render_standards()              #   5W, phrase bank, ratings
└── _render_run_section_subtab()         # Sub-tab 3
    ├── _render_apqc_loader()            #   Auto-load from disk + file uploader
    ├── _execute_pipeline()              #   Build RunConfig, run orchestrator
    └── _display_pipeline_results()      #   Metrics, tables, downloads

Helper functions:
├── _resolve_config_dir()                # Find config/ directory
├── _resolve_project_root()              # Find project root
├── _load_apqc_from_disk()              # Auto-load APQC_Template.xlsx
├── _get_cached_profiles()               # @st.cache_data wrapper
├── _get_cached_taxonomy()               # @st.cache_data wrapper
├── _get_cached_standards()              # @st.cache_data wrapper
└── _get_cached_placement_methods()      # @st.cache_data wrapper
```

### Caching Strategy

All YAML loaders are wrapped in `@st.cache_data` functions. This prevents re-reading files on every Streamlit rerun (any widget interaction triggers a full script re-execution).

Important details:
- Cache keys must be **hashable**. Pydantic models and `Path` objects are not hashable, so cache functions accept `str` paths
- Cached data must be **serializable**. Pydantic models are converted to dicts via `model_dump()` before caching, then reconstructed on retrieval
- `show_spinner="Loading..."` provides user feedback during first load

```python
@st.cache_data(show_spinner="Loading section profiles...")
def _get_cached_profiles(config_dir_str: str) -> dict[str, Any]:
    from controlnexus.core.config import load_all_section_profiles
    profiles = load_all_section_profiles(Path(config_dir_str))
    return {sid: p.model_dump() for sid, p in profiles.items()}
```

---

## 7. Data Models

All models are in `src/controlnexus/core/models.py` and use Pydantic v2.

### SectionProfile

The top-level model for a section config file. Used by Sub-tab 1.

```python
class SectionProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section_id: str                         # "1.0", "4.0", etc.
    domain: str                             # "sourcing_and_procurement"
    risk_profile: RiskProfile               # nested
    affinity: AffinityMatrix                # nested, defaults to empty
    registry: DomainRegistry                # nested
    exemplars: list[ExemplarControl]        # defaults to empty list
```

### RiskProfile

```python
class RiskProfile(BaseModel):
    model_config = ConfigDict(frozen=True)  # immutable

    inherent_risk: int          # 1-5
    regulatory_intensity: int   # 1-5
    control_density: int        # 1-5
    multiplier: float           # e.g., 2.3
    rationale: str              # explanation text
```

### AffinityMatrix

```python
class AffinityMatrix(BaseModel):
    HIGH: list[str]     # e.g., ["Authorization", "Third Party Due Diligence"]
    MEDIUM: list[str]
    LOW: list[str]
    NONE: list[str]     # control types not relevant to this section
```

### DomainRegistry

```python
class DomainRegistry(BaseModel):
    roles: list[str]                # job titles
    systems: list[str]              # software platforms
    data_objects: list[str]         # data types handled
    evidence_artifacts: list[str]   # audit trail documents
    event_triggers: list[str]       # when controls activate
    regulatory_frameworks: list[str] # applicable regulations
```

### ExemplarControl

```python
class ExemplarControl(BaseModel):
    model_config = ConfigDict(frozen=True)

    control_type: str       # e.g., "Third Party Due Diligence"
    placement: str          # e.g., "Preventive"
    method: str             # e.g., "Manual with System Support"
    full_description: str   # 30-80 word narrative
    word_count: int
    quality_rating: str     # "Strong", "Effective", etc.
```

### TaxonomyCatalog

Used by Sub-tab 2 (Global Config).

```python
class TaxonomyCatalog(BaseModel):
    control_types: list[TaxonomyItem]            # 25 items
    business_units: list[BusinessUnitProfile]     # 17 items
```

### TaxonomyItem

```python
class TaxonomyItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    control_type: str    # e.g., "Reconciliation"
    definition: str      # 30-60 word formal definition
```

### BusinessUnitProfile

```python
class BusinessUnitProfile(BaseModel):
    business_unit_id: str           # "BU-001"
    name: str                       # "Retail Banking"
    description: str                # function/purpose
    primary_sections: list[str]     # ["5.0", "3.0", "6.0"]
    key_control_types: list[str]    # subset of the 25 types
    regulatory_exposure: list[str]  # applicable regulations
```

---

## 8. Config Loader Functions

All loaders are in `src/controlnexus/core/config.py`.

| Function | Input | Output | Used By |
|----------|-------|--------|---------|
| `load_all_section_profiles(config_dir)` | `Path` to `config/` | `dict[str, SectionProfile]` keyed by "1"-"13" | Section Profiles sub-tab |
| `load_taxonomy_catalog(path)` | `Path` to `taxonomy.yaml` | `TaxonomyCatalog` | Taxonomy table, Business Units |
| `load_standards(path)` | `Path` to `standards.yaml` | `dict[str, Any]` (raw YAML) | Standards section |
| `load_placement_methods(path)` | `Path` to `placement_methods.yaml` | `dict[str, Any]` (raw YAML) | Placement/Methods tree |

`load_taxonomy_catalog` performs cross-validation: every `key_control_types` entry in business units must reference a control type name that exists in `control_types`. It raises `ConfigValidationError` if not.

`load_standards` and `load_placement_methods` return raw dicts (no Pydantic model). The UI code accesses them with `.get()` calls.

---

## 9. CSS and Styling

The app uses the IBM Carbon Design System. All CSS is in `src/controlnexus/ui/styles.py`.

### Reusable CSS Classes

| Class | Purpose | Used In |
|-------|---------|---------|
| `.report-title` | Large page heading (2.625rem, light weight) | Tab titles |
| `.report-subtitle` | Subtitle with bottom border | Tab subtitles |
| `.carbon-tag` | Inline badge (rounded pill, semibold, small) | Affinity badges, registry items |
| `.affinity-high` | Green badge (#198038) | HIGH affinity items |
| `.affinity-medium` | Yellow badge (#f1c21b) | MEDIUM affinity items |
| `.affinity-low` | Light gray badge (#e0e0e0) | LOW affinity items |
| `.affinity-none` | Very light badge (#f4f4f4) | NONE affinity items |
| `.tag-blue`, `.tag-teal`, `.tag-green`, `.tag-purple`, `.tag-cyan`, `.tag-magenta`, `.tag-red`, `.tag-gray` | Color variants for `carbon-tag` | Various badge uses |

### Design Tokens

Colors, spacing, and typography are defined as Python dicts (`_COLORS`, `_SPACING`, `_TYPOGRAPHY`) and interpolated into CSS via f-strings. Key values:

- Primary text: `#161616`
- Interactive blue: `#0f62fe`
- Font: IBM Plex Sans (loaded from Google Fonts)
- Dark mode: supported via `@media (prefers-color-scheme: dark)` block

### Masthead Navigation

`get_masthead_html()` in styles.py renders the top header bar. It includes "ControlForge" in the nav item list.

---

## 10. How to Run the App

### Prerequisites

- Python 3.11+ (venv at `.venv` using `/opt/homebrew/bin/python3.11`)
- Dependencies installed: `pip install -e .` (includes streamlit, pydantic, pyyaml)

### Start the Dashboard

```bash
streamlit run src/controlnexus/ui/app.py
```

The app opens at `http://localhost:8501`. Click the "ControlForge" tab.

### Clear Cache

If you edit YAML config files and want to see changes reflected:

```bash
# Option 1: In the Streamlit UI, press "C" then "Clear cache"
# Option 2: Restart the Streamlit server
```

---

## 11. Common Development Tasks

### Adding a New Panel to Section Profiles

1. Create a render function in `controlforge_tab.py`:
   ```python
   def _render_my_panel(profile: Any) -> None:
       st.markdown("### My Panel")
       # access profile.my_field
   ```

2. Call it from `_render_section_profiles_subtab()`:
   ```python
   _render_exemplar_controls(profile)
   st.markdown("---")
   _render_my_panel(profile)  # add here
   ```

### Adding a New Section to Global Config

1. Create a render function:
   ```python
   def _render_my_config(config_dir: Path) -> None:
       st.markdown("### My Config")
       data = load_my_config(config_dir / "my_file.yaml")
       # render data
   ```

2. Add a cache wrapper if the file is large:
   ```python
   @st.cache_data(show_spinner="Loading...")
   def _get_cached_my_config(path_str: str) -> dict[str, Any]:
       return load_my_config(Path(path_str))
   ```

3. Call from `_render_global_config_subtab()`.

### Adding a New Config File

1. Create the YAML file in `config/`
2. Add a loader function in `core/config.py` (follow the `load_standards` pattern for raw dicts, or define a Pydantic model for typed access)
3. Add a cache wrapper and render function in `controlforge_tab.py`
4. If the new config has cross-references to `taxonomy.yaml`, add validation in the loader

### Understanding the Pipeline Orchestrator

The control generation pipeline lives in `src/controlnexus/pipeline/orchestrator.py`. Key components:

- **`Orchestrator(run_config, project_root)`** -- main class, takes a `RunConfig` and project root path
- **`execute_planning(config_dir, verbose, progress_callback)`** -- async entry point, returns `PlanningResult`
- **`PlanningResult`** -- dataclass containing `final_records`, `section_allocation`, `type_distribution`, and metadata
- **`planning_result_to_dict(result)`** -- serializes a `PlanningResult` to a JSON-safe dict

The pipeline runs in 3 phases:
1. **Phase 1 (Deterministic):** Loads hierarchy, selects scope, distributes control types across sections, maps leaf nodes to types and business units, builds default 5W fields from section registry data
2. **Phase 2 (LLM Enrichment):** Optionally enriches controls via async `SpecAgent` → `NarrativeAgent` → `EnricherAgent` with `Semaphore`-throttled parallelism. Falls back to deterministic defaults if no LLM credentials are configured.
3. **Phase 3 (Finalization):** Merges enriched and default records, assigns `CTRL-SSTT-TYP-NNN` control IDs, builds `FinalControlRecord` Pydantic objects, exports to Excel

The `RunConfig` model (from `controlnexus.core.models`):
```python
class RunConfig(BaseModel):
    run_id: str
    scope: ScopeConfig            # sections: list[str]
    sizing: SizingConfig          # target_count, dry_run_limit
    checkpoint: CheckpointConfig  # enabled, resume, directory
    transport: TransportConfig    # timeout, retries, temperature
    concurrency: ConcurrencyConfig # max_parallel_sections/controls
    output: OutputConfig          # directory, formats
```

### Understanding the Hierarchy Parser

The APQC hierarchy parser lives in `src/controlnexus/hierarchy/parser.py`:

- **`load_apqc_hierarchy(source: Path)`** -- parses an Excel or CSV file into `list[HierarchyNode]`
- **`load_apqc_hierarchy_from_bytes(data: bytes, filename: str)`** -- same but from raw bytes (for Streamlit file uploader)
- **`select_scope(nodes, top_sections, subsection)`** -- filters nodes to selected sections
- **`build_section_breakdown(nodes)`** -- groups nodes by section with node/leaf counts

The parser reads the APQC template (1803 rows across 13 sections), builds `HierarchyNode` objects, and marks leaf nodes (nodes with no children). Leaf nodes are where controls attach.

---

## 12. End-to-End Walkthrough

This section walks through how a developer would use the ControlForge tab to understand and complete a full Control Taxonomy.

### Step 1: Understand the Control Types

Open the **Global Config** sub-tab. Look at the **Control Type Taxonomy** table. This is the master list of 25 control types. Each has a formal definition. These are the building blocks -- every generated control must be one of these types.

Key types to understand:
- **Authorization** -- approval controls (Preventive)
- **Reconciliation** -- comparison/matching controls (Detective)
- **Segregation of Duties** -- separation of roles (Preventive)
- **Exception Reporting** -- anomaly detection (Detective)
- **Third Party Due Diligence** -- vendor assessment (Preventive)

### Step 2: Understand the Classification Rules

Still in Global Config, look at **Placement & Method Taxonomy**. This shows which control types belong to which placement category:

- **Preventive** (15 types) -- controls that prevent risk events before they occur
- **Detective** (6 types) -- controls that detect risk events after they occur
- **Contingency Planning** (3 types) -- controls for business continuity

This is a hard constraint. You cannot classify a Reconciliation control as Preventive.

### Step 3: Understand Who Owns What

Look at **Business Units** in Global Config. Expand a few cards. Notice:
- `primary_sections` tells you which APQC sections a BU operates in
- `key_control_types` tells you which types are relevant to that BU
- `regulatory_exposure` tells you which regulations apply

For example, BU-015 (Third Party Risk Management) operates in sections 4.0, 11.0, 12.0 and cares about Third Party Due Diligence, Authorization, and Risk and Compliance Assessments.

### Step 4: Explore a Section Profile

Switch to the **Section Profiles** sub-tab. Select **Section 4 -- Sourcing And Procurement**.

Walk through each panel:

**Risk Profile:** Section 4 has multiplier 2.3 (above average), meaning it gets proportionally more controls. Regulatory intensity is 4/5 (high), reflecting OCC and Federal Reserve vendor management requirements.

**Affinity Matrix:** Third Party Due Diligence is HIGH affinity (very relevant to procurement). Surveillance is NONE (not applicable). This drives which control types appear most often in Section 4 output.

**Domain Registry:** These are the concrete nouns and verbs that make controls specific:
- Roles like "Vendor Risk Analyst" replace generic "Control Owner"
- Systems like "Third Party Risk Assessment Tool" replace generic "Enterprise System"
- Evidence artifacts like "vendor risk assessment scorecard with sign-off" replace generic "documentation"
- Event triggers like "New vendor engagement" provide realistic timing

**Exemplar Controls:** These show the target quality and style. The exemplar for Section 4 is a Third Party Due Diligence control rated "Strong" at 52 words. Generated controls should match this pattern.

### Step 5: Compare Across Sections

Select **Section 1 -- Vision And Strategy** for contrast. Notice:
- Multiplier is 1.8 (lower than Section 4)
- Roles are C-suite (CEO, CFO, CRO) instead of analysts
- Systems are governance platforms instead of operational tools
- HIGH affinity types are Risk Limit Setting and Authorization (strategic controls)
- The exemplar is a board-level authorization control

This shows how section profiles tailor the same 25 control types to completely different operational contexts.

### Step 6: Trace a Control End-to-End

Now you can trace how one control gets built. Starting from the config:

1. **Scope:** User selects Section 4.0
2. **Hierarchy:** APQC leaf node 4.1.1.1 "Develop procurement plan" is selected
3. **Type:** "Third Party Due Diligence" is chosen (HIGH affinity for Section 4)
4. **Placement:** Must be "Preventive" (per placement_methods.yaml)
5. **Business Unit:** BU-015 gets priority (primary_sections includes "4.0")
6. **Who:** "Vendor Risk Analyst" (from Section 4 registry.roles)
7. **Where:** "Third Party Risk Assessment Tool" (from registry.systems)
8. **When:** "Upon initiation of new vendor engagement" (from registry.event_triggers)
9. **What/Why:** Generated narrative using 5W framework and phrase bank
10. **Evidence:** Derived from registry.evidence_artifacts
11. **Quality:** Rated against exemplar standards

The output is a control like:

```
control_id:       CTRL-0401-THR-002
hierarchy_id:     4.1.1.1
leaf_name:        Develop procurement plan
selected_level_1: Preventive
selected_level_2: Third Party Due Diligence
business_unit:    BU-015 — Third Party Risk Management
who:              Vendor Risk Analyst
what:             Completes vendor due diligence assessment evaluating
                  financial stability, regulatory compliance, cybersecurity
                  posture, business continuity capabilities...
when:             Upon initiation of new vendor engagement
where:            Third Party Risk Assessment Tool
why:              Mitigates third party operational, compliance, and
                  reputational risks...
evidence:         Vendor risk assessment scorecard with risk tier
                  classification, analyst and manager sign-off
quality_rating:   Effective
```

### Step 7: Run the Pipeline

Switch to the **Run Section** sub-tab.

1. **Load APQC data:** If `data/APQC_Template.xlsx` exists, it auto-loads. Otherwise, upload the file. You'll see a summary of total nodes, leaves, and available sections.
2. **Configure the run:**
   - Select target sections (e.g., [4] for Sourcing and Procurement)
   - Set target control count (e.g., 20 for a quick test)
   - Set dry run limit (e.g., 10 to cap output for testing; 0 = no limit)
3. **Click "Run Pipeline":** Watch the progress status as the orchestrator runs through its 3 phases.
4. **Review results:**
   - Metric cards show target vs. generated counts
   - Section Allocation table shows how controls were distributed
   - Plan JSON shows the full planning result
5. **Download:** Use the download buttons to get the Excel file (19-column control records) and/or Plan JSON.

### Step 8: Verify Completeness

A complete Control Taxonomy covers:
- All 13 APQC sections (each with a section profile)
- All 25 control types (defined in taxonomy.yaml)
- All 17 business units (mapped to sections via primary_sections)
- All 3 placements (each with valid Level 2 types per placement_methods.yaml)
- Consistent cross-references (every type in affinity matrices exists in taxonomy, every BU primary_section maps to a real section file)

Use the ControlForge tab to verify:
- **Global Config > Taxonomy Table:** confirm all 25 types have definitions
- **Global Config > Business Units:** confirm all 17 BUs have primary_sections and key_control_types
- **Global Config > Placement & Methods:** confirm all 25 types are classified into exactly one placement
- **Section Profiles:** for each section 1-13, confirm registry has roles/systems/evidence and affinity covers all 25 types across HIGH/MEDIUM/LOW/NONE
- **Run Section:** run the pipeline for each section individually and verify controls match the section's registry vocabulary and affinity priorities

If any section is missing registry data or has incomplete affinity mappings, that section will produce lower-quality or generic controls.
