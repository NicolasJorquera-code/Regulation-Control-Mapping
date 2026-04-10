# Frontend Redesign Specification

> Executive-grade Streamlit UI for the Regulatory Obligation Control Mapper.
> Replaces flat HTML tables with progressive-disclosure cards, master-detail views,
> and a compliance dashboard optimized for banking executives and senior compliance officers.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Component Library](#2-component-library)
3. [Tab-by-Tab Specification](#3-tab-by-tab-specification)
4. [Session State Key Updates](#4-session-state-key-updates)
5. [Data Field Display Reference](#5-data-field-display-reference)
6. [CSS & Styling Specifications](#6-css--styling-specifications)
7. [Migration Plan](#7-migration-plan)
8. [Files Modified](#8-files-modified)

---

## 1. Design Principles

### 1.1 Progressive Disclosure Over Information Dumps

The top layer shows only what executives scan: citation badges, category badges,
criticality indicators, confidence scores. The full obligation text, rationale,
and relationship details appear only on selection or expansion. Executives assess
within seconds; detail is one interaction away.

### 1.2 Five-to-Seven Data Points Per Scannable Row

No row in any view should present more than 7 visible data elements. Dense legal
text is never a table column — it is always a detail layer.

### 1.3 Human-Readable Names as Primary Identifiers

Show `Manage regulatory compliance` not `11.2.2`. Show `§252.44(d)(3)(ii)` not the
full CFR path. Show process names, not hierarchy IDs. IDs appear as secondary/muted
text or tooltips for traceability.

### 1.4 Color as Semantic Signal, Not Decoration

The existing category color map is retained but applied as badges/pills, not
full-row backgrounds:

| Category | Badge Background |
|----------|-----------------|
| Controls | `#CCE5FF` |
| Documentation | `#D4EDDA` |
| Attestation | `#E2D5F1` |
| General Awareness | `#E2E3E5` |
| Not Assigned | `#F8D7DA` |

Coverage status uses the universal red/yellow/green scheme. Confidence scores use
a subtle progress bar or gradient. Risk ratings use Critical=red, High=orange,
Medium=yellow, Low=green.

### 1.5 Compliance Accessible but Not Dominant

The executive sees coverage metrics, risk distribution, and gap counts as the
primary view. Underlying regulatory text, rationale, and methodology details are
one click deep.

### 1.6 Group by the "One" Side, Nest the "Many" Side

In any many-to-many view (obligations → APQC mappings, obligations → risks), the
obligation is the master; mappings/risks are nested detail items. Never repeat the
obligation text on every mapping row.

---

## 2. Component Library

### 2.1 ObligationCard

**Purpose:** Display a single regulatory obligation in a compact, scannable card.

**Visual description (collapsed):** A bordered container with a single row of:
- Abbreviated citation as a monospace badge (e.g., `§252.34(a)(1)(i)`)
- Obligation category as a colored pill badge (background from `CATEGORY_BG`)
- Criticality tier as a severity dot: High = `🔴`, Medium = `🟡`, Low = `⚪`
- One-line truncation of the abstract (first ~80 chars + "…")

**Visual description (expanded / selected):** Adds below the header:
- Full obligation text from the `text` field in a readable, slightly indented block
- Abstract in a muted callout box
- Classification rationale in italic
- Section title as contextual breadcrumb (Level 2 → 3 → 4 → 5)
- Relationship type with explanation

**Data fields displayed:**
| Field | Display | Level |
|-------|---------|-------|
| `citation` | Monospace badge, abbreviated | Always |
| `obligation_category` | Colored pill | Always |
| `criticality_tier` | Severity dot emoji | Always |
| `abstract` | Truncated (~80 chars) | Always (collapsed) |
| `text` | Full block, readable font | Expanded |
| `abstract` (full) | Muted callout | Expanded |
| `classification_rationale` | Italic text | Expanded |
| `relationship_type` | Small badge | Expanded |
| `section_title` | Breadcrumb | Expanded |
| `subpart` | Group header | Context |

**Streamlit implementation:** `st.container(border=True)` with conditional expansion
driven by `st.session_state`. Clicking the card sets a selected index. The left
panel renders collapsed cards; the right panel renders the selected card's full detail.

### 2.2 MappingChip

**Purpose:** Compact card for an APQC mapping nested within an obligation panel.

**Visual description:** A bordered container showing a horizontal layout:
- APQC process name as primary text (bold)
- Hierarchy ID as muted secondary text (e.g., `11.2.2`)
- Relationship type as a small badge
- Confidence as a numeric indicator (e.g., `0.92`) with color:
  ≥0.8 green, 0.5–0.8 amber, <0.5 red
- Relationship detail as subtitle text below

**Data fields:**
| Field | Display | Level |
|-------|---------|-------|
| `apqc_process_name` | Bold primary text | Always |
| `apqc_hierarchy_id` | Muted secondary | Always |
| `relationship_type` | Small badge | Always |
| `confidence` | Colored number | Always |
| `relationship_detail` | Subtitle text | Always (within chip) |

**Streamlit implementation:** `st.container(border=True)` with `st.columns` for
the horizontal layout inside each chip.

### 2.3 CoverageIndicator

**Purpose:** Visual status component for coverage assessment status.

**Three states:**
- **Covered:** `✅ Covered` (green text)
- **Partially Covered:** `⚠️ Partial` (amber text)
- **Not Covered:** `❌ Gap` (red text)

**Streamlit implementation:** Returns an HTML string with appropriate CSS class,
rendered via `st.markdown(unsafe_allow_html=True)`.

### 2.4 RiskScoreCell

**Purpose:** Compact risk display for the risk register.

**Visual description:** Inherent risk rating as a colored badge:
- Critical = red background, white text
- High = orange background, white text
- Medium = yellow background, dark text
- Low = green background, white text

The numeric score (impact × frequency) shown in small text beside the badge.

**Data fields:**
| Field | Display |
|-------|---------|
| `inherent_risk_rating` | Colored badge |
| `impact_rating` × `frequency_rating` | Small numeric |

**Streamlit implementation:** Returns HTML string with CSS class for the badge.

### 2.5 MetricCard

**Purpose:** Consistent top-of-tab summary statistics.

**Visual description:** Uses `st.metric()` with consistent styling. Four cards
in a row for key numbers — total obligations, coverage percentages, risk counts.

**Streamlit implementation:** `st.columns(4)` with `st.metric()` in each column.

### 2.6 FilterBar

**Purpose:** Horizontal row of filter controls replacing the two-column layout.

**Visual description:** A single row of multiselect dropdowns for category,
criticality, coverage status, subpart. Shows a count indicator below:
"Showing N of M obligations".

**Streamlit implementation:** `st.columns([1, 1, 1, 1])` with `st.multiselect()`
in each column, wrapped in a `st.container()`.

---

## 3. Tab-by-Tab Specification

### 3.1 Tab 1: Upload & Configure

**Layout changes from current:**

1. **Remove the Pipeline Configuration panel.** Config is loaded from YAML;
   displaying metrics for APQC depth and max mappings is developer-facing.

2. **Simplify Data Sources.** Auto-load from `data/` by default. Only show
   upload widgets if files aren't detected. For each detected data source
   (Regulation, APQC, Controls), show a compact success indicator with the
   filename and an expandable preview showing column headers, row count, and
   a scrollable sample of 15–20 rows via `st.dataframe`.

3. **Keep the Run Scope section** (All obligations / Filter by subpart / Quick
   sample) with the summary metrics (Groups to Process, Obligations, Est. LLM
   Calls, LLM Provider).

4. **Keep the Resume from Checkpoint** section and Launch button at the bottom.

5. **Remove `StreamlitEventListener`** and all inline progress event rendering.
   Replace with `st.spinner("Running classification pipeline…")` during graph
   invocation. Terminal logging captures detailed progress.

**Wireframe:**

```
┌─────────────────────────────────────────────────────┐
│ 🎭 Demo Mode — Load pre-computed results [Button]   │
├─────────────────────────────────────────────────────┤
│ 📂 Data Sources                                      │
│ ✅ Regulation — RegYY.xlsx (693 obligations) [▶]     │
│ ✅ APQC — APQC_template.xlsx (1,803 nodes)  [▶]     │
│ ✅ Controls — 12 files (520 controls)        [▶]     │
├─────────────────────────────────────────────────────┤
│ 🎯 Run Scope                                        │
│ ○ All obligations  ○ Filter by subpart  ○ Quick      │
│                                                      │
│ Groups: 89 | Obligations: 693 | LLM Calls: 89 | 🟢  │
├─────────────────────────────────────────────────────┤
│ 💾 Resume from Checkpoint                            │
├─────────────────────────────────────────────────────┤
│ [🚀 Start Classification]                           │
└─────────────────────────────────────────────────────┘
```

### 3.2 Tab 2: Classification Review

**Current state (replaced):** Flat HTML table with 7 columns including the full
`abstract` text crammed into a table cell.

**New layout: Master-detail split.**

**Left panel (60% width) — Obligation List:**
- Scrollable list of `ObligationCard` components, one per classified obligation.
- Each card in collapsed state: citation badge, category pill, criticality dot,
  one-line abstract truncation (~80 chars + ellipsis).
- Cards grouped by subpart with a sticky subpart header
  (e.g., "Subpart E — Supervisory Stress Test Requirements").
- Selecting a card highlights it and populates the right panel.
- `FilterBar` above the list: filter by category, criticality, subpart.
  Show count indicator: "Showing 32 of 693 obligations".

**Right panel (40% width) — Obligation Detail:**
- Full detail of the selected obligation.
- Header: citation (large), category pill, criticality badge, subpart breadcrumb.
- Section "Regulatory Text": Full `text` field in a readable, slightly indented
  block. This is the most important content.
- Section "Abstract": Muted callout box.
- Section "Classification": Category with rationale in italic. Relationship type.
  Criticality with explanation.
- Section "Section Context": Section citation, title hierarchy as breadcrumb.

**Below both panels — Actions:**
- Export for Review / Upload Reviewed File buttons in a horizontal row.
- "Approve and Continue to Mapping" primary button.
- Checkpoint save/load controls.

**Wireframe:**

```
┌────── Filter Bar ──────────────────────────────────────┐
│ [Category ▼] [Criticality ▼] [Subpart ▼]  Showing 32  │
├──────────────────────────┬─────────────────────────────┤
│  Obligation List (60%)   │  Obligation Detail (40%)    │
│ ┌──────────────────────┐ │ ┌─────────────────────────┐ │
│ │ Subpart C            │ │ │ §252.34(a)(1)(i)       │ │
│ ├──────────────────────┤ │ │ [Controls] 🔴 High      │ │
│ │ §252.34(a)(1)(i)     │ │ │                         │ │
│ │ [Controls] 🔴 High   │ │ │ ── Regulatory Text ──  │ │
│ │ The board of direct…  │ │ │ "The board of directors│ │
│ ├──────────────────────┤ │ │  of a covered company  │ │
│ │ §252.34(a)(1)(ii)    │ │ │  shall approve and…"   │ │
│ │ [Docs] 🟡 Medium     │ │ │                         │ │
│ │ Each covered compan…  │ │ │ ── Classification ──   │ │
│ ├──────────────────────┤ │ │ Category: Controls      │ │
│ │ §252.34(a)(2)        │ │ │ Rationale: Requires…   │ │
│ │ [Controls] 🔴 High   │ │ │ Relationship: Constrai…│ │
│ │ The risk committee…   │ │ │ Criticality: High      │ │
│ └──────────────────────┘ │ └─────────────────────────┘ │
├──────────────────────────┴─────────────────────────────┤
│ [📥 Download] [📤 Upload] [✅ Approve & Continue]      │
│ 💾 Checkpoint save/load                                │
└────────────────────────────────────────────────────────┘
```

**Streamlit implementation:**
- `st.columns([0.6, 0.4])` for the split.
- Left panel: `st.container(height=600)` for scrollability. Each card uses
  `st.container(border=True)`. Clicking sets `SK.SELECTED_OBLIGATION_IDX`.
- Right panel updates based on `st.session_state[SK.SELECTED_OBLIGATION_IDX]`.
- Grouping by subpart uses `st.subheader` with a divider before each group.

### 3.3 Tab 3: APQC Mapping Review

**Current state (replaced):** Flat table repeating citation on every mapping row.
APQC hierarchy ID as primary identifier.

**New layout: Grouped obligation panels with nested mapping chips.**

**Structure:**
- Obligations displayed as expandable panels grouped by subpart.
- Each panel header: citation badge, category pill, one-line abstract truncation,
  count badge (e.g., "3 mappings").
- Expanding reveals:
  - Obligation abstract in a readable block.
  - Vertical list of `MappingChip` components — one per APQC mapping.
  - Each chip: APQC process name (primary), hierarchy ID (muted), relationship
    type badge, confidence number, relationship detail subtitle.
- Sorting: default by citation. Option to sort by lowest confidence first.

**Summary strip at top:**
- Total obligations mapped, total mappings, average confidence, relationship type
  distribution.

**Below panels — Actions:**
- Export / Import for review.
- Checkpoint controls.

**Wireframe:**

```
┌─────────────────────────────────────────────────────┐
│ Mapped: 24 obligations | 48 mappings | Avg conf: 0.7│
├─────────────────────────────────────────────────────┤
│ ▸ §252.34(a)(1)(i) [Controls] 🔴    3 mappings      │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ┌─ Mapping Chip ──────────────────────────────┐ │ │
│ │ │ Establish enterprise risk framework  11.1.1  │ │ │
│ │ │ [Constrains Execution]        conf: 0.92     │ │ │
│ │ │ Board must approve liquidity risk…           │ │ │
│ │ └─────────────────────────────────────────────┘ │ │
│ │ ┌─ Mapping Chip ──────────────────────────────┐ │ │
│ │ │ Manage treasury operations         9.7.1     │ │ │
│ │ │ [Sets Frequency]                  conf: 0.85 │ │ │
│ │ │ Annual review of liquidity risk…             │ │ │
│ │ └─────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────┘ │
│ ▸ §252.34(a)(1)(ii) [Documentation] 🟡  2 mappings  │
├─────────────────────────────────────────────────────┤
│ [📥 Download] [📤 Upload] [💾 Checkpoint]            │
└─────────────────────────────────────────────────────┘
```

**Streamlit implementation:**
- `st.expander` for each obligation panel.
- Within each expander, `st.container(border=True)` blocks for mapping chips.
- Chips use `st.columns` for horizontal layout.

### 3.4 Tab 4: Results

**Current state (replaced):** Coverage `st.metric` cards, matplotlib heatmap, flat
gap table, flat risk register table.

**New layout: Executive summary dashboard with drill-down.**

**Top section — Key metrics (always visible):**
- Four `MetricCard` components: Total Assessed, Covered (count+%), Gaps (count+%),
  Total Risks.
- Below: horizontal stacked bar showing coverage distribution (green/amber/red)
  with labels.

**Partial results warning:** If `gap_report["_partial"]`, show `st.warning` banner.

**Middle section — Two-column layout:**

Left column (55%) — **Risk Heatmap:**
- 4×4 matplotlib heatmap with improved styling.
- Below: compact risk distribution summary as horizontal mini-bars.

Right column (45%) — **Top Gaps (at a glance):**
- 5–10 highest-severity gaps as compact cards: citation badge, APQC process name,
  `CoverageIndicator`, best control ID.
- "View all gaps" link expands the full table below.

**Bottom section — Detailed tables (expandable):**

Gap Analysis — `st.expander("Gap Analysis — N gaps", expanded=False)`:
- Gaps grouped by coverage status: "Not Covered" first, then "Partially Covered".
- Each gap shows obligation citation, APQC process name, control ID,
  semantic/relationship match badges.
- Rationale text expandable within each entry.

Risk Register — `st.expander("Risk Register — N risks", expanded=False)`:
- Risks grouped by risk category.
- Each risk: risk ID, citation badge, description, `RiskScoreCell`, impact/frequency.
- Expandable: rationale, sub-category, source APQC.

**Full-width bottom — Export:**
- "Download Full Report" button.
- Checkpoint save/load.

**Wireframe:**

```
┌────────────────────────────────────────────────────────┐
│ Total: 32  | ✅ Covered: 8 (25%) | ⚠️ Gaps: 24 (75%) │
│ | Risks: 36                                            │
│ [████████░░░░░░░░░░░░░░░░░░░░░░] 25% / 30% / 45%     │
├────────────────────────────┬───────────────────────────┤
│  Risk Heatmap (55%)        │  Top Gaps (45%)           │
│ ┌────────────────────────┐ │ ┌───────────────────────┐ │
│ │     1  2  3  4         │ │ │ §252.34(a)(1) [Ctrl]  │ │
│ │  4 │  │  │  │██│       │ │ │ APQC: Manage risk     │ │
│ │  3 │  │  │██│  │       │ │ │ ❌ Gap | No controls  │ │
│ │  2 │  │██│  │  │       │ │ ├───────────────────────┤ │
│ │  1 │██│  │  │  │       │ │ │ §252.35(b)(2) [Docs]  │ │
│ └────────────────────────┘ │ │ ⚠️ Partial | CTRL-042 │ │
│ Risk dist: Compliance: 12  │ └───────────────────────┘ │
│            Operational: 8  │ [View all 24 gaps ▼]      │
├────────────────────────────┴───────────────────────────┤
│ ▸ Gap Analysis — 24 gaps                               │
│ ▸ Risk Register — 36 risks                             │
├────────────────────────────────────────────────────────┤
│ [📥 Download Full Report] [💾 Checkpoint]              │
└────────────────────────────────────────────────────────┘
```

### 3.5 Tab 5: Traceability

**Minimal changes.** Developer/analyst-facing, not executive-facing.

Keep the existing structure:
- Run selector dropdown
- Overview metrics (5 columns)
- Event timeline table
- Node execution table + bar chart
- LLM call inspector with expandable details
- Token-by-node chart
- Maintenance controls

**Minor improvements:**
- Add a developer note at the top: "This tab provides developer-level execution
  traces. For compliance review, see Tabs 2–4."
- Use `st.dataframe` instead of custom HTML tables for event timeline and node
  execution views.

---

## 4. Session State Key Updates

New keys introduced by the redesign:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `SK.SELECTED_OBLIGATION_IDX` | `int` | `0` | Selected obligation index in Tab 2 |
| `SK.SELECTED_MAPPING_OBLIGATION_IDX` | `int \| None` | `None` | Selected obligation in Tab 3 |
| `SK.RESULTS_GAP_EXPANDED` | `bool` | `False` | Gap analysis expander state |
| `SK.RESULTS_RISK_EXPANDED` | `bool` | `False` | Risk register expander state |

These are added to `session_keys.py` under a new `# ── UI navigation ──` group.

---

## 5. Data Field Display Reference

| Field | Source | Display Format | Tabs | Disclosure Level |
|-------|--------|---------------|------|-----------------|
| `citation` | Regulation Excel | Monospace badge, abbreviated (e.g., `§252.34(a)(1)`) | 2, 3, 4 | Always visible |
| `text` | Regulation Excel | Full text block, readable font, indented | 2, 3 | On selection/expansion |
| `abstract` | Regulation Excel | Muted callout OR one-line truncation (~80 chars) | 2, 3 | Truncation always; full on selection |
| `obligation_category` | ObligationClassifierAgent | Colored pill badge | 2, 3, 4 | Always visible |
| `criticality_tier` | ObligationClassifierAgent | Severity dot (🔴/🟡/⚪) | 2, 4 | Always visible |
| `relationship_type` | ClassifierAgent / MapperAgent | Small text badge | 2, 3 | Always visible in card; in MappingChip |
| `classification_rationale` | ObligationClassifierAgent | Italic text block | 2 | On selection (right panel) |
| `section_citation` | Regulation Excel | Muted breadcrumb | 2 | On selection |
| `section_title` | Regulation Excel | Breadcrumb text | 2 | On selection |
| `subpart` | Regulation Excel | Section group header | 2, 3 | Always visible as group separator |
| `apqc_hierarchy_id` | APQCMapperAgent | Muted secondary text (e.g., `11.2.2`) | 3, 4 | Secondary — after process name |
| `apqc_process_name` | APQCMapperAgent | Primary text, bold | 3, 4 | Always visible in mapping views |
| `relationship_detail` | APQCMapperAgent | Subtitle text | 3 | Always visible within MappingChip |
| `confidence` | APQCMapperAgent | Colored number (0.0–1.0) | 3 | Always visible in MappingChip |
| `overall_coverage` | CoverageAssessorAgent | CoverageIndicator (green/amber/red) | 4 | Always visible in gap entries |
| `semantic_match` | CoverageAssessorAgent | Small badge (Full/Partial/None) | 4 | On expansion within gap entry |
| `relationship_match` | CoverageAssessorAgent | Small badge (Satisfied/Partial/Not Satisfied) | 4 | On expansion within gap entry |
| `semantic_rationale` | CoverageAssessorAgent | Expandable text block | 4 | On expansion |
| `relationship_rationale` | CoverageAssessorAgent | Expandable text block | 4 | On expansion |
| `control_id` | Control Dataset | Monospace text | 4 | Always visible in gap/coverage views |
| `risk_id` | RiskExtractorAndScorerAgent | Monospace text (e.g., `RISK-001`) | 4 | Always visible in risk register |
| `risk_description` | RiskExtractorAndScorerAgent | Full text (25–50 words) | 4 | Always visible |
| `risk_category` | RiskExtractorAndScorerAgent | Group header text | 4 | Always visible (grouping label) |
| `sub_risk_category` | RiskExtractorAndScorerAgent | Detail text | 4 | On expansion |
| `impact_rating` | RiskExtractorAndScorerAgent | Labeled number (e.g., `Impact: 3 — Major`) | 4 | Always visible in RiskScoreCell |
| `frequency_rating` | RiskExtractorAndScorerAgent | Labeled number (e.g., `Freq: 2 — Unlikely`) | 4 | Always visible in RiskScoreCell |
| `inherent_risk_rating` | Derived (impact × frequency) | Colored badge (Critical/High/Medium/Low) | 4 | Always visible in RiskScoreCell |
| `coverage_status` | CoverageAssessorAgent | CoverageIndicator | 4 | Always visible |
| `impact_rationale` | RiskExtractorAndScorerAgent | Expandable text | 4 | On expansion |
| `frequency_rationale` | RiskExtractorAndScorerAgent | Expandable text | 4 | On expansion |

---

## 6. CSS & Styling Specifications

### 6.1 Retained Styles (Tab 5 Only)

The existing `.wrapped-table-container` and `.wrapped-table` styles are retained
for the Tab 5 trace viewer only where dense table views are appropriate for a
developer audience.

### 6.2 New Styles

```css
/* Category pill badges */
.category-pill {
    display: inline-block;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.8rem;
    font-weight: 500;
    color: #333;
    white-space: nowrap;
}

/* Citation monospace badges */
.citation-badge {
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
    background: #f0f2f6;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.85rem;
    white-space: nowrap;
}

/* Obligation detail panel */
.obligation-detail {
    padding: 1rem;
    border-left: 3px solid #1E88E5;
    margin-bottom: 0.5rem;
}

/* Coverage indicators */
.coverage-covered {
    color: #2e7d32;
    font-weight: 600;
}
.coverage-partial {
    color: #f57f17;
    font-weight: 600;
}
.coverage-gap {
    color: #c62828;
    font-weight: 600;
}

/* Risk score badges */
.risk-critical {
    display: inline-block;
    background: #c62828;
    color: white;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.8rem;
    font-weight: 600;
}
.risk-high {
    display: inline-block;
    background: #ef6c00;
    color: white;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.8rem;
    font-weight: 600;
}
.risk-medium {
    display: inline-block;
    background: #f9a825;
    color: #333;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.8rem;
    font-weight: 600;
}
.risk-low {
    display: inline-block;
    background: #2e7d32;
    color: white;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.8rem;
    font-weight: 600;
}

/* Confidence coloring */
.conf-high { color: #2e7d32; font-weight: 600; }
.conf-medium { color: #f57f17; font-weight: 600; }
.conf-low { color: #c62828; font-weight: 600; }

/* Muted text helper */
.text-muted {
    color: #6c757d;
    font-size: 0.85rem;
}

/* Obligation card selected state */
.card-selected {
    border-left: 3px solid #1E88E5 !important;
    background-color: #f8f9ff;
}

/* Compact card padding override */
div[data-testid="stVerticalBlock"] > div[data-testid="stContainer"] {
    padding: 0.5rem;
}
```

### 6.3 Global CSS Block

The `_TABLE_CSS` constant in `app.py` is renamed to `_GLOBAL_CSS` and extended
to include both the existing table styles (for Tab 5) and all new styles above.

---

## 7. Migration Plan

### Step 1: Add New CSS

Update `app.py`'s global CSS block — additive. Keep existing `.wrapped-table`
styles for Tab 5. Add all new styles from Section 6.2.

### Step 2: Add Session State Keys

Add 4 new keys to `session_keys.py` under `# ── UI navigation ──` group.

### Step 3: Create Component Helpers

Add new functions to `components.py`:
- `render_obligation_card()` — renders a single obligation card (collapsed form)
- `render_obligation_detail()` — renders the right-panel detail view
- `render_mapping_chip()` — renders a mapping chip
- `render_coverage_indicator()` — returns HTML for coverage status
- `render_risk_score_cell()` — returns HTML for risk rating badge
- `render_filter_bar()` — renders the horizontal filter bar
- `render_metric_row()` — renders a row of metric cards
- `format_citation()` — abbreviates a citation for badge display
- `format_confidence()` — returns colored HTML for confidence value
- `criticality_dot()` — returns emoji dot for criticality tier

Keep all existing helpers (`render_html_table`, checkpoint helpers, etc.).

### Step 4: Rewrite upload_tab.py

- Remove Pipeline Configuration panel
- Simplify data source display with compact success indicators
- Keep data previews (already exist as expanders — good)
- Keep Run Scope, checkpoint, and launch sections

### Step 5: Rewrite review_tabs.py

- Tab 2: Master-detail split with ObligationCard list + detail panel
- Tab 3: Grouped panels with nested MappingChip components
- Preserve all pipeline runner functions (`_run_mapping`, `_run_assessment`)

### Step 6: Rewrite results_tab.py

- Executive dashboard with metric cards + stacked bar
- Two-column heatmap + top gaps layout
- Expandable gap analysis and risk register sections
- Preserve export functionality

### Step 7: Update traceability_tab.py

- Add developer note at top
- Use `st.dataframe` for tables (already mostly done)
- Keep existing structure

### Step 8: Update app.py

- Replace `_TABLE_CSS` with `_GLOBAL_CSS`
- No other structural changes needed

### Step 9: Test

- Run full pipeline in deterministic mode
- Verify all 5 tabs render correctly
- Test checkpoint save/load across all stages

---

## 8. Files Modified

| File | Action | Changes |
|------|--------|---------|
| `doc/FRONTEND_REDESIGN.md` | Create | This document |
| `src/regrisk/ui/session_keys.py` | Modify | Add 4 new UI navigation keys |
| `src/regrisk/ui/components.py` | Modify | Add ~10 new component functions, keep existing helpers |
| `src/regrisk/ui/app.py` | Modify | Extend global CSS with new styles |
| `src/regrisk/ui/upload_tab.py` | Modify | Simplify layout, remove config panel display |
| `src/regrisk/ui/review_tabs.py` | Rewrite | Master-detail Tab 2, grouped panels Tab 3 |
| `src/regrisk/ui/results_tab.py` | Rewrite | Executive dashboard layout |
| `src/regrisk/ui/traceability_tab.py` | Minor modify | Add developer note |
