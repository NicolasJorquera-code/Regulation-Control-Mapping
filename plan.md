# Regulatory Obligation Control Mapper — Complete Build Specification

> **Document type:** Agentic development specification for autonomous coding agent
> **Purpose:** Build a standalone LangGraph project from scratch that maps regulatory obligations to APQC business processes, assesses control coverage, extracts risks, and produces compliance reports
> **Input data:** Located in `data/` subfolder alongside the source code
> **Framework:** LangGraph state machine with typed state, conditional routing, event emission, deterministic fallbacks

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Input Data Specifications](#2-input-data-specifications)
3. [Architecture and Graph Topology](#3-architecture-and-graph-topology)
4. [State Definition](#4-state-definition)
5. [Domain Models](#5-domain-models)
6. [Pipeline Configuration](#6-pipeline-configuration)
7. [Ingest Layer (Deterministic)](#7-ingest-layer)
8. [Agent Specifications](#8-agent-specifications)
9. [Graph Node Implementations](#9-graph-node-implementations)
10. [Validation Rules](#10-validation-rules)
11. [Export Layer](#11-export-layer)
12. [Streamlit UI](#12-streamlit-ui)
13. [Infrastructure Modules](#13-infrastructure-modules)
14. [Testing Strategy](#14-testing-strategy)
15. [File Manifest and Build Order](#15-file-manifest-and-build-order)
16. [Skeleton Patterns (Mandatory)](#16-skeleton-patterns)
17. [Acceptance Criteria](#17-acceptance-criteria)

---

## 1. Project Overview

### What This System Does

A financial institution holds a regulatory obligation inventory (693 obligations from Federal Reserve Regulation YY, parsed into a structured Excel spreadsheet by Promontory). The institution also maintains a control inventory (520+ controls mapped to the APQC Process Classification Framework) and the APQC process hierarchy itself (1,803 process nodes).

This system takes all three inputs and produces:

1. **Classified obligations** — each obligation categorized as Attestation, Documentation, Controls, General Awareness, or Not Assigned (following the Promontory/IBM RCM methodology)
2. **Obligation-to-APQC crosswalk** — a many-to-many mapping between individual obligations and APQC processes at depth 3 (configurable to depth 4), with typed relationships describing HOW the regulation relates to the process
3. **Control coverage assessment** — for each mapped obligation, evaluates whether existing controls adequately cover the requirement using structural matching, semantic evaluation, and relationship-type checking
4. **Gap analysis** — identifies obligations with no control coverage, partial coverage, or full coverage
5. **Risk extraction and scoring** — for uncovered or partially covered obligations, extracts risks and scores them on 4-point impact × likelihood scales
6. **Compliance reports** — exportable matrices and risk registers with full traceability chains

### What This System Does NOT Do

- It does not generate new controls (that is ControlNexus/ControlForge's job — a separate system)
- It does not perform RAG/vector retrieval (all inputs are structured Excel, fully loadable in memory)
- It does not handle unstructured PDF/DOCX regulation parsing (input is pre-parsed Promontory format)
- It does not filter by institutional applicability in this version (all obligations treated as applicable)

### Technology Stack

| Layer | Technology |
|---|---|
| Orchestration | **LangGraph** — StateGraph with TypedDict, conditional edges, add reducers |
| Agent base | BaseAgent ABC with `call_llm()`, `call_llm_with_tools()`, `parse_json()`, deterministic fallback |
| LLM transport | `AsyncTransportClient` — OpenAI-compatible HTTP client with retry, supports ICA (IBM) and OpenAI |
| Models | Pydantic v2 frozen models for every pipeline artifact |
| Config | YAML → Pydantic `PipelineConfig` |
| Events | Protocol-based `EventEmitter` with typed `PipelineEvent` |
| Data processing | pandas + openpyxl for Excel I/O |
| Frontend | Streamlit with live progress, review tables, risk heatmap |
| Export | openpyxl Excel workbooks |
| Testing | pytest with mock transport — all tests run without API keys |

---

## 2. Input Data Specifications

All input files are in the `data/` subfolder.

### 2.1 Regulation Excel — `data/regulations_yy.xlsx`

**Format:** Promontory-format regulatory obligation inventory
**Sheet:** `Requirements` (693 rows × 81 columns)
**Second sheet:** `Definition` (metadata only, not used)

**Columns used by the parser (15 of 81):**

| Column | Type | Example | Purpose |
|---|---|---|---|
| `Citation` | str | `12 CFR 252.34(a)(1)(i)` | Unique obligation identifier |
| `Mandate Title` | str | `Enhanced Prudential Standards (Regulation YY)` | Regulation name (same for all rows) |
| `Abstract` | str | `Enhanced Prudential Standards for BHCs...` | Primary text content for the obligation |
| `Text` | str | (often empty or duplicates Abstract) | Backup text field — use if Abstract is empty |
| `Link` | str | `https://www.ecfr.gov/current/...` | eCFR source URL |
| `Status` | str | `In Force` or `Pending` | 687 In Force, 6 Pending |
| `Title Level 2` | str | `Enhanced Prudential Standards for BHCs With $50B+` | Subpart-level topic name |
| `Title Level 3` | str | `Liquidity risk-management requirements` | Section-level topic name |
| `Title Level 4` | str | `Liquidity risk tolerance` | Sub-section topic |
| `Title Level 5` | str | `Liquidity risk tolerance` | Sub-sub-section topic |
| `Citation Level 2` | str | `Subpart D` | Subpart identifier (15 unique values) |
| `Citation Level 3` | str | `12 CFR 252.34` | Section-level CFR citation (89 unique) |
| `Effective Date` | str | `1-Apr-2021` | When the obligation became effective |
| `Applicability` | str | (often empty) | Applicability notes |
| `Mandate Citation` | str | `12 CFR 252` | Top-level CFR part |

**Data statistics:**

| Metric | Value |
|---|---|
| Total rows | 693 |
| Unique subparts (Citation Level 2) | 15 |
| Unique sections (Citation Level 3) | 89 |
| Average obligations per section | 7.8 |
| Largest section | 12 CFR 252.34 (55 obligations — liquidity risk management) |
| Smallest sections | 1 obligation each |

**Subpart distribution:**

| Subpart | Sections | Rows | Topic |
|---|---|---|---|
| Subpart A | 4 | 11 | General Provisions (authority, definitions) |
| Subpart B | 6 | 60 | Stress tests ($10-50B BHCs) |
| Subpart C | 2 | 19 | Risk committee ($10B+ BHCs) |
| Subpart D | 6 | 112 | Enhanced prudential standards ($50B+ BHCs) |
| Subpart E | 7 | 32 | Supervisory stress tests ($50B+) |
| Subpart F | 8 | 37 | Company-run stress tests ($50B+) |
| Subpart G | 8 | 26 | TLAC/long-term debt (G-SIBs) |
| Subpart H | 9 | 62 | Single-counterparty credit limits |
| Subpart I | 8 | 51 | QFC requirements (G-SIBs) |
| Subpart M | 2 | 9 | Risk committee (FBOs $10-50B) |
| Subpart N | 6 | 26 | Enhanced standards (FBOs, combined <$50B) |
| Subpart O | 7 | 151 | Enhanced standards (FBOs, combined $50B+) |
| Subpart P | 5 | 5 | Covered IHC TLAC |
| Subpart Q | 9 | 81 | Single-counterparty credit limits (FBOs) |
| Subpart U | 2 | 9 | Debt-to-equity limits |

### 2.2 APQC Template — `data/APQC_Template.xlsx`

**Sheet used:** `Combined` (1,803 rows × 6 columns)
**Other sheets:** Per-category sheets (1.0 through 13.0), Categories summary, Introduction, Glossary — not needed for this pipeline.

**Columns:**

| Column | Type | Example |
|---|---|---|
| `PCF ID` | int | `10002` |
| `Hierarchy ID` | str | `11.1.1.1` |
| `Name` | str | `Determine risk tolerance for organization` |
| `Difference Index` | int | (not used) |
| `Change details` | str | (not used) |
| `Metrics available?` | str | (not used) |

**Hierarchy depth:**

| Depth | Example | Count | Level type |
|---|---|---|---|
| 1 (X.0) | 11.0 | 13 | Category |
| 2 (X.Y) | 11.1 | 81 | Process group |
| 3 (X.Y.Z) | 11.1.1 | 310 | Process — **PRIMARY MAPPING TARGET** |
| 4 (X.Y.Z.W) | 11.1.1.1 | 1,224 | Activity |
| 5+ | 11.1.1.1.1 | 188 | Task/sub-task |

**13 top-level categories:**

| ID | Name | Relevance to Reg YY |
|---|---|---|
| 1.0 | Develop Vision and Strategy | Medium — strategic risk governance |
| 2.0 | Develop and Manage Products and Services | Low |
| 3.0 | Market and Sell Products and Services | Low |
| 4.0 | Source and Procure Materials and Services | Low |
| 5.0 | Deliver Services | Low |
| 6.0 | Manage Customer Service | Low |
| 7.0 | Develop and Manage Human Capital | Low — staffing/expertise |
| 8.0 | Manage Information Technology (IT) | Medium — systems, data, reporting |
| 9.0 | Manage Financial Resources | **High** — capital, treasury, liquidity |
| 10.0 | Acquire, Construct, and Manage Assets | Low |
| 11.0 | Manage Enterprise Risk, Compliance, Remediation, and Resiliency | **High** — risk governance, compliance |
| 12.0 | Manage External Relationships | Medium — regulatory relationships |
| 13.0 | Develop and Manage Business Capabilities | Medium — process management |

### 2.3 Control Inventory — `data/section_*__controls.xlsx`

**Format:** Multiple Excel files, one per APQC section, following the naming pattern `section_{N}__controls.xlsx` where N is the APQC top-level category number (1 through 13). Each file has a sheet named `section_{N}_controls`.

**The ingest layer must auto-discover and merge all matching files in the data/ folder.**

**Schema (19 columns, identical across all files):**

| Column | Type | Example |
|---|---|---|
| `control_id` | str | `CTRL-0100-RSK-001` |
| `hierarchy_id` | str | `1.0` or `1.1.1.1` |
| `leaf_name` | str | `Develop Vision and Strategy` |
| `full_description` | str | 30-80 word 5W narrative of the control |
| `selected_level_1` | str | `Preventive` or `Detective` |
| `selected_level_2` | str | Control type (15 types — see below) |
| `business_unit_id` | str | `BU-008` |
| `business_unit_name` | str | `Risk Management` |
| `who` | str | `Chief Risk Officer` |
| `what` | str | Action performed |
| `when` | str | Timing description |
| `frequency` | str | `Annual`, `Quarterly`, `Monthly`, `Daily` |
| `where` | str | System/platform |
| `why` | str | Risk being mitigated |
| `quality_rating` | str | `Strong`, `Effective`, `Satisfactory`, `Needs Improvement` |
| `validator_passed` | bool | True/False |
| `validator_retries` | int | 0-3 |
| `validator_failures` | str | JSON list of failure codes |
| `evidence` | str | Evidence description |

**15 control types (selected_level_2):**

Authorization, Risk Limit Setting, Risk and Compliance Assessments, Verification and Validation, Documentation/Data/Activity Completeness and Appropriateness Checks, Segregation of Duties, Risk Escalation Processes, Internal and External Audits, Automated Rules, Exception Reporting, Training and Awareness Programs, Third Party Due Diligence, System Change Management, Staffing and Resourcing Adequacy, Client Due Diligence and Transaction Monitoring.

**Known data from sections 1 and 2:**

| Metric | Value |
|---|---|
| Section 1 controls | 175 (hierarchy 1.0 — 1.4.3) |
| Section 2 controls | 345 (hierarchy 2.0 — 2.3.3.6) |
| Total known | 520 |
| Unique hierarchy_ids | 177 |
| Controls mentioning risk/compliance in `why` | 471/520 (91%) |

**Sample control record:**

```json
{
  "control_id": "CTRL-0100-RSK-001",
  "hierarchy_id": "1.0",
  "leaf_name": "Develop Vision and Strategy",
  "full_description": "During each annual strategic planning cycle, the Chief Risk Officer establishes enterprise-wide risk appetite thresholds and tolerance limits across credit, market, operational, liquidity, and strategic risk categories using the Board Portal and Governance Platform.",
  "selected_level_1": "Preventive",
  "selected_level_2": "Risk Limit Setting",
  "who": "Chief Risk Officer",
  "what": "Establishes enterprise-wide risk appetite thresholds and tolerance limits",
  "when": "At each annual strategic planning cycle",
  "frequency": "Annual",
  "where": "Board Portal and Governance Platform",
  "why": "To prevent the enterprise from assuming risk exposures that exceed Board-approved appetite levels",
  "evidence": "Board-approved Risk Appetite Statement with quantitative tolerance limits, signed by Chief Risk Officer"
}
```

---

## 3. Architecture and Graph Topology

### Pipeline Phases

```
Phase 1 — INGEST (deterministic, no LLM)
  Parse regulation Excel → 693 Obligation records
  Load APQC hierarchy → 1,803 APQCNode records
  Auto-discover and merge control files → unified control inventory
  Group obligations by section → ~89 ObligationGroups

Phase 2 — CLASSIFY (LLM, per section group)
  For each section group (~89 groups):
    Classify every obligation in the group:
      → Obligation Category: Attestation | Documentation | Controls | General Awareness | Not Assigned
      → Relationship Type (for Controls/Documentation):
          Requires Existence | Constrains Execution | Requires Evidence | Sets Frequency
      → Criticality Tier: High | Medium | Low
  Output: ClassifiedObligation records

  ** Human review checkpoint — analyst reviews classifications in Streamlit + Excel **

Phase 3 — MAP TO APQC (LLM, per section group)
  For each section group containing Controls or Documentation obligations:
    Map obligations to APQC processes at depth 3 (configurable to 4)
    Produce typed relationships (how the obligation constrains the process)
  Output: ObligationAPQCMapping records (many-to-many)

  ** Human review checkpoint — analyst reviews mappings in Streamlit + Excel **

Phase 4 — ASSESS CONTROL COVERAGE (deterministic + LLM)
  For each mapped obligation:
    Layer 1 (deterministic): Structural match — find controls at overlapping APQC hierarchy_ids
    Layer 2 (LLM): Semantic match — does the control's description address the obligation's requirement?
    Layer 3 (LLM): Relationship-type match — does the control satisfy the specific constraint?
      (e.g., if obligation sets frequency "monthly", does the control operate monthly or more?)
    Tag: Covered | Partially Covered | Not Covered
  Output: CoverageAssessment records

Phase 5 — RISK EXTRACTION + SCORING (LLM)
  For obligations tagged Not Covered or Partially Covered:
    Extract 1-3 risks per obligation (what could go wrong)
    Classify into banking risk taxonomy (8 categories, 40+ sub-risks)
    Score on 4-point impact × 4-point frequency scales
  Output: ScoredRisk records with traceability

Phase 6 — FINALIZE + EXPORT (deterministic)
  Assemble: Gap analysis matrix, compliance report, risk register
  Export: Excel workbooks with multiple sheets
```

### LangGraph Topology

```
START → init → ingest → classify_group ─┐
                             ↑            │ has_more_classify_groups?
                             └────────────┘
                                   │ (all classified)
                                   ▼
                          *** HUMAN REVIEW CHECKPOINT ***
                                   │
                                   ▼
                          map_group ─┐
                             ↑       │ has_more_map_groups?
                             └───────┘
                                   │ (all mapped)
                                   ▼
                          *** HUMAN REVIEW CHECKPOINT ***
                                   │
                                   ▼
                          assess_coverage ─┐
                             ↑              │ has_more_assessments?
                             └──────────────┘
                                   │ (all assessed)
                                   ▼
                          extract_and_score ─┐
                             ↑                │ has_more_gaps?
                             └────────────────┘
                                   │ (all scored)
                                   ▼
                            finalize → END
```

**Node count:** 7 (init, ingest, classify_group, map_group, assess_coverage, extract_and_score, finalize)
**Conditional edges:** 4 (one per loop)
**Human review checkpoints:** 2 (after classification, after APQC mapping)
**LLM-calling nodes:** 4 (classify, map, assess, extract_and_score)

### Human Review Implementation

Human review checkpoints are NOT graph pauses. Instead:

1. The graph runs Phase 1-2 (classify) to completion, writes results to `st.session_state`
2. The Streamlit UI renders a review table with Accept/Reject/Edit per row
3. The user can also download an Excel file, edit offline, and re-upload
4. Only after the user clicks "Approve and Continue" does the graph resume with Phase 3
5. Same pattern between Phase 3 and Phase 4

This is implemented as **two separate graph invocations** orchestrated by the Streamlit UI, not as a single graph with a pause. The first graph produces classifications; the user reviews; the second graph consumes the approved classifications and runs mapping → assessment → scoring → finalize.

---

## 4. State Definition

The pipeline uses **two separate state types** for the two graph invocations:

### ClassificationState (Graph 1: Ingest + Classify)

```python
class ClassifyState(TypedDict, total=False):
    # Input
    regulation_path: str
    apqc_path: str
    controls_dir: str                           # folder with section_*__controls.xlsx
    config_path: str

    # Init
    pipeline_config: dict[str, Any]
    risk_taxonomy: dict[str, Any]
    llm_enabled: bool

    # Ingest (deterministic)
    regulation_name: str
    total_obligations: int
    obligation_groups: list[dict[str, Any]]     # ~89 groups
    apqc_nodes: list[dict[str, Any]]            # 1,803 nodes
    controls: list[dict[str, Any]]              # all controls merged

    # Classification loop
    classify_idx: int
    classified_obligations: Annotated[list[dict[str, Any]], operator.add]  # accumulated

    # Errors
    errors: Annotated[list[str], operator.add]
```

### MappingAndAssessmentState (Graph 2: Map + Assess + Score + Finalize)

```python
class AssessState(TypedDict, total=False):
    # Carried from Graph 1 (loaded from session state)
    regulation_name: str
    pipeline_config: dict[str, Any]
    risk_taxonomy: dict[str, Any]
    llm_enabled: bool
    apqc_nodes: list[dict[str, Any]]
    controls: list[dict[str, Any]]

    # Approved classifications (from human review)
    approved_obligations: list[dict[str, Any]]

    # Groups that need APQC mapping (Controls + Documentation categories only)
    mappable_groups: list[dict[str, Any]]

    # Mapping loop
    map_idx: int
    obligation_mappings: Annotated[list[dict[str, Any]], operator.add]

    # Coverage assessment loop
    assess_idx: int
    coverage_assessments: Annotated[list[dict[str, Any]], operator.add]

    # Risk extraction loop (only for Not Covered / Partially Covered)
    gap_obligations: list[dict[str, Any]]
    risk_idx: int
    scored_risks: Annotated[list[dict[str, Any]], operator.add]

    # Final
    risk_register: dict[str, Any]
    gap_report: dict[str, Any]
    compliance_matrix: dict[str, Any]

    # Errors
    errors: Annotated[list[str], operator.add]
```

**Why two states/graphs:** The human review checkpoint between classification and mapping requires persisting intermediate results and letting the user modify them. A single graph cannot pause mid-execution, yield control to a human, accept edits, and resume. Two graph invocations with Streamlit session state bridging them is the clean pattern.

---

## 5. Domain Models

All models use `frozen=True` (immutable after creation). Agents produce new instances, never mutate existing ones.

```python
# ── Ingest artifacts (deterministic) ──

class Obligation(BaseModel, frozen=True):
    """Single row from the regulation Excel."""
    citation: str                       # "12 CFR 252.34(a)(1)(i)"
    mandate_title: str                  # "Enhanced Prudential Standards (Regulation YY)"
    abstract: str                       # Primary text content
    text: str                           # Backup text (use if abstract empty)
    link: str                           # eCFR URL
    status: str                         # "In Force" | "Pending"
    title_level_2: str                  # Subpart topic
    title_level_3: str                  # Section topic
    title_level_4: str                  # Sub-section topic
    title_level_5: str                  # Sub-sub-section topic
    citation_level_2: str               # "Subpart D"
    citation_level_3: str               # "12 CFR 252.34"
    effective_date: str
    applicability: str

class ObligationGroup(BaseModel, frozen=True):
    """Obligations grouped by section for batch LLM processing."""
    group_id: str                       # "Subpart_D__252.34"
    subpart: str                        # "Subpart D"
    section_citation: str               # "12 CFR 252.34"
    section_title: str                  # "Liquidity risk-management requirements"
    topic_title: str                    # Title Level 2
    obligation_count: int
    obligations: list[Obligation]

class APQCNode(BaseModel, frozen=True):
    """Single APQC process hierarchy node."""
    pcf_id: int
    hierarchy_id: str                   # "11.1.1"
    name: str                           # "Establish the enterprise risk framework and policies"
    depth: int                          # 3
    parent_id: str                      # "11.1"

class ControlRecord(BaseModel, frozen=True):
    """Single control from the control inventory."""
    control_id: str                     # "CTRL-0100-RSK-001"
    hierarchy_id: str                   # APQC mapping: "1.0" or "11.1.1.1"
    leaf_name: str
    full_description: str
    selected_level_1: str               # "Preventive" | "Detective"
    selected_level_2: str               # Control type
    who: str
    what: str
    when: str
    frequency: str                      # "Annual" | "Quarterly" | etc.
    where: str
    why: str
    evidence: str
    quality_rating: str
    business_unit_name: str

# ── Classification artifacts (LLM Phase 2) ──

class ClassifiedObligation(BaseModel, frozen=True):
    """An obligation enriched with Promontory-style categorization."""
    citation: str
    abstract: str
    section_citation: str
    section_title: str
    subpart: str

    obligation_category: str            # Attestation | Documentation | Controls | General Awareness | Not Assigned
    relationship_type: str              # Requires Existence | Constrains Execution | Requires Evidence | Sets Frequency | N/A
    criticality_tier: str               # High | Medium | Low
    classification_rationale: str       # 1-2 sentence explanation

# ── APQC Mapping artifacts (LLM Phase 3) ──

class ObligationAPQCMapping(BaseModel, frozen=True):
    """One obligation-to-APQC-process link (many-to-many)."""
    citation: str                       # The obligation
    apqc_hierarchy_id: str              # "11.1.1"
    apqc_process_name: str              # "Establish the enterprise risk framework"
    relationship_type: str              # How the regulation relates to the process
    relationship_detail: str            # Specific constraint description
    confidence: float = Field(ge=0.0, le=1.0)

# ── Coverage Assessment artifacts (Phase 4) ──

class CoverageAssessment(BaseModel, frozen=True):
    """Assessment of whether a control covers a mapped obligation."""
    citation: str                       # The obligation
    apqc_hierarchy_id: str              # The mapped APQC process
    control_id: str | None              # Matched control (None if no match)

    structural_match: bool              # Layer 1: hierarchy overlap
    semantic_match: str                 # Layer 2: "Full" | "Partial" | "None"
    semantic_rationale: str
    relationship_match: str             # Layer 3: "Satisfied" | "Partial" | "Not Satisfied"
    relationship_rationale: str

    overall_coverage: str               # "Covered" | "Partially Covered" | "Not Covered"

# ── Risk artifacts (Phase 5) ──

class ScoredRisk(BaseModel, frozen=True):
    """A risk extracted from an uncovered obligation, scored."""
    risk_id: str
    source_citation: str                # Obligation that created this risk
    source_apqc_id: str                 # APQC process where coverage is missing

    risk_description: str               # 25-50 word description
    risk_category: str                  # From taxonomy: "Operational Risk"
    sub_risk_category: str              # "Process Risk"

    impact_rating: int = Field(ge=1, le=4)
    impact_rationale: str
    frequency_rating: int = Field(ge=1, le=4)
    frequency_rationale: str
    inherent_risk_rating: str           # Derived: Critical | High | Medium | Low

    coverage_status: str                # "Not Covered" | "Partially Covered"

# ── Final output artifacts (Phase 6) ──

class GapReport(BaseModel):
    """The gap analysis output."""
    regulation_name: str
    total_obligations: int
    classified_counts: dict[str, int]   # {Attestation: N, Controls: N, ...}
    mapped_obligation_count: int
    coverage_summary: dict[str, int]    # {Covered: N, Partially: N, Not Covered: N}
    gaps: list[CoverageAssessment]      # Only Not Covered and Partially Covered

class ComplianceMatrix(BaseModel):
    """Full obligation × control × APQC matrix."""
    rows: list[dict[str, Any]]          # One row per obligation

class RiskRegister(BaseModel):
    """Scored risks with full traceability."""
    scored_risks: list[ScoredRisk]
    total_risks: int
    risk_distribution: dict[str, int]   # By category
    critical_count: int
    high_count: int
```

---

## 6. Pipeline Configuration

### `config/default.yaml`

```yaml
name: "reg-obligation-mapper"
description: "Regulatory Obligation → APQC → Control Coverage → Risk Scoring"

# Ingest
active_statuses:
  - "In Force"
  - "Pending"
control_file_pattern: "section_*__controls.xlsx"

# Classification
obligation_categories:
  - "Attestation"
  - "Documentation"
  - "Controls"
  - "General Awareness"
  - "Not Assigned"

relationship_types:
  - "Requires Existence"
  - "Constrains Execution"
  - "Requires Evidence"
  - "Sets Frequency"
  - "N/A"

criticality_tiers:
  - "High"
  - "Medium"
  - "Low"

# Categories that require APQC mapping and control coverage assessment
actionable_categories:
  - "Controls"
  - "Documentation"
  - "Attestation"

# APQC mapping
apqc_mapping_depth: 3                  # Map to depth 3 (X.Y.Z). Change to 4 for activity-level.
max_apqc_mappings_per_obligation: 5

# Control coverage
coverage_thresholds:
  semantic_match_min_confidence: 0.6
  frequency_tolerance: 1               # Allow 1 tier less frequent (e.g., quarterly for monthly)

# Risk extraction
min_risks_per_gap: 1
max_risks_per_gap: 3

# Risk scoring (4-point scales from SCB framework)
impact_scale:
  1:
    label: "Minor"
    financial: "<5% annual pre-tax income or <$1B outflow"
    operational: "Non-critical activity impact"
    reputational: "Employee-level coverage"
  2:
    label: "Moderate"
    financial: "5-25% annual pre-tax income or $1-3B outflow"
    operational: "<1 day critical activity impact"
    reputational: "Localised media"
  3:
    label: "Major"
    financial: "1-2 quarters pre-tax income or $3-5B outflow"
    operational: "1 day partial failure"
    reputational: "National/short-term media"
  4:
    label: "Severe"
    financial: ">=2 quarters pre-tax income or >=$5B outflow"
    operational: ">1 day critical system failure"
    reputational: "National media, cease and desist"

frequency_scale:
  1:
    label: "Remote"
    frequency: "Once every 3+ years"
  2:
    label: "Unlikely"
    frequency: "Once every 1-3 years"
  3:
    label: "Possible"
    frequency: "Once per year"
  4:
    label: "Likely"
    frequency: "Once per quarter or more"

# Output
risk_id_prefix: "RISK"
```

### `config/risk_taxonomy.json`

The SCB banking risk taxonomy — 8 categories with 40+ sub-risks:

```json
{
  "Credit Risk": {
    "description": "Risk of loss arising from a borrower or counterparty failing to meet its obligations.",
    "sub_risks": ["Commercial Credit Risk", "Consumer Credit Risk"]
  },
  "Operational Risk": {
    "description": "Risk of loss from inadequate or failed internal processes, people, systems, or external events.",
    "sub_risks": [
      "Technology Risk", "Information Security Risk", "Third Party Risk",
      "Data Management Risk", "External Fraud Risk", "Business Continuity Risk",
      "Process Risk", "Model Risk", "People Risk", "Change Management Risk",
      "Execution Risk", "Internal Fraud Risk"
    ]
  },
  "Market Risk": {
    "description": "Risk of loss from adverse movements in market prices or rates.",
    "sub_risks": ["Commodity Risk", "Counterparty Risk", "FX Risk", "Equity Risk"]
  },
  "Compliance Risk": {
    "description": "Risk from failure to comply with laws and regulations.",
    "sub_risks": ["Conduct Risk", "Regulatory Compliance Risk", "Financial Crimes Risk"]
  },
  "Strategic Risk": {
    "description": "Risk to earnings from adverse business decisions or improper strategy implementation.",
    "sub_risks": ["Capital Adequacy Risk", "New Business Initiatives Risk", "Competitive Risk", "Business Model Risk"]
  },
  "Reputational Risk": {
    "description": "Risk from negative public perception.",
    "sub_risks": ["Media Risk", "Political Risk", "Social and Public Risk"]
  },
  "Interest Rate Risk": {
    "description": "Risk from interest rate changes affecting assets and liabilities.",
    "sub_risks": ["Balance Sheet Management Risk", "Basis Risk", "Repricing Risk", "Yield Curve Risk"]
  },
  "Liquidity Risk": {
    "description": "Risk of inability to meet obligations as they become due.",
    "sub_risks": ["Collateral Risk", "Deposit Risk", "Funding Gap Risk", "Market Liquidity Risk", "Contingency Funding Risk"]
  }
}
```

---

## 7. Ingest Layer

All ingest is deterministic (no LLM calls). Pure Python + pandas.

### 7.1 `ingest/regulation_parser.py`

**Functions:**

```python
def parse_regulation_excel(path: str) -> tuple[str, list[Obligation]]:
    """Parse Promontory-format regulation Excel.
    Read 'Requirements' sheet. Extract 15 key columns.
    Return (regulation_name, list_of_693_obligations).
    Handle: NaN values → empty strings, 'nan' string → empty."""

def group_obligations(obligations: list[Obligation]) -> list[ObligationGroup]:
    """Group by (Citation Level 2, Citation Level 3).
    Returns ~89 groups. Each group gets:
      group_id: '{subpart}__{section_number}' e.g. 'Subpart_D__252.34'
      All obligations in that section bundled together."""
```

### 7.2 `ingest/apqc_loader.py`

**Functions:**

```python
def load_apqc_hierarchy(path: str) -> list[APQCNode]:
    """Parse 'Combined' sheet → 1,803 APQCNode objects.
    Compute depth from hierarchy_id dot-count.
    Compute parent_id by stripping last segment."""

def build_apqc_summary(nodes: list[APQCNode], max_depth: int = 3) -> str:
    """Build indented text summary for LLM prompts.
    Only includes nodes up to max_depth. Returns ~400 lines.
    Used in APQC mapping agent prompts."""

def get_apqc_subtree(nodes: list[APQCNode], root_id: str) -> list[APQCNode]:
    """Get all descendants of a given hierarchy_id.
    Used for structural matching in coverage assessment."""
```

### 7.3 `ingest/control_loader.py`

**Functions:**

```python
def discover_control_files(directory: str, pattern: str = "section_*__controls.xlsx") -> list[str]:
    """Glob for control files matching the pattern. Return sorted file paths."""

def load_and_merge_controls(file_paths: list[str]) -> list[ControlRecord]:
    """For each file:
      - Detect sheet name (pattern: section_{N}_controls)
      - Read the sheet into DataFrame
      - Convert each row to ControlRecord
    Concatenate all into a single list. Deduplicate by control_id.
    Return unified control inventory."""

def build_control_index(controls: list[ControlRecord]) -> dict[str, list[ControlRecord]]:
    """Index controls by APQC hierarchy_id for fast structural matching.
    Key: hierarchy_id prefix (e.g. '11.1' matches controls at 11.1, 11.1.1, 11.1.1.1).
    Used by the coverage assessment node."""
```

---

## 8. Agent Specifications

### 8.1 Base Agent (copy from skeleton)

Use the exact `BaseAgent` ABC from the skeleton project. It provides:

- `async execute(**kwargs) -> dict[str, Any]` — abstract method
- `call_llm(system_prompt, user_prompt) -> str` — simple LLM call
- `call_llm_with_tools(messages, tools, tool_executor, max_tool_rounds) -> dict` — tool-calling loop
- `parse_json(text) -> dict` — robust JSON extraction (handles markdown fences, trailing text)
- `AgentContext` dataclass (client, model, temperature, max_tokens)
- `@register_agent` decorator → `AGENT_REGISTRY`

Key features that MUST be preserved:
- Returns empty string/dict when `context.client is None` (deterministic mode)
- `parse_json()` tries: direct parse → strip markdown fences → regex `{...}` extraction
- `call_llm_with_tools()` loops up to `max_tool_rounds`, appending tool results

### 8.2 ObligationClassifierAgent

**Role:** Takes one ObligationGroup and classifies every obligation in it.

**System prompt:**

```
You are a regulatory compliance analyst specializing in regulatory change management for financial institutions.

You are classifying regulatory obligations using the Promontory/IBM RCM methodology.

For each obligation, determine:

1. OBLIGATION CATEGORY (exactly one):
   - Attestation: Requires senior management sign-off, certification, or board approval
   - Documentation: Requires maintenance of written policies, procedures, plans, or records
   - Controls: Requires evidence of operating processes, controls, systems, or monitoring
   - General Awareness: Is principle-based, definitional, or provides general authority with no explicit implementation requirement
   - Not Assigned: Is a general requirement not directly actionable

2. RELATIONSHIP TYPE (for Attestation, Documentation, and Controls only; "N/A" for General Awareness and Not Assigned):
   - Requires Existence: The regulation requires a specific function, committee, role, or process to exist
   - Constrains Execution: The regulation imposes specific requirements on HOW a process must be performed (e.g., board approval, independence, specific methodology)
   - Requires Evidence: The regulation requires documentation, reports, or records to be produced and maintained
   - Sets Frequency: The regulation specifies how often an activity must be performed (e.g., "at least quarterly", "annually")

3. CRITICALITY TIER:
   - High: Violation would likely trigger enforcement action, consent order, or MRA
   - Medium: Violation would result in supervisory criticism or examination findings
   - Low: Violation would be noted as an observation or best-practice gap

Respond ONLY with JSON:
{
  "classifications": [
    {
      "citation": "12 CFR 252.34(a)(1)(i)",
      "obligation_category": "Controls",
      "relationship_type": "Constrains Execution",
      "criticality_tier": "High",
      "classification_rationale": "Requires the board to approve liquidity risk tolerance annually, imposing a specific governance constraint on the risk management process."
    }
  ]
}
```

**User prompt:**

```
Classify each obligation in this regulatory section:

REGULATION: {regulation_name}
SECTION: {section_citation} — {section_title}
SUBPART: {subpart} — {topic_title}

OBLIGATIONS ({count}):
{for each obligation in group:}
  - {citation}: {title_level_3} | {title_level_4} | {title_level_5}
    {abstract[:300]}
{end for}

Classify ALL {count} obligations. Return one classification per obligation.
```

**Deterministic fallback:**
- Title contains "definitions", "authority" → General Awareness
- Title contains "must", "shall", "require" → Controls, High
- Title contains "report", "submit", "disclose" → Documentation, Medium
- Otherwise → Not Assigned, Low

### 8.3 APQCMapperAgent

**Role:** Takes classified obligations (Controls/Documentation/Attestation only) from one section group and maps each to APQC processes.

**System prompt:**

```
You are mapping regulatory obligations to business processes using the APQC Process Classification Framework (PCF).

For each obligation, identify 1-{max_mappings} APQC processes that the obligation constrains or requires. Map to depth {depth} (format: X.Y.Z).

APQC PROCESS HIERARCHY:
{apqc_summary_text}

For each mapping, specify:
- The APQC hierarchy_id and process name
- The relationship_type: Requires Existence | Constrains Execution | Requires Evidence | Sets Frequency
- A specific relationship_detail describing WHAT the regulation requires OF that process
- A confidence score (0.0 to 1.0)

RULES:
- Prefer specific processes over general ones. "11.1.1 Establish enterprise risk framework" is better than "11.0 Manage Enterprise Risk."
- An obligation CAN map to multiple processes (many-to-many is expected).
- Relationship_detail must be specific: NOT "relates to risk management" but "requires the board to approve risk tolerance levels at least annually."
- If no APQC process fits, map to the closest match with low confidence.

Respond ONLY with JSON:
{
  "mappings": [
    {
      "citation": "12 CFR 252.34(a)(1)(i)",
      "apqc_hierarchy_id": "11.1.1",
      "apqc_process_name": "Establish the enterprise risk framework and policies",
      "relationship_type": "Constrains Execution",
      "relationship_detail": "Board must approve acceptable level of liquidity risk at least annually, taking into account capital structure, risk profile, complexity, activities, and size.",
      "confidence": 0.92
    }
  ]
}
```

**User prompt:**

```
Map the following regulatory obligations to APQC processes:

REGULATION: {regulation_name}
SECTION: {section_citation} — {section_title}

OBLIGATIONS TO MAP ({count}):
{for each classified obligation where category in [Controls, Documentation, Attestation]:}
  - {citation} [{obligation_category}, {relationship_type}, {criticality_tier}]:
    {abstract[:300]}
{end for}

Produce mappings for ALL listed obligations.
```

**Deterministic fallback:** Map all obligations in a section to the most likely APQC category based on keyword matching against section titles (e.g., "liquidity" → 9.x, "risk committee" → 11.x, "stress test" → 9.x + 11.x).

### 8.4 CoverageAssessorAgent

**Role:** Takes one obligation + its APQC mapping + candidate controls (from structural match) and evaluates whether the controls satisfy the obligation.

**System prompt:**

```
You are evaluating whether existing internal controls adequately cover a specific regulatory obligation.

EVALUATION LAYERS:

Layer 1 — STRUCTURAL MATCH (already completed, provided below):
Controls were found at APQC hierarchy nodes that overlap with the obligation's mapped processes.

Layer 2 — SEMANTIC MATCH:
Does the control's description, purpose ('why' field), and action ('what' field) substantively address what the obligation requires?
Rate: "Full" (directly addresses), "Partial" (related but incomplete), "None" (unrelated despite structural match)

Layer 3 — RELATIONSHIP TYPE MATCH:
The obligation has a specific relationship type. Does the control satisfy it?
- If "Requires Existence": Does the control demonstrate the required function/role/committee exists?
- If "Constrains Execution": Does the control enforce the specific constraint (e.g., board approval, independence)?
- If "Requires Evidence": Does the control produce the required documentation/reports?
- If "Sets Frequency": Does the control operate at the required frequency or more often?
Rate: "Satisfied" | "Partial" | "Not Satisfied"

OVERALL COVERAGE:
- "Covered": Semantic=Full AND Relationship=Satisfied
- "Partially Covered": Semantic=Partial OR Relationship=Partial
- "Not Covered": Semantic=None OR Relationship=Not Satisfied OR no structural matches

Respond ONLY with JSON:
{
  "semantic_match": "Partial",
  "semantic_rationale": "The control addresses risk appetite thresholds broadly but does not specifically address liquidity risk tolerance as required by this obligation.",
  "relationship_match": "Partial",
  "relationship_rationale": "The control operates annually which meets the frequency requirement, but it covers enterprise-wide risk appetite rather than specifically liquidity risk tolerance.",
  "overall_coverage": "Partially Covered"
}
```

**User prompt:**

```
Evaluate control coverage for this regulatory obligation:

OBLIGATION: {citation}
REQUIREMENT: {abstract}
OBLIGATION CATEGORY: {obligation_category}
RELATIONSHIP TYPE: {relationship_type}
CRITICALITY: {criticality_tier}
MAPPED APQC PROCESS: {apqc_hierarchy_id} — {apqc_process_name}

CANDIDATE CONTROL:
  ID: {control_id}
  APQC: {control_hierarchy_id} — {leaf_name}
  Type: {selected_level_2}
  Description: {full_description}
  Who: {who}
  What: {what}
  When: {when} (Frequency: {frequency})
  Where: {where}
  Why: {why}
  Evidence: {evidence}

Evaluate whether this control covers the obligation.
```

If no candidate controls are found (structural match returns empty), skip the LLM call and directly tag as "Not Covered" (deterministic).

If multiple candidate controls are found at the same APQC node, evaluate the BEST match. If ANY control provides full coverage, the obligation is Covered.

**Deterministic fallback:** Structural match only. If hierarchy overlap exists → "Partially Covered". If no overlap → "Not Covered".

### 8.5 RiskExtractorAndScorerAgent

**Role:** Takes an uncovered or partially covered obligation and extracts + scores risks in one call.

**System prompt:**

```
You are a senior risk analyst at a large financial institution.

For the given regulatory obligation that lacks adequate control coverage, identify the risks that arise from non-compliance.

RISK TAXONOMY (classify each risk into exactly one category and sub-category):
{risk_taxonomy_formatted}

IMPACT SCALE (1-4):
{impact_scale_formatted}

FREQUENCY/LIKELIHOOD SCALE (1-4):
{frequency_scale_formatted}

For each risk:
1. Write a 25-50 word risk description (what could go wrong)
2. Classify into a risk_category and sub_risk_category from the taxonomy
3. Score impact (1-4) and frequency (1-4) with 2-4 sentence rationales
4. The inherent_risk_rating is derived: impact × frequency. >=12=Critical, >=8=High, >=4=Medium, <4=Low.

Respond ONLY with JSON:
{
  "risks": [
    {
      "risk_description": "...",
      "risk_category": "Compliance Risk",
      "sub_risk_category": "Regulatory Compliance Risk",
      "impact_rating": 3,
      "impact_rationale": "...",
      "frequency_rating": 2,
      "frequency_rationale": "..."
    }
  ]
}
```

**User prompt:**

```
The following regulatory obligation has {coverage_status} control coverage:

OBLIGATION: {citation}
REQUIREMENT: {abstract}
CRITICALITY: {criticality_tier}
MAPPED APQC: {apqc_hierarchy_id} — {apqc_process_name}
COVERAGE GAP: {gap_rationale}

Extract 1-3 risks and score them.
```

**Deterministic fallback:** One generic compliance risk per obligation:
- Criticality High → impact=3, frequency=2
- Criticality Medium → impact=2, frequency=2
- Criticality Low → impact=1, frequency=1

---

## 9. Graph Node Implementations

Follow the skeleton's `research_graph.py` pattern EXACTLY for: module-level caches, `_emit()` helper, `_get_agent()` factory, `_build_context()`, `_get_loop()` for async.

### Graph 1: `classify_graph.py`

```python
# Module-level singletons
_emitter, _llm_client_cache, _agent_cache, _event_loop = ...

def init_node(state): ...
    # Load PipelineConfig, risk_taxonomy, detect LLM

def ingest_node(state): ...
    # parse_regulation_excel → obligations
    # group_obligations → obligation_groups
    # load_apqc_hierarchy → apqc_nodes
    # discover_control_files + load_and_merge_controls → controls
    # Set classify_idx = 0

def classify_group_node(state): ...
    # Get group at state["classify_idx"]
    # Call ObligationClassifierAgent for all obligations in group
    # Append ClassifiedObligation dicts to classified_obligations
    # Increment classify_idx

def has_more_classify_groups(state) -> str:
    # If classify_idx < len(obligation_groups): return "classify_group"
    # Else: return "end_classify"

def end_classify_node(state): ...
    # Summary statistics, emit completion event

def build_classify_graph():
    graph = StateGraph(ClassifyState)
    graph.add_node("init", init_node)
    graph.add_node("ingest", ingest_node)
    graph.add_node("classify_group", classify_group_node)
    graph.add_node("end_classify", end_classify_node)
    graph.add_edge(START, "init")
    graph.add_edge("init", "ingest")
    graph.add_edge("ingest", "classify_group")
    graph.add_conditional_edges("classify_group", has_more_classify_groups)
    graph.add_edge("end_classify", END)
    return graph.compile()
```

### Graph 2: `assess_graph.py`

```python
def map_group_node(state): ...
    # Get next mappable group at state["map_idx"]
    # Call APQCMapperAgent for obligations in the group
    # Append ObligationAPQCMapping dicts
    # Increment map_idx

def has_more_map_groups(state) -> str:
    # If map_idx < len(mappable_groups): return "map_group"
    # Else: return "prepare_assessment" (transition node)

def prepare_assessment_node(state): ...
    # For each mapping, find candidate controls via structural match
    # Build list of (obligation, mapping, candidate_controls) tuples
    # Set assess_idx = 0

def assess_coverage_node(state): ...
    # Get assessment at state["assess_idx"]
    # If candidates exist: call CoverageAssessorAgent
    # If no candidates: directly tag "Not Covered"
    # Append CoverageAssessment dict
    # Increment assess_idx

def has_more_assessments(state) -> str:
    # If assess_idx < total_assessments: return "assess_coverage"
    # Else: return "prepare_risks" (transition node)

def prepare_risks_node(state): ...
    # Filter: only Not Covered and Partially Covered assessments
    # Set risk_idx = 0, gap_obligations = filtered list

def extract_and_score_node(state): ...
    # Get gap at state["risk_idx"]
    # Call RiskExtractorAndScorerAgent
    # Derive inherent_risk_rating from impact × frequency
    # Assign risk_id: RISK-{sequential:03d}
    # Append ScoredRisk dicts
    # Increment risk_idx

def has_more_gaps(state) -> str:
    # If risk_idx < len(gap_obligations): return "extract_and_score"
    # Else: return "finalize"

def finalize_node(state): ...
    # Assemble GapReport, ComplianceMatrix, RiskRegister
    # Export to Excel

def build_assess_graph():
    graph = StateGraph(AssessState)
    graph.add_node("map_group", map_group_node)
    graph.add_node("prepare_assessment", prepare_assessment_node)
    graph.add_node("assess_coverage", assess_coverage_node)
    graph.add_node("prepare_risks", prepare_risks_node)
    graph.add_node("extract_and_score", extract_and_score_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "map_group")
    graph.add_conditional_edges("map_group", has_more_map_groups)
    graph.add_edge("prepare_assessment", "assess_coverage")
    graph.add_conditional_edges("assess_coverage", has_more_assessments)
    graph.add_edge("prepare_risks", "extract_and_score")
    graph.add_conditional_edges("extract_and_score", has_more_gaps)
    graph.add_edge("finalize", END)
    return graph.compile()
```

---

## 10. Validation Rules

Deterministic validation (no LLM) applied at each stage:

```python
def validate_classification(c: dict) -> tuple[bool, list[str]]:
    failures = []
    if c.get("obligation_category") not in VALID_CATEGORIES:
        failures.append("INVALID_CATEGORY")
    if c.get("obligation_category") in ["Controls", "Documentation", "Attestation"]:
        if c.get("relationship_type") not in VALID_RELATIONSHIP_TYPES:
            failures.append("MISSING_RELATIONSHIP_TYPE")
    if c.get("criticality_tier") not in ["High", "Medium", "Low"]:
        failures.append("INVALID_CRITICALITY")
    return (len(failures) == 0, failures)

def validate_mapping(m: dict) -> tuple[bool, list[str]]:
    failures = []
    if not m.get("apqc_hierarchy_id"):
        failures.append("MISSING_APQC_ID")
    if not m.get("relationship_detail"):
        failures.append("MISSING_RELATIONSHIP_DETAIL")
    confidence = m.get("confidence", 0)
    if not (0.0 <= confidence <= 1.0):
        failures.append("INVALID_CONFIDENCE")
    return (len(failures) == 0, failures)

def validate_coverage(a: dict) -> tuple[bool, list[str]]:
    failures = []
    if a.get("overall_coverage") not in ["Covered", "Partially Covered", "Not Covered"]:
        failures.append("INVALID_COVERAGE_STATUS")
    if a.get("semantic_match") not in ["Full", "Partial", "None"]:
        failures.append("INVALID_SEMANTIC_MATCH")
    return (len(failures) == 0, failures)

def validate_risk(r: dict) -> tuple[bool, list[str]]:
    failures = []
    words = len(r.get("risk_description", "").split())
    if words < 20 or words > 60:
        failures.append(f"WORD_COUNT ({words})")
    for field in ["impact_rating", "frequency_rating"]:
        val = r.get(field, 0)
        if not (1 <= val <= 4):
            failures.append(f"INVALID_{field.upper()} ({val})")
    return (len(failures) == 0, failures)

def derive_inherent_rating(impact: int, frequency: int) -> str:
    score = impact * frequency
    if score >= 12: return "Critical"
    if score >= 8: return "High"
    if score >= 4: return "Medium"
    return "Low"
```

---

## 11. Export Layer

### `export/excel_export.py`

```python
def export_gap_report(gap_report: GapReport, path: str):
    """Excel workbook with sheets:
    1. 'Summary' — overview counts and percentages
    2. 'Classified Obligations' — all 693 with categories
    3. 'APQC Mappings' — obligation-to-process crosswalk
    4. 'Coverage Assessment' — control coverage per obligation
    5. 'Gaps' — only Not Covered and Partially Covered
    6. 'Risk Register' — scored risks from gaps
    """

def export_compliance_matrix(matrix: ComplianceMatrix, path: str):
    """Excel with one row per obligation showing:
    citation | category | criticality | apqc_process | control_id | coverage_status | risk_id
    Full traceability chain in a single flat table."""

def export_for_review(data: list[dict], stage: str, path: str):
    """Export intermediate results for human review.
    stage='classification' → obligation classifications
    stage='mapping' → APQC mappings
    Includes an 'approved' column (default True) that the human can toggle."""

def import_reviewed(path: str, stage: str) -> list[dict]:
    """Import human-reviewed Excel back.
    Reads the 'approved' column. Filters to approved=True.
    Returns the approved records."""
```

---

## 12. Streamlit UI

### Tab Layout (5 tabs)

**Tab 1 — Upload & Configure**
- File uploaders: regulation Excel, APQC Excel, control files (multi-file)
- Config display: loaded pipeline settings
- "Start Classification" button → runs Graph 1

**Tab 2 — Classification Review**
- DataFrame of all 693 classified obligations
- Columns: citation, section, category, relationship_type, criticality, rationale
- Color-coded by category (Controls=blue, Documentation=green, Attestation=purple, General Awareness=gray, Not Assigned=red)
- Filter/sort controls
- "Download for Review" button → Excel export
- "Upload Reviewed File" uploader → re-import
- "Approve and Continue to Mapping" button → triggers Graph 2 (mapping phase only)

**Tab 3 — Mapping Review**
- DataFrame of obligation-to-APQC mappings
- Columns: citation, apqc_id, apqc_name, relationship_type, relationship_detail, confidence
- Same download/upload/approve pattern
- "Approve and Run Coverage Assessment" button → continues Graph 2

**Tab 4 — Results**
- Coverage summary cards: N Covered, N Partially, N Not Covered (with percentages)
- 4×4 risk heatmap (matplotlib, reuse SCB pattern): impact × frequency, risks plotted
- Gap analysis table: obligations lacking coverage
- Risk register table: scored risks with traceability
- "Download Full Report" button → Excel workbook with all sheets

**Tab 5 — Traceability**
- Expandable cards per subpart
- Each card shows: section → obligations → APQC mappings → controls → coverage → risks
- Full chain visible for any obligation

### Progress Display

Use the `EventEmitter` pattern during graph execution:
- "Classifying section 12 CFR 252.34 (15 of 89)..."
- "Mapping obligations to APQC processes (23 of 62)..."
- "Assessing control coverage (145 of 312)..."
- "Extracting risks for gap 47 of 89..."

---

## 13. Infrastructure Modules

### `core/transport.py`

Copy the skeleton's `AsyncTransportClient` exactly. Modify `build_client_from_env()`:

```python
def build_client_from_env() -> AsyncTransportClient | None:
    # Priority 1: ICA (IBM Cloud AI)
    if os.environ.get("ICA_API_KEY") and os.environ.get("ICA_BASE_URL"):
        return AsyncTransportClient(
            api_key=os.environ["ICA_API_KEY"],
            base_url=os.environ["ICA_BASE_URL"],
            model=os.environ.get("ICA_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"),
            provider="ica",
        )
    # Priority 2: OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        return AsyncTransportClient(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.environ.get("OPENAI_MODEL_ID", "gpt-4o"),
            provider="openai",
        )
    return None  # Deterministic mode
```

### `core/events.py`

Copy skeleton's events.py. Add domain events:

```python
INGEST_COMPLETED = "ingest_completed"
GROUP_CLASSIFIED = "group_classified"
MAPPING_COMPLETED = "mapping_completed"
COVERAGE_ASSESSED = "coverage_assessed"
RISK_SCORED = "risk_scored"
REVIEW_CHECKPOINT = "review_checkpoint"
```

### `exceptions.py`

```python
class RegRiskError(Exception): ...
class IngestError(RegRiskError): ...
class AgentError(RegRiskError): ...
class TransportError(RegRiskError): ...
class ValidationError(RegRiskError): ...
```

---

## 14. Testing Strategy

**ALL tests run without API keys, external services, or network access.**

### `tests/conftest.py`

```python
@pytest.fixture
def sample_obligations():
    """13 Obligation objects from 12 CFR 252.22 (risk committee requirements)."""

@pytest.fixture
def sample_apqc_nodes():
    """50 APQCNode objects covering sections 1.0, 9.0, 11.0 at depths 1-4."""

@pytest.fixture
def sample_controls():
    """20 ControlRecord objects at various hierarchy_ids."""

@pytest.fixture
def sample_config():
    """PipelineConfig loaded from config/default.yaml."""

@pytest.fixture
def mock_transport():
    """AsyncTransportClient that returns canned JSON responses."""
```

### Test files

| File | Tests |
|---|---|
| `test_ingest.py` | parse_regulation_excel, group_obligations, load_apqc_hierarchy, discover_control_files, load_and_merge_controls |
| `test_classify_graph.py` | Graph 1 compilation, node count, deterministic end-to-end |
| `test_assess_graph.py` | Graph 2 compilation, node count, structural matching, deterministic end-to-end |
| `test_validator.py` | All validation rules, edge cases |
| `test_models.py` | Pydantic model construction, frozen enforcement, serialization |

---

## 15. File Manifest and Build Order

**Total files: 32**

### Phase A — Foundation (no dependencies)

```
1.  pyproject.toml
2.  config/default.yaml
3.  config/risk_taxonomy.json
4.  src/regrisk/__init__.py
5.  src/regrisk/exceptions.py
```

### Phase B — Core (depends on A)

```
6.  src/regrisk/core/__init__.py
7.  src/regrisk/core/events.py
8.  src/regrisk/core/transport.py
9.  src/regrisk/core/models.py
10. src/regrisk/core/config.py
```

### Phase C — Ingest (depends on B)

```
11. src/regrisk/ingest/__init__.py
12. src/regrisk/ingest/regulation_parser.py
13. src/regrisk/ingest/apqc_loader.py
14. src/regrisk/ingest/control_loader.py
```

### Phase D — Agents (depends on B)

```
15. src/regrisk/agents/__init__.py
16. src/regrisk/agents/base.py
17. src/regrisk/agents/obligation_classifier.py
18. src/regrisk/agents/apqc_mapper.py
19. src/regrisk/agents/coverage_assessor.py
20. src/regrisk/agents/risk_extractor_scorer.py
```

### Phase E — Validation (depends on B)

```
21. src/regrisk/validation/__init__.py
22. src/regrisk/validation/validator.py
```

### Phase F — Graphs (depends on all above)

```
23. src/regrisk/graphs/__init__.py
24. src/regrisk/graphs/classify_state.py
25. src/regrisk/graphs/assess_state.py
26. src/regrisk/graphs/classify_graph.py
27. src/regrisk/graphs/assess_graph.py
```

### Phase G — Export + UI (depends on F)

```
28. src/regrisk/export/__init__.py
29. src/regrisk/export/excel_export.py
30. src/regrisk/ui/__init__.py
31. src/regrisk/ui/app.py
```

### Phase H — Tests

```
32. tests/__init__.py
33. tests/conftest.py
34. tests/test_ingest.py
35. tests/test_classify_graph.py
36. tests/test_assess_graph.py
37. tests/test_validator.py
38. tests/test_models.py
39. README.md
```

---

## 16. Skeleton Patterns (MANDATORY)

These patterns come from a production LangGraph application. Violating ANY of them is a build failure.

### Pattern 1: Module-level caches in graph files

```python
_emitter: EventEmitter = EventEmitter()
_llm_client_cache: Any = None
_agent_cache: dict[str, Any] = {}
_event_loop: asyncio.AbstractEventLoop | None = None
```

Agents and LLM clients are built ONCE and reused across all node invocations. Include `reset_caches()` for test isolation.

### Pattern 2: Annotated[list, operator.add] reducers

Any state field that accumulates across loop iterations MUST use the add reducer:

```python
classified_obligations: Annotated[list[dict], operator.add]
```

Without it, each loop iteration OVERWRITES the list instead of appending. This is the most common LangGraph bug.

### Pattern 3: Deterministic fallback

Every agent MUST have a code path when `context.client is None`. When the LLM returns empty string, the agent returns deterministic defaults. ALL tests run in this mode.

### Pattern 4: Event emission

Every node MUST emit events:

```python
def classify_group_node(state):
    _emit(EventType.ITEM_STARTED, f"Classifying {section_citation} ({idx}/{total})")
    ...
    _emit(EventType.GROUP_CLASSIFIED, f"Classified {count} obligations")
```

### Pattern 5: Frozen Pydantic models

All intermediate artifacts are `frozen=True`. Agents produce NEW instances, never mutate existing ones.

### Pattern 6: Config-driven behavior

All thresholds, scales, keywords, category lists, and limits come from `PipelineConfig`. Nothing hardcoded in agent logic.

### Pattern 7: Tool executor closure

If any agent uses tools, they receive a closure:

```python
executor = build_tool_executor(config, apqc_nodes, controls)
result = executor("apqc_search", {"query": "liquidity", "max_depth": 3})
```

### Pattern 8: Conditional edge functions return node names

```python
def has_more_groups(state) -> str:
    if state["classify_idx"] < len(state["obligation_groups"]):
        return "classify_group"
    return "end_classify"
```

Edge functions return a STRING that matches an `add_node()` name. This is explicit routing, not magic.

---

## 17. Acceptance Criteria

The build is complete when:

1. `python -m pytest tests/` passes with 0 failures (no API keys needed)

2. `python -m streamlit run src/regrisk/ui/app.py` launches the 5-tab UI

3. Uploading regulation + APQC + control files and clicking "Start Classification" produces:
   - All 693 obligations classified with category, relationship_type, criticality
   - Classification review table renders in Tab 2
   - Download and re-upload of reviewed Excel works

4. Clicking "Approve and Continue" runs APQC mapping:
   - Obligations tagged Controls/Documentation/Attestation get mapped to APQC processes
   - Mapping review table renders in Tab 3
   - Many-to-many relationships visible with typed relationship details

5. Clicking "Run Coverage Assessment" produces:
   - Control coverage evaluation using all 3 layers (structural, semantic, relationship)
   - Coverage summary: N Covered, N Partially, N Not Covered
   - 4×4 risk heatmap for scored risks
   - Gap analysis table showing uncovered obligations

6. The deterministic mode (no LLM keys) produces complete output with placeholder classifications and default scores

7. The exported Excel workbook contains all 6 sheets:
   - Summary, Classified Obligations, APQC Mappings, Coverage Assessment, Gaps, Risk Register

8. Every risk traces back to: specific CFR citation → APQC process → coverage gap → risk description → impact/frequency score

---

## LLM Call Budget Estimate

| Phase | Agent | Calls | Notes |
|---|---|---|---|
| Classify | ObligationClassifierAgent | ~89 | One per section group |
| Map | APQCMapperAgent | ~62 | One per group with actionable obligations |
| Assess | CoverageAssessorAgent | ~200-400 | One per (obligation × APQC mapping) pair with candidates |
| Score | RiskExtractorAndScorerAgent | ~100-200 | One per uncovered/partially covered obligation |
| **Total** | | **~450-750** | |

With 5 concurrent calls: ~90-150 minutes wall-clock time.
Estimated cost at GPT-4o pricing (~$5/1M input tokens): ~$5-10 per full run.