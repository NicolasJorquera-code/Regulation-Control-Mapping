# Analysis Tab: Current Workflow, Bugs, and Tool-Calling Improvement Plan

This document traces the complete execution flow of the **Analysis tab** in the ControlNexus Streamlit UI — from Excel upload through gap analysis to remediation output — explains the two critical bugs encountered, how the current workaround bypasses the graph, and lays out a comprehensive plan for introducing LLM-driven tool calling to make the pipeline autonomous and intelligent.

The core question this document answers: **The codebase has five tools, a LangGraph tool_node, OpenAI function-calling schemas, and a `messages` field on the graph state — but none of it is connected. How did that happen, what would "connected" look like, and what's the concrete plan to get there?**

---

## Table of Contents

1. [The Analysis Tab: What the User Sees](#1-the-analysis-tab-what-the-user-sees)
2. [Step-by-Step Code Flow: Upload to Gap Report](#2-step-by-step-code-flow-upload-to-gap-report)
3. [Step-by-Step Code Flow: Gap Report to Remediation](#3-step-by-step-code-flow-gap-report-to-remediation)
4. [The Three Execution Paths (and Why They Exist)](#4-the-three-execution-paths-and-why-they-exist)
5. [Deep Dive: How Agents Work Today (No Tool Calling)](#5-deep-dive-how-agents-work-today-no-tool-calling)
6. [Deep Dive: The Orchestrator's Pre-Computation Pattern](#6-deep-dive-the-orchestrators-pre-computation-pattern)
7. [Deep Dive: Why the Remediation Graph is a Skeleton](#7-deep-dive-why-the-remediation-graph-is-a-skeleton)
8. [Bug 1: Graph Only Processes assignments[0]](#8-bug-1-graph-only-processes-assignments0)
9. [Bug 2: Frequency Narrative Fails Validation, Merge Produces Nothing](#9-bug-2-frequency-narrative-fails-validation-merge-produces-nothing)
10. [How the Direct-Path Fix Works](#10-how-the-direct-path-fix-works)
11. [The Tool-Calling Infrastructure: Complete Inventory](#11-the-tool-calling-infrastructure-complete-inventory)
12. [What "Tool Calling" Actually Means (Explained Simply)](#12-what-tool-calling-actually-means-explained-simply)
13. [How Tool Calling Would Have Prevented Both Bugs](#13-how-tool-calling-would-have-prevented-both-bugs)
14. [The Graph vs. Orchestrator Duality (Explained in Depth)](#14-the-graph-vs-orchestrator-duality-explained-in-depth)
15. [The Vision: Tool-Calling-Enhanced Analysis Tab](#15-the-vision-tool-calling-enhanced-analysis-tab)
16. [Implementation Plan: 5 Phases to Unified Tool-Calling Pipeline](#16-implementation-plan-5-phases-to-unified-tool-calling-pipeline)
17. [Design Decisions and Rationale](#17-design-decisions-and-rationale)
18. [Verification and Testing Strategy](#18-verification-and-testing-strategy)
19. [Summary: Current vs. Target Architecture](#19-summary-current-vs-target-architecture)

---

## 1. The Analysis Tab: What the User Sees

The Analysis tab has four visual stages:

```
┌─────────────────────────────────────────────────────────┐
│  1. UPLOAD CONTROLS                                     │
│     [Select Excel file]  →  "Ingested 42 controls"     │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  2. RUN GAP ANALYSIS                                    │
│     [Run Gap Analysis]  →  progress spinner             │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  3. GAP ANALYSIS RESULTS                                │
│     Overall Score: 72/100                               │
│     ┌──────────┬──────────┬──────────┬──────────┐       │
│     │ Reg (3)  │ Bal (2)  │ Freq (4) │ Evid (1) │       │
│     └──────────┴──────────┴──────────┴──────────┘       │
│     [Accept All Gaps for Remediation]                   │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  4. REMEDIATION                                         │
│     ☑ Gap 1: SOX Compliance regulatory gap              │
│     ☑ Gap 2: Reconciliation under-represented           │
│     ☑ Gap 3: CTRL-001 frequency Monthly→Daily           │
│     ...                                                 │
│     [Generate Remediation Controls]                     │
│     → Table of generated control records                │
│     → [Download Excel]                                  │
└─────────────────────────────────────────────────────────┘
```

**File:** `src/controlnexus/ui/app.py` — `_render_analysis_tab()` (line 80) orchestrates the four stages.

---

## 2. Step-by-Step Code Flow: Upload to Gap Report

### Step 1: Upload Excel

**Files involved:**
- `src/controlnexus/ui/components/upload.py` — `render_upload_widget()`
- `src/controlnexus/analysis/ingest.py` — `ingest_excel()`

**What happens:**
1. User uploads an `.xlsx` file via `st.file_uploader`.
2. The file is written to a temp path (openpyxl requires a real file).
3. `ingest_excel()` opens the workbook in read-only mode.
4. For each sheet named `section_*`, it:
   - Reads the header row and maps 19 expected column names to indices.
   - For each data row, constructs a `FinalControlRecord` with type coercion for bools, ints, and failure lists.
5. Returns `list[FinalControlRecord]`, stored in `st.session_state["controls"]`.

**Key data transformation:**
```
Excel row → dict of 19 columns → FinalControlRecord (Pydantic model)
```

**No LLM, no tools, no graph involved.** This is pure file parsing.

### Step 2: Run Gap Analysis

**Files involved:**
- `src/controlnexus/ui/components/analysis_runner.py` — `render_analysis_runner()`
- `src/controlnexus/analysis/pipeline.py` — `run_analysis()`
- `src/controlnexus/analysis/scanners.py` — 4 scanner functions

**What happens when the user clicks "Run Gap Analysis":**

1. **Load section profiles** — `_load_section_profiles()` reads `config/sections/section_*.yaml` files and creates `SectionProfile` objects (containing risk profiles, affinity matrices, registries, exemplars).

2. **Run 4 scanners sequentially** — `run_analysis(controls, profiles)` calls:

   **Scanner 1: `regulatory_coverage_scan()`** (Weight: 40%)
   - Groups controls by top-level section (e.g., `hierarchy_id "4.1.2.1"` → section `"4.0"`).
   - For each section, loads its `registry.regulatory_frameworks` (e.g., `["SOX Compliance", "Basel III"]`).
   - For each framework, extracts keyword fragments (words > 3 chars, excluding filler).
   - Scans each control's `why + full_description` for those keywords.
   - If coverage < 60%, creates a `RegulatoryGap(framework, required_theme, current_coverage, severity)`.
   - **Limitation: Keyword matching is naive.** It only checks if words from the framework name appear literally in the control text. It does not understand regulatory requirements semantically.

   **Scanner 2: `ecosystem_balance_analysis()`** (Weight: 25%)
   - For each section, builds an `affinity_map` from the section profile's `AffinityMatrix` (e.g., `Reconciliation → HIGH`, `Surveillance → LOW`).
   - Counts control type distribution and checks against expected ranges: HIGH ≥40%, MEDIUM 20-40%, LOW 5-20%, NONE 0-5%.
   - Flags types outside their expected range as `BalanceGap(control_type, expected_pct, actual_pct, direction)`.

   **Scanner 3: `frequency_coherence_scan()`** (Weight: 15%)
   - For each control, derives frequency from the `when` field via `derive_frequency_from_when()` (regex keyword matching: "daily" → Daily, "monthly" → Monthly, etc.).
   - Compares against type expectations: Reconciliation/Exception Reporting/Automated Rules should be Monthly+; Authorization/V&V/SoD/Risk Escalation should be Quarterly+.
   - Flags mismatches as `FrequencyIssue(control_id, hierarchy_id, expected, actual)`.

   **Scanner 4: `evidence_sufficiency_scan()`** (Weight: 20%)
   - Scores each control's `evidence` field 0-3: artifact name (+1), preparer/sign-off mention (+1), retention location (+1).
   - Controls scoring < 2 are flagged as `EvidenceIssue(control_id, hierarchy_id, issue)`.

3. **Score each dimension** 0-100 and compute weighted overall score.

4. **Assemble `GapReport`** with all gaps, the overall score, and a summary string.

5. **Store in session state** — `st.session_state["gap_report"] = gap_report`, trigger `st.rerun()`.

**Important:** This entire pipeline is **pure Python**. No LLM calls. No tool calls. No graph (the Analysis LangGraph at `graphs/analysis_graph.py` exists but is **not used** by the UI — the UI calls `run_analysis()` directly).

### Step 3: Display Gap Dashboard

**File:** `src/controlnexus/ui/renderers/gap_dashboard.py` — `render_gap_dashboard()`

Renders:
- Overall score banner with color coding.
- 4 dimension cards showing gap counts and weights.
- Expandable lists of individual gaps per dimension.
- "Accept All Gaps for Remediation" button → sets `st.session_state["accepted_gaps"]`.

**No computation here.** Pure rendering of the `GapReport` model.

---

## 3. Step-by-Step Code Flow: Gap Report to Remediation

**File:** `src/controlnexus/ui/components/remediation_runner.py`

This is where the bugs lived, and where tool calling would have the biggest impact.

### Step 1: Gap Selection

`render_remediation_runner()` displays an interactive `st.data_editor` table where the user can check/uncheck individual gaps.

- `_gap_report_to_rows()` flattens the `GapReport` into rows with `selected: True`, `gap_type`, `detail`, `severity`, and the raw gap data fields.
- The editor lets users deselect gaps they don't want to remediate.

### Step 2: Generate Remediation Controls

When the user clicks "Generate Remediation Controls":

1. **Convert selected rows back to gap dict** — `_rows_to_gap_dict()` reconstructs the dictionary structure that `plan_assignments()` expects.

2. **Plan assignments** — `plan_assignments(gap_dict)` (from `remediation/planner.py`) creates an ordered list:
   - Regulatory gaps → one assignment each (highest priority).
   - Balance gaps (under-represented only) → one assignment each.
   - Frequency issues → one assignment each.
   - Evidence issues → one assignment each.

3. **Build records** — `_run_remediation()` iterates over **every** assignment and calls `_build_record()` for each one.

4. **`_build_record()` is fully deterministic** — it uses template strings to generate control records:
   - **Frequency fix:** "The Control Owner updates the execution frequency of control {id} from {actual} to {expected}..."
   - **Evidence fix:** "The Control Owner enhances the evidence documentation for control {id}..."
   - **Regulatory gap:** "The Compliance Officer monitors and validates compliance with {framework}..."
   - **Balance gap:** "The Control Owner performs {control_type} activities..."

5. **Display results** — summary cards, data table, Excel download button.

**Key insight: The current remediation path is 100% deterministic.** No LLM involved. No graph involved. Every generated control follows the exact same template with gap-specific values plugged in. This is by design — it's a working fallback — but it produces generic, low-quality controls.

---

## 4. The Three Execution Paths (and Why They Exist)

This is the root of the architectural confusion. There are **three** separate systems that can all produce remediation control records, but they work differently and exist for historical reasons:

### Path A: The Direct Path (what the Analysis tab UI uses now)

**File:** `src/controlnexus/ui/components/remediation_runner.py`

```
User clicks "Generate Remediation Controls"
    ↓
remediation_runner.py → _run_remediation()
    ↓
planner.plan_assignments(gap_dict)      ← converts gaps into ordered assignments
    ↓
for each assignment:
    _build_record(assignment, index)    ← template-based, no LLM
    ↓
list of deterministic records           ← stored in session state, rendered as table
```

| Aspect | Detail |
|--------|--------|
| **Where used** | Analysis tab remediation section |
| **LLM calls** | Zero |
| **Tool calls** | Zero |
| **Graph involved** | No |
| **Processes all assignments** | Yes (simple `for` loop) |
| **Output quality** | Low — same template for all gaps of the same type |

**Why it exists:** Created as a workaround after the remediation graph's bugs (sections 8-9) made it unusable. It always works because it's purely deterministic.

### Path B: The LangGraph Remediation Graph (broken, unused by any UI)

**File:** `src/controlnexus/graphs/remediation_graph.py`

```
build_remediation_graph().invoke(state)
    ↓
START → planner_node → router_node → spec_agent_node → narrative_agent_node
                                                            ↓
                                                       validator_node
                                                      ↙           ↘
                                            (retry ≤ 3)        (passed)
                                            narrative_agent     enricher_node
                                                                    ↓
                                                             quality_gate_node
                                                                    ↓
                                                               merge_node
                                                                    ↓
                                                              export_node → END
```

| Aspect | Detail |
|--------|--------|
| **Where used** | Nowhere in the UI. Only in unit tests. |
| **LLM calls** | Zero — agent nodes are **stubs** returning hardcoded/template data |
| **Tool calls** | Zero — `tool_node` exists but is **not wired into the graph** |
| **Processes all assignments** | **No** — `router_node` always picks `assignments[0]` (Bug 1) |
| **Output quality** | N/A — frequency paths produce empty output (Bug 2) |

**Why it exists:** Designed as the future LangGraph-native pipeline for gap-driven remediation. The graph topology (nodes, edges, conditional routing, retry loops) is correct and well-designed. But the agent nodes were left as skeleton stubs waiting for real LLM integration, and the `tool_node` was never added to the graph.

### Path C: The Orchestrator (used by the ControlForge tab)

**File:** `src/controlnexus/pipeline/orchestrator.py` (~1,020 lines)

```
Orchestrator(run_config, project_root).execute_planning(config_dir)
    ↓
Phase 0: Load hierarchy, select scope, compute sizing, allocate sections
    ↓
Phase 1: Deterministic defaults (sequential)
     for each assignment:
         pre-compute role, system, trigger, evidence, spec, narrative, enriched
    ↓
Phase 2: LLM enrichment (parallel async, if API key present)
     for each prepared control:
         SpecAgent.execute()     ← real LLM call
         NarrativeAgent.execute() ← real LLM call, with retry on validation failure
         EnricherAgent.execute() ← real LLM call (but nearest_neighbors=[] always)
    ↓
Phase 3: Finalize (sequential)
     merge LLM results with Phase 1 defaults, assign CTRL-IDs, validate, export
```

| Aspect | Detail |
|--------|--------|
| **Where used** | ControlForge tab "Run Section" |
| **LLM calls** | Yes — 3 agents called per control (SpecAgent → NarrativeAgent → EnricherAgent) |
| **Tool calls** | Zero — agents do single LLM call → parse JSON → return |
| **Graph involved** | No — everything is imperative Python with asyncio.gather |
| **Processes all assignments** | Yes (loop over all) |
| **Output quality** | High (when LLM is available), with deterministic fallbacks |

**Why it exists:** Built first for the ControlForge tab's "generate controls from APQC hierarchy" use case. It works well for that purpose but is not designed for gap-driven remediation (Analysis tab).

### Why Three Paths Exist (Historical Evolution)

```
Time →
┌──────────────────┐
│ 1. Orchestrator   │  Built first for ControlForge tab.
│    (orchestrator   │  Has real LLM agents. Works. 1000+ lines.
│     .py)           │
└────────┬─────────┘
         │ "Let's build a proper LangGraph version for remediation"
         ▼
┌──────────────────┐
│ 2. Remediation    │  Designed with correct graph topology.
│    Graph           │  But agent nodes left as stubs.
│    (remediation_   │  tool_node built but never wired in.
│     graph.py)      │  Has two critical bugs.
└────────┬─────────┘
         │ "Graph doesn't work, need something for the Analysis tab now"
         ▼
┌──────────────────┐
│ 3. Direct Path    │  Simple for-loop with template strings.
│    (remediation_   │  Always works. No intelligence.
│     runner.py)     │  Current workaround.
└──────────────────┘
```

The goal is to collapse these three paths into **one**: a unified LangGraph pipeline that uses real agents with tool-calling capability. The Direct Path's reliability merges with the Graph's architecture and the Orchestrator's LLM integration.

---

## 5. Deep Dive: How Agents Work Today (No Tool Calling)

To understand what tool calling would change, you first need to understand exactly how agents work **right now**. Every agent in the system follows exactly the same pattern:

### The Current Pattern: Prompt-In, JSON-Out

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT EXECUTION (e.g., SpecAgent)                          │
│                                                             │
│  1. Orchestrator pre-computes ALL context:                  │
│     • taxonomy_constraints (which L1/L2 pairs are valid)    │
│     • registry (roles, systems, triggers, evidence)         │
│     • placement definitions                                 │
│     • diversity context (available business units)           │
│                                                             │
│  2. Agent packs everything into ONE user prompt:            │
│     user_prompt = json.dumps({                              │
│         "leaf": {...},                                      │
│         "control_type": "Reconciliation",                   │
│         "domain_registry": {roles: [...], systems: [...]},  │
│         "taxonomy_constraints": {level_1_options: [...]},   │
│         "diversity_context": {available_bus: [...]},        │
│     })                                                      │
│                                                             │
│  3. Agent makes ONE LLM call:                               │
│     raw_text = await self.call_llm(system_prompt, user)     │
│                                                             │
│  4. Agent parses JSON from response:                        │
│     result = self.parse_json(raw_text)                      │
│                                                             │
│  5. Return dict                                             │
└─────────────────────────────────────────────────────────────┘
```

### What `call_llm()` Actually Does (Line by Line)

From `src/controlnexus/agents/base.py`:

```python
async def call_llm(self, system_prompt, user_prompt, temperature, max_tokens):
    # 1. Build OpenAI-format message array
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    # 2. Send to transport (which sends HTTP POST to LLM API)
    response_json = await self.client.chat_completion(
        messages=messages,
        temperature=effective_temp,
        max_tokens=effective_max,
        # ← NO tools parameter. The transport doesn't accept one.
    )

    # 3. Extract text content from response
    return self._extract_text_from_openai_style(response_json)
    # Returns a plain string. No tool_calls handling.
```

### What `chat_completion()` Sends to the LLM API

From `src/controlnexus/core/transport.py`:

```python
payload = {
    "model": self.model,
    "temperature": temperature,
    "max_tokens": max_tokens,
    "messages": messages,
    # ← That's it. No "tools" key. No "tool_choice" key.
    # The LLM has NO knowledge that tools exist.
}
```

### What This Means in Practice

The LLM receives a giant JSON blob in the user prompt containing everything it might need — taxonomy constraints, role lists, system lists, regulatory frameworks, exemplars, phrase banks, etc. — and must produce a correct JSON response in a single shot.

**The agent cannot:**
- Say "I'm not sure if 'Detective' is the right L1 for 'Reconciliation' — let me check" → call `taxonomy_validator`
- Say "I need to understand SOX requirements better" → call `regulatory_lookup`
- Say "Are there similar controls I should differentiate from?" → call `memory_retrieval`
- Say "What frequency should a Reconciliation control run at?" → call `frequency_lookup`

Instead, **all of that data is pre-computed and dumped into the prompt**, whether the agent needs it or not.

### The Cost of This Pattern

1. **Prompt bloat:** Every agent gets the entire registry, full taxonomy constraints, all exemplars, all business units — even if it only needs one piece of information. This wastes tokens and can exceed context windows.

2. **No self-correction:** If the agent picks a wrong L1/L2 pair, it has no way to check. The validator catches it _after the fact_, and the retry sends the exact same pre-computed context again (hoping the LLM gets it right this time).

3. **No dynamic context:** The EnricherAgent always receives `nearest_neighbors=[]` (hardcoded at `orchestrator.py` line ~874) because the orchestrator never queries ChromaDB for similar controls. The memory store exists but is completely disconnected from the enrichment flow.

4. **Rigid sequencing:** The orchestrator calls SpecAgent → NarrativeAgent → EnricherAgent in a fixed order. There's no ability for an agent to say "I need spec-level information from a different angle" and go back.

---

## 6. Deep Dive: The Orchestrator's Pre-Computation Pattern

The Orchestrator is a 1,020-line Python class that runs in the ControlForge tab. Understanding how it pre-computes context is essential because the tool-calling plan replaces much of this with on-demand tool calls.

### Phase 1: What Gets Pre-Computed (for Every Single Control)

For each of the N assignments, the orchestrator computes and stores:

```python
prepared.append({
    # From assignment:
    "hierarchy_id":  "4.1.2.1",
    "control_type":  "Reconciliation",

    # From section profile (cycling through lists):
    "role":    profile.registry.roles[i % len(roles)],           # e.g., "Staff Accountant"
    "system":  profile.registry.systems[i % len(systems)],       # e.g., "SAP ERP"
    "trigger": profile.registry.event_triggers[i % len(triggers)],# e.g., "monthly"
    "evidence": f"{artifact} with {role} sign-off, retained in {system}",

    # Pre-computed taxonomy constraints:
    "taxonomy_constraints": {
        "level_1_options": ["Preventive", "Detective", "Contingency Planning"],
        "selected_level_1": "Detective",                         # Pre-chosen!
        "allowed_level_2_for_selected_level_1": ["Reconciliation", "Variance Analysis", ...],
        "level_2_definitions": {"Reconciliation": "Compares two data sources..."},
    },

    # Deterministic baseline outputs:
    "spec": {
        "who": "Staff Accountant",
        "what_action": "Performs reconciliation checks for ...",
        "when": "monthly",
        "where_system": "SAP ERP",
        "why_risk": "Operational and compliance risk mitigation",
        "evidence": "reconciliation report with sign-off...",
    },
    "narrative": {
        "full_description": "monthly, Staff Accountant performs reconciliation...",
    },
    "enriched": {
        "refined_full_description": "...(same as narrative)...",
        "quality_rating": "Satisfactory",
    },
})
```

### Phase 2: What Gets Sent to Each LLM Agent

**SpecAgent receives (user prompt):**
```json
{
  "leaf": {"hierarchy_id": "4.1.2.1", "name": "Reconcile Accounts"},
  "control_type": "Reconciliation",
  "control_type_definition": "Compares two data sources...",
  "domain_registry": {
    "roles": ["Staff Accountant", "Senior Analyst", "Manager", ...],
    "systems": ["SAP ERP", "Oracle Financials", ...],
    "evidence_artifacts": ["reconciliation report", "audit log", ...],
    "regulatory_frameworks": ["SOX Compliance", "Basel III", ...]
  },
  "taxonomy_constraints": {
    "selected_level_1": "Detective",
    "allowed_level_2_for_selected_level_1": [...]
  },
  "diversity_context": {
    "available_business_units": [{...}, {...}, {...}],
    "suggested_business_unit": {"business_unit_id": "BU-001", ...}
  },
  "constraints": [
    "selected_level_1 must be one value from taxonomy_constraints.level_1_options",
    "who must be one role from registry.roles",
    "..."
  ]
}
```

That's a **massive** user prompt. All of `roles`, `systems`, `evidence_artifacts`, `regulatory_frameworks`, `business_units` — dumped in regardless of whether the agent needs all of it for this particular control.

### What Tool Calling Replaces

With tool calling, the SpecAgent prompt shrinks to essential context:

```json
{
  "leaf": {"hierarchy_id": "4.1.2.1", "name": "Reconcile Accounts"},
  "control_type": "Reconciliation",
  "section_id": "4.0"
}
```

And the agent can autonomously decide:
- "I need to verify my L1/L2 selection" → calls `taxonomy_validator("Detective", "Reconciliation")`
- "I need the regulatory context for this section" → calls `regulatory_lookup("SOX Compliance", "4.0")`
- "I need to see what other controls exist for this leaf" → calls `hierarchy_search("4.0", "reconcile")`

The agent only looks up what it actually needs, when it needs it.

---

## 7. Deep Dive: Why the Remediation Graph is a Skeleton

The remediation graph at `src/controlnexus/graphs/remediation_graph.py` has the **right topology** but **fake internals**. Here's exactly what each node does — and doesn't do:

### What "Stub" Means Concretely

**`spec_agent_node()` (line ~74):**
```python
def spec_agent_node(state):
    assignment = state.get("current_assignment", {})
    # Does NOT do this:
    #   spec = await SpecAgent(ctx).execute(leaf=..., control_type=..., ...)
    # Instead, copies fields from the assignment dict:
    spec = {
        "hierarchy_id": assignment.get("hierarchy_id", ""),
        "gap_source": gap_source,
        "framework": assignment.get("framework", ""),
        "control_type": assignment.get("control_type", ""),
        "who": assignment.get("who", "Control Owner"),       # ← hardcoded fallback
        "where_system": assignment.get("where_system", "Enterprise System"),  # ← hardcoded
    }
    return {"current_spec": spec}
```

No LLM call. No tool call. Just copies assignment fields into a spec dict with hardcoded fallbacks.

**`narrative_agent_node()` (line ~87):**
```python
def narrative_agent_node(state):
    # For frequency gaps: returns a ~23-word template string
    # For evidence gaps: returns a ~40-word template string
    # For everything else: returns " ".join(["word"] * 40)  ← literal filler!

    # Does NOT do this:
    #   narrative = await NarrativeAgent(ctx).execute(locked_spec=spec, standards=..., ...)
```

The `" ".join(["word"] * 40)` line is particularly telling — it's a placeholder that produces the string "word word word word..." repeated 40 times, designed to pass the word count validator but containing zero actual control content.

**`enricher_node()` (line ~141):**
```python
def enricher_node(state):
    narrative = state.get("current_narrative", {})
    return {
        "current_enriched": {
            **narrative,
            "quality_rating": "Satisfactory",   # ← always "Satisfactory"
        },
    }
    # Does NOT:
    #   call EnricherAgent.execute()
    #   query ChromaDB for nearest neighbors
    #   actually evaluate quality
```

### Why the Stubs Were Left In

The graph was built as **architecture-first** — get the topology right (nodes, edges, conditional routing, retry logic), then replace each stub with a real agent call later. This is a valid development approach, but the "later" step never happened because:

1. The orchestrator already works and has real agents (ControlForge tab needs it).
2. The Analysis tab needed something _now_, so the Direct Path was created.
3. Wiring real agents into the graph requires solving the tool-calling problem first — without tools, graph nodes would just replicate the orchestrator's pre-compute-everything pattern, offering no advantage.

### What the Graph Topology Gets Right

Despite the stub internals, the graph's topology is well-designed for tool calling:

- **Conditional retry loop:** `validator → (fail?) → narrative_agent → validator` — this is exactly the pattern needed for an LLM agent that can adjust its output based on validation feedback.
- **Quality gate:** `enricher → quality_gate → (weak?) → adversarial_review` — this enables the Adversarial Reviewer to red-team controls before they're finalized.
- **Merge accumulation:** `generated_records: Annotated[list, add]` — the `add` reducer on this field means each `merge_node` appends its result without overwriting previous results.
- **Messages field:** `messages: Annotated[list, add]` — designed for tool-calling message history, waiting to be used.

The fix is not to throw away the graph, but to replace the stub internals with real agent calls and wire in the tool_node.

---

## 8. Bug 1: Graph Only Processes assignments[0]

### Where It Happens

`remediation_graph.py`, `router_node()` (line ~47):

```python
def router_node(state: RemediationState) -> dict[str, Any]:
    assignments = state.get("assignments", [])
    if not assignments:
        return {"current_assignment": {}, "current_gap_source": ""}
    current = assignments[0]   # ← BUG: Always picks the first one
    ...
```

### What Goes Wrong

If `plan_assignments()` produces 6 assignments (e.g., 3 regulatory + 1 balance + 1 frequency + 1 evidence), the graph only processes `assignments[0]`. After the graph reaches `export → END`, it terminates. Assignments 1-5 are never touched.

### Why It Happens

The remediation graph was designed to process **one assignment at a time**. The Architecture.md even states: *"The graph processes one assignment at a time (router picks `assignments[0]`). For multiple gaps, the graph would be invoked iteratively or the router would be extended to loop."* But this iteration/loop was never implemented.

### Root Cause

The graph has no looping mechanism. After `merge → export → END`, there's no edge back to `router` to pick the next assignment. The graph topology is linear, not cyclic.

### How the Direct Path Fixes It

`_run_remediation()` in `remediation_runner.py` uses a simple `for` loop:
```python
for i, assignment in enumerate(assignments):
    record = _build_record(assignment, i)
    generated.append(record)
```
Every assignment gets processed. No graph needed.

---

## 9. Bug 2: Frequency Narrative Fails Validation, Merge Produces Nothing

### Where It Happens

`remediation_graph.py`, `narrative_agent_node()` (line ~87) and `merge_node()` (line ~186).

### The Chain of Failures

Let's say the gap being processed is a frequency issue (e.g., control CTRL-001 should be Daily, not Monthly).

**Step 1:** `narrative_agent_node()` detects `gap_source == "frequency"` and generates a deterministic narrative:

```python
"full_description": f"The {spec.get('who', 'control owner')} updates the control frequency to {fix.get('frequency', 'monthly')} in the {spec.get('where_system', 'enterprise system')} to ensure adequate risk coverage and timely detection."
```

This produces approximately 23 words: *"The control owner updates the control frequency to Daily in the enterprise system to ensure adequate risk coverage and timely detection."*

**Step 2:** `validator_node()` runs the 6-rule validator. Rule 5 (`WORD_COUNT_OUT_OF_RANGE`) requires 30-80 words. 23 words fails.

```python
if word_count < MIN_WORDS or word_count > MAX_WORDS:
    failures.append("WORD_COUNT_OUT_OF_RANGE")
```

**Step 3:** `should_retry()` checks: `validation_passed` is `False`, `retry_count` is 0 (then 1, then 2). Routes back to `narrative_agent`. But `narrative_agent_node()` is deterministic for frequency gaps — it produces the exact same 23-word text every time. Three retries, same failure each time.

**Step 4:** After 3 retries, `should_retry()` returns `"merge"` (fallback). The graph routes directly to `merge_node()`, **skipping `enricher_node()`**.

**Step 5:** `merge_node()` reads `state.get("current_enriched", {})`:
```python
def merge_node(state: RemediationState) -> dict[str, Any]:
    enriched = state.get("current_enriched", {})
    if enriched:
        return {"generated_records": [enriched]}
    return {"generated_records": []}
```

Since `enricher_node()` was skipped, `current_enriched` is never set. An empty dict `{}` is falsy in Python. So `merge_node()` returns `{"generated_records": []}`. Nothing is generated.

### Why It Happens

Two interacting problems:
1. The frequency narrative is too short for the validator's 30-word minimum, and retries don't help because the template is deterministic.
2. The fallback path skips the enricher, so `current_enriched` is never populated, and `merge_node` produces nothing.

### How the Direct Path Fixes It

`_build_record()` in `remediation_runner.py` generates frequency fix narratives with 50+ words by design:

```python
"full_description": (
    f"The Control Owner updates the execution frequency of control "
    f"{control_id} from {actual} to {expected} in the Enterprise "
    f"Control System. This change aligns the control cadence with "
    f"policy requirements and ensures adequate risk coverage. The "
    f"updated frequency provides timely detection and prevention "
    f"of control gaps, supporting ongoing compliance and effective "
    f"risk mitigation across the control ecosystem."
),
```

This always passes the 30-80 word validation window. And there's no enricher dependency — the record is complete by construction.

---

## 10. How the Direct-Path Fix Works

The current fix (`_run_remediation` in `remediation_runner.py`) is clean and effective:

```
User selects gaps
    ↓
_rows_to_gap_dict() → dict matching plan_assignments() input shape
    ↓
plan_assignments(gap_dict) → ordered list of assignments
    ↓
for each assignment:
    _build_record(assignment, index) → complete record dict
    ↓
list[dict] → stored in session state → rendered as table + Excel download
```

**What it sacrifices:** LLM intelligence. Every record is a template with variable substitution. A regulatory gap for SOX and a regulatory gap for Basel III produce structurally identical controls, just with the framework name swapped.

**What it gains:** Reliability. Every gap produces exactly one record. No validation failures. No empty outputs.

---

## 11. The Tool-Calling Infrastructure: Complete Inventory

The codebase has a **fully implemented but entirely unused** tool-calling layer. Every piece exists in isolation — schemas, implementations, a graph-compatible node, a state field for messages — but zero wiring connects them. This section is an exhaustive inventory.

### Layer 1: Tool Schemas (what the LLM would see)

**File:** `src/controlnexus/tools/schemas.py`

These are OpenAI function-calling JSON schemas — the format used by GPT-4, Claude, and other LLMs to understand what tools are available. If these were passed to the LLM via the `tools` parameter, the LLM could choose to call them.

| Tool | Schema Name | Parameters | Purpose |
|------|-------------|------------|---------|
| `taxonomy_validator` | `TAXONOMY_VALIDATOR_SCHEMA` | `level_1: str, level_2: str` | "Is this L1/L2 pair legal?" |
| `regulatory_lookup` | `REGULATORY_LOOKUP_SCHEMA` | `framework: str, section_id: str` | "What does this regulation require in this section?" |
| `hierarchy_search` | `HIERARCHY_SEARCH_SCHEMA` | `section_id: str, keyword: str` | "Find APQC leaves matching this keyword" |
| `frequency_lookup` | `FREQUENCY_LOOKUP_SCHEMA` | `control_type: str, trigger: str` | "How often should this control run?" |
| `memory_retrieval` | `MEMORY_RETRIEVAL_SCHEMA` | `query_text: str, section_id?: str, n?: int` | "Find similar existing controls" |

All five are bundled in `TOOL_SCHEMAS: list[dict]` — ready to be passed to any OpenAI-compatible `tools` parameter.

**Status:** ✅ Complete, tested, **never passed to any LLM call.**

### Layer 2: Tool Implementations (what actually runs when a tool is called)

**File:** `src/controlnexus/tools/implementations.py`

Each tool is a pure Python function that reads from module-level globals (set by `configure_tools()`):

```python
# Module-level globals — must be set before tools are called
_placement_config: dict = {}        # From config/placement_methods.yaml
_section_profiles: dict = {}        # From config/sections/section_*.yaml
_memory: ControlMemory | None = None  # ChromaDB wrapper
_bank_id: str = ""                   # Organization ID for memory collections
```

**`configure_tools()` — Line 24:**
```python
def configure_tools(placement_config, section_profiles, memory=None, bank_id=""):
    global _placement_config, _section_profiles, _memory, _bank_id
    _placement_config = placement_config
    _section_profiles = section_profiles
    _memory = memory
    _bank_id = bank_id
```

**Status:** ✅ All 5 functions implemented and tested. ❌ `configure_tools()` is **never called outside `tests/test_tools.py`**, so in production the globals are always empty dicts/None.

### What Each Tool Implementation Does

**`taxonomy_validator(level_1, level_2)`:**
```python
# Looks up _placement_config["control_taxonomy"]["level_2_by_level_1"]
# Returns: {valid: True} or {valid: False, suggestion: {correct_level_1: "Detective"}}
```
→ Could replace the orchestrator's `_taxonomy_constraints_for_type()` pre-computation and `_sanitize_taxonomy_selection()` post-check.

**`regulatory_lookup(framework, section_id)`:**
```python
# Loads section profile, checks registry.regulatory_frameworks for matches
# Returns: {framework, section_id, required_themes, applicable_types, domain}
```
→ Could replace the Analysis scanner's naive keyword matching with structured lookups.

**`hierarchy_search(section_id, keyword)`:**
```python
# Currently a partial stub — returns section domain info but not actual leaf search
# Returns: {section_id, domain, keyword, available_roles[:5], available_systems[:5], leaves: []}
```
→ Needs APQC template access to return real leaf matches. Currently limited.

**`frequency_lookup(control_type, trigger)`:**
```python
# Uses derive_frequency_from_when() + type-specific expectations
# Returns: {control_type, trigger, derived_frequency, expected_frequency, reasoning}
```
→ Key for Bug 2 fix — provides `reasoning` text that would make narratives richer.

**`memory_retrieval(query_text, section_id, n)`:**
```python
# Queries ChromaDB via _memory.query_similar()
# Returns: {similar_controls: [{document, score, metadata}]}
# WARNING: Returns {error: "Memory not configured"} when _memory is None (always in production)
```
→ This is the critical unconnected piece. The EnricherAgent always receives `nearest_neighbors=[]` because this tool is never called and memory is never initialized outside tests.

### Layer 3: Tool Dispatch Map & Executor

**File:** `src/controlnexus/tools/nodes.py`

```python
TOOL_MAP = {
    "taxonomy_validator": taxonomy_validator,
    "regulatory_lookup":  regulatory_lookup,
    "hierarchy_search":   hierarchy_search,
    "frequency_lookup":   frequency_lookup,
    "memory_retrieval":   memory_retrieval,
}

def execute_tool_call(tool_name: str, arguments: dict) -> dict:
    """Execute one tool by name. Returns result dict or {error: ...}."""
    func = TOOL_MAP.get(tool_name)
    if func is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return func(**arguments)
```

**Status:** ✅ Complete, tested. This is the function that `AgentContext.tool_executor` would point to.

### Layer 4: LangGraph Tool Node

**File:** `src/controlnexus/tools/nodes.py` (line ~47)

```python
def tool_node(state: dict) -> dict:
    """LangGraph node that processes tool_calls from the last message."""
    messages = state.get("messages", [])
    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])

    new_messages = []
    for call in tool_calls:
        tool_name = call["function"]["name"]
        args = json.loads(call["function"]["arguments"])
        result = execute_tool_call(tool_name, args)
        new_messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": json.dumps(result),
        })
    return {"messages": new_messages}
```

This node is designed to be added to a LangGraph `StateGraph` and process tool calls from agent messages. It reads `state["messages"]`, finds tool_calls, executes them, and writes tool results back.

**Status:** ✅ Complete, tested. ❌ **Never added to any graph.** Neither `build_analysis_graph()` nor `build_remediation_graph()` includes this node.

### Layer 5: Graph State Field

**File:** `src/controlnexus/graphs/state.py` (line ~72)

```python
class RemediationState(TypedDict, total=False):
    # ... other fields ...
    messages: Annotated[list[dict[str, Any]], add]  # LLM messages for tool calling
```

The `messages` field exists with the `add` reducer (meaning parallel writes are safe — they concatenate rather than overwrite). It's designed for exactly the tool-calling message pattern:
1. Agent node writes `[system_msg, user_msg, assistant_msg_with_tool_calls]`
2. `tool_node` writes `[tool_result_msg_1, tool_result_msg_2, ...]`
3. Agent node reads all messages, sees tool results, continues reasoning

**Status:** ✅ Exists with correct reducer. ❌ **Never read or written by any node.**

### Layer 6: Transport (the missing link)

**File:** `src/controlnexus/core/transport.py` (line ~63)

```python
async def chat_completion(self, messages, temperature=0.2, max_tokens=1400):
    payload = {
        "model": self.model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
        # ← NO "tools" key
        # ← NO "tool_choice" key
    }
```

This is the **single point of failure** for tool calling. Even if you wired everything else together, the HTTP request to the LLM API never includes tool definitions, so the LLM never knows tools exist and never produces `tool_calls` in its response.

**Status:** ❌ Does not accept a `tools` parameter. This is the first thing that must change.

### Layer 7: Agent Base Class (another missing link)

**File:** `src/controlnexus/agents/base.py`

```python
@dataclass
class AgentContext:
    client: AsyncTransportClient | None = None
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120
    # ← NO tools field
    # ← NO tool_executor field
```

Even if transport accepted tools, agents have no way to specify which tools they want, and no way to execute tool calls when the LLM returns them.

**Status:** ❌ No `tools` field, no `tool_executor` field, no `call_llm_with_tools()` method.

### Complete Disconnection Map

Here's the full picture of what exists and what's missing, read top-to-bottom:

```
LLM API (OpenAI/Anthropic/ICA)
    ▲
    │ HTTP POST with {messages, model, temperature, max_tokens}
    │ ← "tools" parameter is NEVER included (transport.py)
    │
AsyncTransportClient.chat_completion()
    ▲
    │ ← No "tools" param accepted (transport.py:63)
    │
BaseAgent.call_llm()
    ▲
    │ ← No tool-calling loop. Single call → parse JSON → return.
    │    No call_llm_with_tools() method exists.
    │
AgentContext
    │ ← No "tools" field. No "tool_executor" field.
    │
    ╳  DISCONNECT ╳
    │
TOOL_SCHEMAS (schemas.py)        ← Exists, never passed to any agent
TOOL_MAP (nodes.py)              ← Exists, never called by any agent
execute_tool_call (nodes.py)     ← Exists, never referenced by any agent
tool_node (nodes.py)             ← Exists, never added to any graph
configure_tools (impls.py)       ← Exists, never called in production
RemediationState.messages        ← Exists, never read or written
```

Every piece below the `╳ DISCONNECT ╳` line is fully built, tested, and working — but nothing above the line knows it exists.

---

## 12. What "Tool Calling" Actually Means (Explained Simply)

If the above is confusing, here's a simplified explanation of what tool calling is and how it changes the agent execution pattern.

### Without Tool Calling (current state)

Think of calling an LLM agent like giving someone a closed-book exam. You hand them a massive packet of reference material (the prompt), they read it all, write their answer in one shot, and hand it back. If they needed information that wasn't in the packet, they're out of luck — they have to guess.

```
YOU:    "Here's the control type taxonomy, the regulatory frameworks,
         the role list, the system list, the evidence artifacts,
         the business units, and the exemplar controls.
         Write me a control specification."

LLM:    {who: "Staff Accountant", what: "Performs reconciliation...", ...}

Done. One question, one answer.
```

### With Tool Calling (target state)

Now imagine the same exam, but open-book. You tell the person: "Here are the basic facts. If you need to look something up, here are five reference books you can request." They can ask for a specific reference mid-answer, read it, then continue.

```
YOU:    "Here's the basic context: hierarchy leaf 4.1.2.1,
         control type Reconciliation, section 4.0.
         You can use these tools: taxonomy_validator,
         regulatory_lookup, hierarchy_search, frequency_lookup,
         memory_retrieval."

LLM:    "Before I write the spec, let me verify my taxonomy choice."
        → TOOL CALL: taxonomy_validator("Detective", "Reconciliation")

TOOL:   {valid: true}

LLM:    "Good. Now let me check what SOX requires for this section."
        → TOOL CALL: regulatory_lookup("SOX Compliance", "4.0")

TOOL:   {required_themes: ["SOX Compliance"], applicable_types: [...], domain: "financial_reporting"}

LLM:    "Now I know the regulatory context. Let me write the spec."
        {who: "Staff Accountant", what: "Performs daily reconciliation of
         GL accounts to ensure SOX compliance...", ...}

Done. Multiple rounds, each building on tool results.
```

### How It Works Technically (OpenAI Function Calling Protocol)

The tool-calling loop is a standard pattern supported by all major LLM APIs:

```
Round 1:
  YOU → LLM:  {messages: [...], tools: [taxonomy_validator, regulatory_lookup, ...]}
  LLM → YOU:  {tool_calls: [{name: "taxonomy_validator", args: {level_1: "Detective", level_2: "Reconciliation"}}]}

Round 2:
  YOU execute: taxonomy_validator("Detective", "Reconciliation") → {valid: true}
  YOU → LLM:  {messages: [..., tool_result: {valid: true}]}
  LLM → YOU:  {tool_calls: [{name: "regulatory_lookup", args: {framework: "SOX", section_id: "4.0"}}]}

Round 3:
  YOU execute: regulatory_lookup("SOX", "4.0") → {required_themes: [...]}
  YOU → LLM:  {messages: [..., tool_result: {required_themes: [...]}]}
  LLM → YOU:  {content: '{"who": "Staff Accountant", "what": "..."}'}  ← final answer

Done. The LLM decided when to call tools and when to produce the final answer.
```

The key insight: **the LLM decides** which tools to call, in what order, and when to stop. You don't hardcode "call regulatory_lookup then taxonomy_validator." The LLM makes that decision based on the task at hand.

### Where the Loop Lives: BaseAgent vs. Graph

There are two places this loop can run:

**Option A: Inside `BaseAgent.call_llm_with_tools()` (agent-internal loop)**

```python
async def call_llm_with_tools(self, system_prompt, user_prompt, max_rounds=5):
    messages = [system_msg, user_msg]
    for _ in range(max_rounds):
        response = await self.client.chat_completion(messages, tools=self.context.tools)
        if no_tool_calls(response):
            return extract_text(response)          # ← final answer
        messages.append(assistant_msg_with_tool_calls)
        for tool_call in response.tool_calls:
            result = self.context.tool_executor(tool_call.name, tool_call.args)
            messages.append(tool_result_msg)
    return extract_text(response)                   # ← exhausted rounds
```

The agent handles its own tool-calling loop internally. From the graph's perspective, the agent node is still a single step — it just takes longer because there are internal LLM round-trips.

**Option B: LangGraph-native tool loop (graph-external loop)**

```
agent_node → (has_tool_calls?) ──yes──→ tool_node → agent_node  (loop)
                                 │
                                 no
                                 │
                                 ▼
                            next_node
```

The graph controls the loop. The agent node produces a message with tool_calls, a routing function detects tool_calls, routes to `tool_node`, which executes tools and writes results back, then routes back to the agent node.

**Our hybrid approach uses both:** The graph handles the high-level flow (spec → narrative → validator → enricher), while each agent handles its own tool-calling loop internally via `call_llm_with_tools()`. This is simpler to implement and doesn't require separate tool_nodes per agent.

---

## 13. How Tool Calling Would Have Prevented Both Bugs

### Bug 1 (Only processes first assignment)

**Root cause:** The graph is a linear pipeline that terminates at END after processing one assignment. It has no loop edge back to `router` for the next assignment.

**With tool calling + graph unification:** The graph gets a proper assignment loop:

```
planner → router → spec_agent → narrative_agent → validator → enricher
                ▲                                                │
                │                                                ▼
                └──────── (more assignments?) ◀──── merge ─── quality_gate
                                                      │
                                                      ▼ (no more)
                                                    export → END
```

After `merge`, a routing function checks if there are remaining assignments. If yes, it pops the next one and routes back to `router`. If no, it routes to `export → END`.

But even without fixing the graph topology, the shift to tool-calling agents makes the bug less critical, because the `_run_remediation()` direct path already loops correctly and would now call real agents with tools instead of templates.

### Bug 2 (Frequency narrative too short → merge produces nothing)

**Root cause:** A deterministic template produces 23 words; the validator requires 30; retries produce the same text; the fallback path skips enricher; merge gets an empty dict.

**How tool calling prevents this at every failure point:**

1. **23-word template → richer narrative:** Instead of a hardcoded template, the NarrativeAgent (now with real LLM) could call `frequency_lookup("Reconciliation", "monthly")` and receive:
   ```json
   {
     "derived_frequency": "Monthly",
     "expected_frequency": "Daily",
     "reasoning": "'Reconciliation' controls should operate at monthly or higher
                   frequency for timely detection of discrepancies."
   }
   ```
   The LLM uses this `reasoning` to write a 40-50 word narrative that explains the _why_ behind the frequency change, naturally exceeding the 30-word minimum.

2. **Retries now produce different text:** Because the LLM is non-deterministic and receives validation failure feedback (via `build_retry_appendix()`), each retry produces a genuinely different attempt — unlike the deterministic template that produces identical text every time.

3. **Fallback path still produces output:** Even if all 3 retries fail, the fallback `merge` path would now use `current_narrative` (which has real content from the LLM, not an empty dict) rather than depending on `current_enriched` being set by the skipped enricher.

4. **Self-correction via tools:** If the LLM's first attempt is too short, the validation failure message tells it "WORD_COUNT_OUT_OF_RANGE: need 30-80 words." The LLM can then call `frequency_lookup` again or `regulatory_lookup` for additional context to pad its narrative with real substance, not filler words.

---

## 14. The Graph vs. Orchestrator Duality (Explained in Depth)

This section addresses the core architectural question: **should the tool-calling pipeline live in the LangGraph remediation graph, or in the Orchestrator's imperative Python code?**

### The Fundamental Difference

**Orchestrator (imperative):**
```python
# You write the control flow explicitly
spec = await spec_agent.execute(...)
narrative = await narrative_agent.execute(...)
validation = validate(narrative, spec)
if not validation.passed:
    for attempt in range(3):
        narrative = await narrative_agent.execute(..., retry_appendix=...)
        validation = validate(narrative, spec)
        if validation.passed:
            break
enriched = await enricher_agent.execute(...)
```

Control flow is buried in Python `if/for/while` statements. To understand the pipeline, you must read ~200 lines of orchestrator code. To change the flow (e.g., add an adversarial review step), you modify deeply nested imperative code.

**LangGraph (declarative):**
```python
# You declare nodes and edges; the framework handles execution
graph.add_node("spec_agent", spec_agent_fn)
graph.add_node("narrative_agent", narrative_agent_fn)
graph.add_node("validator", validator_fn)
graph.add_node("enricher", enricher_fn)

graph.add_edge("spec_agent", "narrative_agent")
graph.add_edge("narrative_agent", "validator")
graph.add_conditional_edges("validator", should_retry, {
    "enricher": "enricher",
    "narrative_agent": "narrative_agent",
    "merge": "merge",
})
```

The pipeline topology is explicit, visual, and modifiable. Adding a new step means adding a node and an edge, not refactoring nested control flow.

### Why LangGraph Wins for Tool Calling

LangGraph was designed for exactly this pattern: agent produces outputs → conditional routing → tool execution → loop back to agent. Key advantages:

1. **Built-in message state management:** The `messages: Annotated[list, add]` field with the `add` reducer handles message accumulation across nodes safely — even in parallel execution.

2. **Conditional routing is first-class:** `add_conditional_edges()` makes it trivial to route based on `should_retry()`, `has_tool_calls()`, `quality_check()`, etc.

3. **Visual debugging:** `graph.get_graph().draw_mermaid()` renders the entire pipeline as a diagram, making it easy to verify topology.

4. **State checkpointing:** LangGraph supports checkpoints, so you can replay failed runs, inspect state at any point, and debug individual node outputs.

5. **Fan-out/fan-in:** The analysis graph already uses this for running 4 scanners in parallel. The remediation graph could use it for processing multiple assignments concurrently.

### What "Unify on the Graph" Means Concretely

**Currently:**
```
ControlForge tab → Orchestrator → real agents (no tools, no graph)
Analysis tab     → Direct Path   → templates (no agents, no tools, no graph)
Tests            → Remediation Graph → stubs (no real agents, no tools)
```

**After unification:**
```
ControlForge tab ─┐
Analysis tab     ─┼→ Orchestrator (thin wrapper) → Remediation Graph → real agents + tools
Tests            ─┘
```

The Orchestrator shrinks from 1,020 lines to ~200: load config → set up graph state → invoke graph → return results. All agent logic, retry logic, tool calling, routing, and quality gates live in the graph.

### What Happens to the Orchestrator's Pre-Computation

The orchestrator currently pre-computes a lot of useful context (section profiles, taxonomy constraints, registry data). This doesn't disappear — it moves into a `prepare_context` graph node that runs before the agent pipeline:

```
START → planner → prepare_context → router → spec_agent → ...
```

`prepare_context` loads section profiles, taxonomy config, standards, and placement methods, then writes them to the graph state. Agent nodes read essential context from the state and use tools for supplementary lookups. This is the **hybrid** approach: pre-compute the foundation, let agents autonomously fill in details.

---

## 15. The Vision: Tool-Calling-Enhanced Analysis Tab

Here's how the Analysis tab flow would change with tool calling enabled:

### Current Flow (deterministic, no LLM)

```
Upload → 4 keyword-based scanners → GapReport → template-based remediation → Excel
```

Every control looks like: *"The Compliance Officer monitors and validates compliance with {framework} requirements related to {theme}..."* — identical structure, just with variables swapped.

### Enhanced Flow (hybrid: deterministic + LLM + tools)

```
Upload → 4 scanners → GapReport
                          ↓
              ┌─────────────────────────────────────────┐
              │  For each gap:                          │
              │                                         │
              │  1. SpecAgent receives gap context       │
              │     + available tools list               │
              │                                         │
              │  2. SpecAgent reasons about the gap:     │
              │     "This is a SOX compliance gap in     │
              │      section 4.0. Let me look up what    │
              │      SOX specifically requires here."    │
              │                                         │
              │     → calls regulatory_lookup(           │
              │         "SOX Compliance", "4.0")         │
              │     ← receives: required_themes,         │
              │       applicable_types, domain           │
              │                                         │
              │     "Now let me verify my L1/L2 choice." │
              │     → calls taxonomy_validator(           │
              │         "Detective", "Reconciliation")   │
              │     ← receives: {valid: true}            │
              │                                         │
              │     → produces spec with real context    │
              │                                         │
              │  3. NarrativeAgent receives spec         │
              │     + tool access                        │
              │                                         │
              │     "Let me check the expected           │
              │      frequency for this control type."   │
              │     → calls frequency_lookup(             │
              │         "Reconciliation", "monthly")     │
              │     ← reasoning about why quarterly+     │
              │                                         │
              │     → produces 40-60 word narrative      │
              │       grounded in tool results           │
              │                                         │
              │  4. Validator checks output              │
              │     → if fail: agent retries with        │
              │       failure feedback + tool access     │
              │                                         │
              │  5. EnricherAgent refines narrative      │
              │     "Let me find similar controls."      │
              │     → calls memory_retrieval(             │
              │         "reconciliation of GL accounts") │
              │     ← receives 3 similar controls        │
              │                                         │
              │     → quality rating based on real       │
              │       comparison to existing controls    │
              └─────────────────────────────────────────┘
                          ↓
              Rich, contextual, differentiated controls → Excel
```

### What the Output Difference Looks Like

**Current template output (regulatory gap for SOX):**
> "The Compliance Officer monitors and validates compliance with SOX Compliance requirements related to SOX Compliance in the Governance Risk and Compliance Platform on a quarterly basis within 10 business days of quarter-end. This control ensures adequate regulatory coverage, prevents compliance gaps, and supports the organization's risk management framework by providing timely detection of regulatory exposure."

**Tool-calling-enhanced output (same gap):**
> "The Senior Financial Analyst performs monthly reconciliation of general ledger account balances in SAP ERP to ensure compliance with SOX Section 404 requirements for internal controls over financial reporting. This reconciliation compares subledger totals to GL postings, identifies variances exceeding the $5,000 materiality threshold, and escalates unresolved items to the Accounting Manager within 5 business days. The process mitigates the risk of material misstatement and supports the quarterly SOX certification cycle."

The difference: the tool-calling version references specific regulatory requirements (SOX Section 404), uses domain-appropriate roles (Senior Financial Analyst, not generic Compliance Officer), names real systems (SAP ERP), includes specific thresholds, and links to downstream processes — because the agent looked up this context via tools rather than relying on a template.

### New Gap Categories (Tool-Discovered)

Beyond the current 4 scanners, tool-calling agents could discover additional gap categories:

**Regulatory Deep-Dive Gaps:**
- Agent calls `regulatory_lookup("SOX Compliance", "4.0")` and gets back required themes.
- Agent then calls a future **`read_regulatory_documentation`** tool that queries a vector DB of actual regulation text.
- Discovers that SOX Section 404 requires testing of controls over financial reporting, but no controls in the ecosystem mention "testing" or "ICFR" → flag as a deeper regulatory gap.

**Semantic Coverage Gaps:**
- Agent calls `memory_retrieval(query_text="reconciliation of general ledger accounts")` and gets back 5 similar controls.
- If all 5 have high similarity (>0.92) to each other, the agent flags a **concentration risk** — many controls doing the same thing, but missing variants.

**Cross-Section Gap Detection:**
- Agent calls `hierarchy_search` across multiple sections and identifies process areas with no controls at all (not just under-represented types, but completely uncovered process nodes).

---

## 16. Implementation Plan: 5 Phases to Unified Tool-Calling Pipeline

This section maps directly to the codebase. Each phase lists the exact files, functions, and changes required.

### Phase 1: Transport & Base Agent — Enable Tool Calling

**Goal:** Make it physically possible for an LLM to receive tool definitions and for agents to handle tool-call responses.

#### Step 1.1: Add `tools` parameter to Transport

**File:** `src/controlnexus/core/transport.py`
**Function:** `AsyncTransportClient.chat_completion()`
**Change:** Add optional `tools` parameter to the function signature and include it in the HTTP payload when present.

```python
# BEFORE (current):
async def chat_completion(self, messages, temperature=0.2, max_tokens=1400):
    payload = {
        "model": self.model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }

# AFTER (with tool calling):
async def chat_completion(self, messages, temperature=0.2, max_tokens=1400, tools=None):
    payload = {
        "model": self.model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"  # LLM decides when to call tools
```

**Why this matters:** This is the single most critical change. Without it, no LLM ever receives tool definitions, regardless of what else is wired up. With it, the LLM can return `tool_calls` in its response.

#### Step 1.2: Extend `AgentContext`

**File:** `src/controlnexus/agents/base.py`
**Change:** Add two new fields to the `AgentContext` dataclass.

```python
@dataclass
class AgentContext:
    client: AsyncTransportClient | None = None
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120
    tools: list[dict] = field(default_factory=list)           # NEW
    tool_executor: Callable | None = None                      # NEW
```

- `tools`: The list of OpenAI function-calling schemas (from `TOOL_SCHEMAS`) that this agent can use. Each agent gets a subset — SpecAgent gets 3 tools, NarrativeAgent gets 2, etc.
- `tool_executor`: A reference to `execute_tool_call` from `tools/nodes.py` — the function that dispatches tool names to implementations.

#### Step 1.3: Add `call_llm_with_tools()` to `BaseAgent`

**File:** `src/controlnexus/agents/base.py`
**Change:** Add a new method alongside the existing `call_llm()`.

```python
async def call_llm_with_tools(self, system_prompt, user_prompt, max_tool_rounds=5):
    """Send a prompt with tools, handling the tool-calling loop.

    The LLM may return tool_calls instead of content. When it does:
    1. Execute each tool call via self.context.tool_executor
    2. Append tool results as messages
    3. Call the LLM again with the full message history
    4. Repeat until the LLM returns content (or max rounds exceeded)
    """
    if not self.context.tools or not self.context.tool_executor:
        # Fallback: no tools configured, use regular call_llm
        return await self.call_llm(system_prompt, user_prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(max_tool_rounds):
        response = await self.client.chat_completion(
            messages=messages,
            temperature=self.context.temperature,
            max_tokens=self.context.max_tokens,
            tools=self.context.tools,
        )

        choice = response["choices"][0]["message"]

        if not choice.get("tool_calls"):
            return self._extract_text_from_openai_style(response)

        # Append assistant message (with tool_calls) to conversation
        messages.append(choice)

        # Execute each tool and append results
        for tool_call in choice["tool_calls"]:
            name = tool_call["function"]["name"]
            args = json.loads(tool_call["function"]["arguments"])
            result = self.context.tool_executor(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result),
            })

    # Exhausted rounds — return whatever text was in the last response
    return self._extract_text_from_openai_style(response)
```

**Key design decisions:**
- Falls back to `call_llm()` if no tools are configured → backward compatible.
- Max 5 rounds by default → prevents infinite loops.
- Appends the full message history → LLM sees tool results and can build on them.

### Phase 2: Wire Tools into Each Agent (Hybrid Approach)

**Goal:** Each agent gets a specific subset of tools. The orchestrator/graph still pre-computes essential context, but agents can autonomously call tools for supplementary lookups.

#### Step 2.1: Define Tool Subsets per Agent

| Agent | Tool Schemas (from `schemas.py`) | Why |
|-------|----------------------------------|-----|
| SpecAgent | `TAXONOMY_VALIDATOR_SCHEMA`, `REGULATORY_LOOKUP_SCHEMA`, `HIERARCHY_SEARCH_SCHEMA` | Verify L1/L2 pairs, look up regulatory requirements, find APQC context |
| NarrativeAgent | `FREQUENCY_LOOKUP_SCHEMA`, `REGULATORY_LOOKUP_SCHEMA` | Check expected frequency, enrich regulatory context for richer prose |
| EnricherAgent | `MEMORY_RETRIEVAL_SCHEMA` | Find similar controls for quality benchmarking and deduplication |
| AdversarialReviewer | `TAXONOMY_VALIDATOR_SCHEMA`, `REGULATORY_LOOKUP_SCHEMA` | Verify claims in the control against real taxonomy/regulatory data |
| DifferentiationAgent | `MEMORY_RETRIEVAL_SCHEMA`, `HIERARCHY_SEARCH_SCHEMA` | Find similar controls and APQC context for differentiation |

#### Step 2.2: Update Each Agent's `execute()` Method

For each agent, the only code change is switching from `call_llm()` to `call_llm_with_tools()`:

```python
# In spec.py, narrative.py, enricher.py, adversarial.py, differentiator.py:

# BEFORE:
raw = await self.call_llm(system_prompt, user_prompt)

# AFTER:
raw = await self.call_llm_with_tools(system_prompt, user_prompt)
```

That's it per agent — one line change. The tool schemas are passed via `AgentContext.tools` when the agent is constructed, not hardcoded in `execute()`.

#### Step 2.3: Fix EnricherAgent's `nearest_neighbors=[]` Problem

**File:** `src/controlnexus/pipeline/orchestrator.py` (line ~874)

Currently:
```python
enriched_candidate = await enricher_agent.execute(
    validated_control={...},
    rating_criteria_cfg={...},
    nearest_neighbors=[],       # ← ALWAYS empty
)
```

With tool calling, this hardcoded `[]` becomes irrelevant — the EnricherAgent can call `memory_retrieval` itself when it decides neighbor context would help:

```
EnricherAgent system prompt:
  "If you need to compare this control against existing controls,
   use the memory_retrieval tool to find similar ones."

LLM reasoning:
  "This is a reconciliation control. Let me find similar ones."
  → calls memory_retrieval("GL account reconciliation", "4.0", n=3)
  ← receives 3 similar controls with similarity scores
  "These neighbors are all rated Strong. My control should be at
   least as specific. Rating: Effective."
```

### Phase 3: Unify on the Remediation Graph

**Goal:** Replace the graph's stub nodes with real agent calls, wire tool support into the graph state, and fix the two bugs.

#### Step 3.1: Replace Stub Nodes with Real Agent Calls

**File:** `src/controlnexus/graphs/remediation_graph.py`

Each stub node becomes an async function that instantiates and calls the real agent:

```python
# BEFORE (stub):
def spec_agent_node(state):
    assignment = state.get("current_assignment", {})
    spec = {"who": "Control Owner", "where_system": "Enterprise System", ...}
    return {"current_spec": spec}

# AFTER (real):
async def spec_agent_node(state):
    assignment = state.get("current_assignment", {})
    context = state.get("agent_context")  # Pre-built AgentContext with tools
    spec_agent = SpecAgent(context)

    spec = await spec_agent.execute(
        leaf={"hierarchy_id": assignment["hierarchy_id"], "name": assignment.get("leaf_name", "")},
        control_type=assignment.get("control_type", ""),
        type_definition=state.get("type_definitions", {}).get(assignment.get("control_type", ""), ""),
        registry=state.get("current_profile", {}).get("registry", {}),
        placement_defs=state.get("placement_config", {}),
        method_defs=state.get("placement_config", {}),
        taxonomy_constraints=state.get("taxonomy_constraints", {}),
        diversity_context=state.get("diversity_context", {}),
    )
    return {"current_spec": spec}
```

Same pattern for `narrative_agent_node` and `enricher_node`.

#### Step 3.2: Call `configure_tools()` at Graph Construction

**File:** `src/controlnexus/graphs/remediation_graph.py` (new `setup_tools` node)

```python
def setup_tools_node(state):
    """Initialize tool context from graph state."""
    from controlnexus.tools.implementations import configure_tools
    configure_tools(
        placement_config=state.get("placement_config", {}),
        section_profiles=state.get("section_profiles", {}),
        memory=state.get("memory"),
        bank_id=state.get("bank_id", ""),
    )
    return {}
```

Added as: `START → planner → setup_tools → prepare_context → router → ...`

#### Step 3.3: Fix Bug 1 — Add Assignment Loop

Add a routing function after `merge` that checks for remaining assignments:

```python
def has_more_assignments(state):
    assignments = state.get("assignments", [])
    processed = len(state.get("generated_records", []))
    if processed < len(assignments):
        return "router"    # Process next assignment
    return "export"        # All done

# In graph builder:
graph.add_conditional_edges("merge", has_more_assignments, {
    "router": "router",
    "export": "export",
})
```

And fix `router_node` to pop the next unprocessed assignment instead of always taking `assignments[0]`:

```python
def router_node(state):
    assignments = state.get("assignments", [])
    processed = len(state.get("generated_records", []))
    if processed >= len(assignments):
        return {"current_assignment": {}, "current_gap_source": ""}
    current = assignments[processed]   # ← Pick the next unprocessed one
    ...
```

#### Step 3.4: Fix Bug 2 — Fallback Produces Output

Ensure the fallback `merge` path (when validation exhausts retries) uses `current_narrative` instead of depending on `current_enriched`:

```python
def merge_node(state):
    enriched = state.get("current_enriched", {})
    narrative = state.get("current_narrative", {})

    # Use enriched if available, fall back to narrative
    record = enriched if enriched else narrative
    if record:
        return {"generated_records": [record]}
    return {"generated_records": []}
```

#### Step 3.5: Implement Adversarial Review Routing

Replace the TODO stub:

```python
# BEFORE:
def quality_check(state):
    if state.get("quality_gate_passed", True):
        return "merge"
    return "merge"  # TODO: Phase 9+ will route to adversarial_reviewer

# AFTER:
def quality_check(state):
    if state.get("quality_gate_passed", True):
        return "merge"
    return "adversarial_review"

# New node:
async def adversarial_review_node(state):
    context = state.get("agent_context")
    reviewer = AdversarialReviewer(context)
    review = await reviewer.execute(
        control=state.get("current_enriched", {}),
        spec=state.get("current_spec", {}),
        standards=state.get("standards_config", {}),
    )
    assessment = review.get("overall_assessment", "Satisfactory")
    if assessment in ("Weak", "Needs Improvement"):
        return {"current_narrative": {}, "retry_count": 0}  # Route back to narrative
    return {}  # Proceed to merge
```

### Phase 4: Retire Orchestrator Duplication

**Goal:** The Orchestrator becomes a thin wrapper that prepares config and invokes the graph.

#### Step 4.1: Move Pre-Computation into a Graph Node

Create a `prepare_context` node that does what the Orchestrator's Phase 1 does — load section profiles, build taxonomy constraints, prepare registry data — but writes it to graph state instead of a local `prepared` list.

#### Step 4.2: Refactor the Orchestrator

Replace the 200+ lines of `_llm_enrich_single()`, `_build_control_records()` Phase 2, and retry logic with:

```python
async def _build_control_records(self, assignments, ...):
    graph = build_remediation_graph()
    state = {
        "assignments": assignments,
        "section_profiles": section_profiles,
        "placement_config": placement_methods_cfg,
        "standards_config": standards_cfg,
        "agent_context": agent_ctx,
        ...
    }
    result = await graph.ainvoke(state)
    return result["generated_records"]
```

The Orchestrator shrinks from ~1,020 lines to ~300 (loading, sizing, allocation, graph invocation, export).

#### Step 4.3: Update the UI

`remediation_runner.py`: Replace `_run_remediation()` with an async function that invokes the graph (or falls back to the deterministic `_build_record()` when no LLM is configured):

```python
async def _run_remediation_with_llm(selected_rows, section_profiles, status):
    """Process gaps through the real agent pipeline with tool calling."""
    client = build_client_from_env()
    if client is None:
        # No LLM available — use deterministic templates (current behavior)
        return _run_remediation(selected_rows, section_profiles, status)

    # Initialize agents with tools
    # Build and invoke remediation graph
    # Return generated records
```

### Phase 5: State & Messages Cleanup

**Goal:** Ensure the `messages` field in `RemediationState` is properly used for tool-calling history and cleared between assignment iterations.

#### Step 5.1: Agent Nodes Write to `state["messages"]`

Each agent node should append its messages to the state:

```python
async def spec_agent_node(state):
    # ... (agent execution as in Phase 3) ...
    # After execution, write the message history for debugging/replay:
    return {
        "current_spec": spec,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps(spec)},
        ],
    }
```

#### Step 5.2: Clear Messages Between Assignments

In `merge_node()`, after finalizing a record and before the graph loops back to `router`:

```python
def merge_node(state):
    record = state.get("current_enriched", {}) or state.get("current_narrative", {})
    return {
        "generated_records": [record] if record else [],
        "messages": [],  # Clear for next assignment (add reducer replaces via empty)
        "current_spec": {},
        "current_narrative": {},
        "current_enriched": {},
    }
```

**Note:** Because `messages` uses the `add` reducer, resetting requires a custom approach — either a dedicated "clear" mechanism or replacing the reducer behavior for resets.

---

## 17. Design Decisions and Rationale

### Decision 1: Hybrid Tool Calling (Not Fully Autonomous)

**What it means:** Agents still receive essential context pre-computed (taxonomy constraints, standards, section profiles) in their prompts, but can call tools for supplementary data.

**Why not fully autonomous (agents get zero context, must tool-call for everything)?**
- **Cost:** Each tool call = one additional LLM round-trip. If SpecAgent needs taxonomy constraints, registry, and placement definitions, that's 3 tool calls × prompt re-processing = ~3x the token cost per control.
- **Latency:** Each tool round adds ~1-2 seconds. For 100 controls × 3 agents × 3 tool calls, that's ~15 minutes of added wait time.
- **Reliability:** Pre-computed context is deterministic and always available. Tools can fail (memory not configured, section not found).

**Hybrid sweet spot:** Give agents enough context to do their job in 0-1 tool calls, but let them autonomously decide when they need more.

### Decision 2: LangGraph-Native Architecture (Not Orchestrator-Only)

**What it means:** The remediation graph is the single execution path. The orchestrator becomes a thin wrapper.

**Why not just add tool calling to the orchestrator?**
- **Maintenance:** Maintaining two parallel pipelines (graph + orchestrator) doubles the surface area for bugs.
- **Tool-call loops:** LangGraph's conditional edges handle `agent → tool → agent` loops natively. Doing this in the orchestrator means manually coding `while has_tool_calls: execute_tools(); call_llm_again()` — reimplementing what LangGraph provides for free.
- **Extensibility:** Adding adversarial review, differentiation checks, or new gap scanners means adding nodes and edges to the graph — not refactoring nested Python conditionals.

### Decision 3: `call_llm_with_tools()` as Agent-Internal Loop

**What it means:** Each agent handles its own tool-calling loop internally, rather than the graph routing between agent and tool_node.

**Why not graph-level tool routing?**
- **Simplicity:** With 5 agents, graph-level routing requires either 5 separate tool_nodes (one per agent) or a shared tool_node with a `current_agent` routing field. Both add complexity.
- **Encapsulation:** The agent knows best when to call tools. Graph-level routing forces the graph to understand individual agent decisions.
- **Backward compatibility:** `call_llm_with_tools()` falls back to `call_llm()` when no tools are configured — existing code that creates agents without tools continues to work unchanged.

**Trade-off:** The graph doesn't see individual tool calls in its state (they happen inside agent nodes). For debugging, agent nodes can optionally write their full message history to `state["messages"]`.

### Decision 4: Single `configure_tools()` Call at Graph Start

**What it means:** Tool implementations use module-level globals set once before graph execution, not passed per-call.

**Why not inject config per tool call?**
- **Existing pattern:** The tool implementations are already designed around module globals. Changing to dependency injection would require rewriting all 5 tools.
- **Config doesn't change mid-run:** Section profiles, taxonomy config, and placement methods are static for a given pipeline execution. Setting them once is sufficient.
- **Graph initialization:** A `setup_tools` node at the start of the graph ensures tools are configured before any agent runs.

---

## 18. Verification and Testing Strategy

### Unit Tests

**Extend `tests/test_tools.py`:**
- Test the `call_llm_with_tools()` loop: mock the LLM to return a `tool_calls` response on the first call, then a final text response on the second call. Verify the tool was executed and its result appeared in the second prompt.
- Test with 0 tool calls (LLM immediately returns text → behaves like `call_llm()`).
- Test with max rounds exhausted (LLM keeps returning tool_calls for 6 rounds → returns last available text).
- Test with unknown tool name → `execute_tool_call` returns `{error: "Unknown tool"}`.

### Integration Tests

**New test: `tests/test_tool_calling_integration.py`:**
- Run a single control through the unified remediation graph with a mock LLM that:
  1. Returns a `taxonomy_validator` tool call on the first SpecAgent call.
  2. Returns a final spec JSON on the second call.
  3. Returns a narrative JSON for NarrativeAgent.
  4. Returns an enrichment JSON for EnricherAgent.
- Verify: `configure_tools()` was called, at least one tool was executed, the final control output includes data that could only come from a tool result.

### Regression Tests

**Run `tests/test_e2e.py` against both paths:**
- Deterministic path (no LLM configured) → output matches current behavior.
- LLM path → output quality is equal or better than current orchestrator output.

### Graph Visualization

After building the graph, generate a visual diagram:
```python
graph = build_remediation_graph()
print(graph.get_graph().draw_mermaid())
```

Expected topology:
```
START → planner → setup_tools → prepare_context → router → spec_agent
  → narrative_agent → validator → [enricher | narrative_agent (retry) | merge (fallback)]
  → quality_gate → [merge | adversarial_review]
  → merge → (more assignments?) → [router | export → END]
```

---

## 19. Summary: Current vs. Target Architecture

### Current Architecture

```
Upload → 4 deterministic scanners → GapReport
            ↓
(User selects gaps)
            ↓
Deterministic templates → Generic controls → Excel

    Meanwhile, sitting unused:
    ┌─────────────────────────────────────────────────┐
    │  5 tool schemas         (schemas.py)            │
    │  5 tool implementations (implementations.py)    │
    │  tool_node              (nodes.py)              │
    │  configure_tools()      (implementations.py)    │
    │  TOOL_MAP               (nodes.py)              │
    │  RemediationState.messages (state.py)           │
    │  Remediation graph topology (remediation_graph) │
    │  SpecAgent, NarrativeAgent, EnricherAgent       │
    │  AdversarialReviewer, DifferentiationAgent      │
    │  ChromaDB memory store  (store.py)              │
    │  EventEmitter AGENT_* events (events.py)        │
    └─────────────────────────────────────────────────┘
```

**Problems:**
- Scanners use naive keyword matching (no semantic understanding of regulations).
- Remediation produces nearly identical template controls regardless of gap type or context.
- 5 built-and-tested tools are completely disconnected from every pipeline path.
- The LangGraph remediation graph has correct topology but stub internals and two critical bugs.
- Real LLM agents exist (SpecAgent, NarrativeAgent, EnricherAgent) but are only used by the ControlForge tab, never the Analysis tab.
- ChromaDB memory store exists but `nearest_neighbors=[]` is hardcoded — EnricherAgent never sees similar controls.
- Event types (AGENT_STARTED, AGENT_COMPLETED, etc.) exist but are never emitted.

### Target Architecture

```
Upload → 4 deterministic scanners → GapReport
            ↓
   (Optional: LLM Gap Discovery Agent with tools)
            ↓
(User selects gaps)
            ↓
Orchestrator (thin wrapper: load config → invoke graph → return results)
            ↓
┌─ Remediation Graph ──────────────────────────────────────────────┐
│                                                                   │
│  setup_tools → prepare_context → router                           │
│                                     ↓                             │
│  ┌─────────── Per-assignment loop ──────────────────────┐        │
│  │                                                       │        │
│  │  SpecAgent (with taxonomy_validator, regulatory_lookup,│       │
│  │            hierarchy_search tools)                     │        │
│  │      ↓                                                │        │
│  │  NarrativeAgent (with frequency_lookup,               │        │
│  │                  regulatory_lookup tools)              │        │
│  │      ↓                                                │        │
│  │  Validator (deterministic 6-rule check)               │        │
│  │      ↓                                                │        │
│  │  [retry → NarrativeAgent | enricher | fallback merge] │        │
│  │      ↓                                                │        │
│  │  EnricherAgent (with memory_retrieval tool)           │        │
│  │      ↓                                                │        │
│  │  Quality Gate → [merge | AdversarialReviewer]         │        │
│  │      ↓                                                │        │
│  │  Merge → (more assignments?) → [router | export]      │        │
│  └───────────────────────────────────────────────────────┘        │
│                                                                   │
│  export → END                                                     │
└───────────────────────────────────────────────────────────────────┘
            ↓
Rich, contextual, differentiated controls → Excel
```

**What changes:**
1. **Transport** gets `tools` parameter (~5 lines in `transport.py`).
2. **AgentContext** gets `tools` and `tool_executor` fields (~3 lines in `base.py`).
3. **BaseAgent** gets `call_llm_with_tools()` method (~40 lines in `base.py`).
4. **Each agent's `execute()`** switches from `call_llm()` to `call_llm_with_tools()` (1 line per agent).
5. **`configure_tools()`** is called at graph startup (1 new graph node).
6. **Graph stub nodes** are replaced with real agent calls (~20 lines per node).
7. **Graph topology** gains: assignment loop edge, adversarial review routing, setup_tools node.
8. **Orchestrator** shrinks from ~1,020 to ~300 lines (delegates to graph).
9. **Remediation runner** calls graph when LLM available, falls back to templates when not.

**What stays the same:**
- The 4 deterministic scanners (proven, fast, zero API cost).
- Frequency and evidence fixes (deterministic is appropriate for simple changes).
- The validator's 6 rules.
- The Excel export pipeline.
- The fallback to deterministic templates when no LLM is configured.
- All existing tests continue to pass.
