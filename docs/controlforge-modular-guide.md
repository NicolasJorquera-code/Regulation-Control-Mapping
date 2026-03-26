# ControlForge Modular — Front-End Guide & Real-World Usage

A hands-on guide for running, testing, and understanding the ControlForge Modular tab. Covers how to launch the UI, what every setting does, and real-world scenarios showing when and why you would use each feature.

---

## Table of Contents

1. [How to Launch and Test the Front End](#1-how-to-launch-and-test-the-front-end)
2. [UI Walkthrough — Screen by Screen](#2-ui-walkthrough--screen-by-screen)
3. [Generation Settings — Deep Dive](#3-generation-settings--deep-dive)
4. [Real-World Examples](#4-real-world-examples)
5. [Understanding the Output](#5-understanding-the-output)
6. [Customizing Config Profiles](#6-customizing-config-profiles)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. How to Launch and Test the Front End

### Prerequisites

- Python 3.11+
- The project dependencies installed (`pip install -e ".[dev]"` or `pip install -e .` from the repo root)

### Starting the App

From the repo root:

```bash
streamlit run src/controlnexus/ui/app.py
```

This opens the ControlNexus dashboard in your browser (default: `http://localhost:8501`). You'll see four tabs across the top:

| Tab | Purpose |
|-----|---------|
| **ControlForge** | Original configuration explorer and pipeline runner |
| **ControlForge Modular** | **The new tab** — config-driven control generation |
| **Analysis** | Upload existing controls, run gap analysis |
| **Playground** | Interactive agent testing |

Click **"ControlForge Modular"** to open the new tab.

### Quick Smoke Test

1. Launch the app
2. Click the **ControlForge Modular** tab
3. The config selector should default to one of the profiles in `config/profiles/` (e.g., "Community Bank Demo")
4. Leave "Number of controls to generate" at **10**
5. Click **"Generate Controls"**
6. A table of 10 generated controls should appear with download buttons

If that works, the entire pipeline — config loading, validation, graph execution, and UI rendering — is functional.

---

## 2. UI Walkthrough — Screen by Screen

The Modular tab has four visual sections, top to bottom:

### 2.1 Organization Config (top section)

This is where you choose *which organization's rules* the pipeline should follow.

**Left column — Config selector dropdown:**
Lists every `.yaml` file in `config/profiles/`. Out of the box you get:
- **Community Bank Demo** — 3 control types, 2 business units, 2 process areas. Good for quick tests.
- **Banking Standard** — 25 control types, 17 business units, 13 process areas. Equivalent to the full current system.

**Right column — Upload custom YAML:**
Drag-and-drop or browse for a custom `domain_config.yaml`. This overrides the dropdown selection. Useful for testing a new organization's config without saving it to `config/profiles/`.

**Preview metrics (below the selector):**
Three cards showing counts from the loaded config:
- **Control Types** — How many types of controls this org uses (e.g., Authorization, Reconciliation)
- **Business Units** — How many BUs are defined (e.g., Retail Banking, Operations)
- **Process Areas** — How many process areas / sections (e.g., Lending Operations, Settlement and Clearing)

**"Config Details" expander:**
Click to see three tables showing the specifics of the loaded config:
- Control types with their codes and minimum frequency requirements
- Business units with IDs, names, and key control types
- Process areas with IDs, names, and risk multipliers

### 2.2 Generation Settings (middle section)

This is the core control panel for *how many* controls to generate and *how to distribute them*. See [Section 3](#3-generation-settings--deep-dive) for the full deep dive.

### 2.3 Generate Button

A full-width primary button. Click it and a live status panel (`st.status()`) appears showing real-time progress: which agent is running, which tools are being called, validation results, and per-control completion. This is powered by the `EventEmitter` → `StreamlitEventListener` pipeline.

- **Deterministic mode** (no LLM keys): Under a second for 10 controls.
- **LLM mode** (OpenAI/Anthropic key configured): ~2-5 seconds per control depending on model speed and tool call rounds.

### 2.4 Results (bottom section)

After generation:
- **Summary metrics**: Total controls, control types used, business units used
- **Data table**: Every generated control as a row. Columns match the export schema: `control_id`, `hierarchy_id`, `leaf_name`, `selected_level_1`, `selected_level_2`, `business_unit_id`, `business_unit_name`, `who`, `what`, `when`, `frequency`, `where`, `why`, `full_description`, `quality_rating`, `evidence`
- **Download buttons**: CSV and JSON exports

---

## 3. Generation Settings — Deep Dive

This section explains exactly what every control in the "Generation Settings" area does, what the defaults mean, and how changing them affects the output.

### 3.1 Number of Controls to Generate

```
Number of controls to generate: [10]    (min: 1, max: 500)
```

**What it does:** Sets the exact total number of control records the graph will produce. The pipeline builds an "assignment matrix" of that size — a list of (section, control type, business unit) combinations — then generates one control per assignment.

**How the count gets distributed:** The `target_count` is split two ways:
1. **Across control types** — proportional to type weights (default: even split)
2. **Across process areas / sections** — proportional to section weights (default: risk multiplier from the config)

Example with Community Bank Demo (3 types, 2 sections) requesting 10 controls:
- Even type split: ~3-4 controls per type (Authorization ≈ 3, Reconciliation ≈ 4, Exception Reporting ≈ 3)
- Section split weighted by risk multiplier: Section 1.0 (multiplier 1.8) gets ~4 controls, Section 2.0 (multiplier 2.4) gets ~6 controls

### 3.2 Customize Distribution (Expander)

Click "Customize Distribution" to reveal two groups of sliders:

#### Control Type Weight Sliders

One slider per control type. Range: **0.0 to 10.0**, default: **1.0**, step: **0.5**.

**What the number means:** It's a *relative* weight, not a percentage or absolute count. The pipeline uses proportional distribution:

```
controls_for_type_X = (weight_X / sum_of_all_weights) × target_count
```

**Practical examples:**

| Scenario | Authorization slider | Reconciliation slider | Exception Reporting slider | Result (10 controls) |
|----------|---------------------|----------------------|---------------------------|---------------------|
| Default (even) | 1.0 | 1.0 | 1.0 | ~3, ~4, ~3 |
| Heavy Authorization | **5.0** | 1.0 | 1.0 | ~7, ~1-2, ~1-2 |
| No Exception Reporting | 1.0 | 1.0 | **0.0** | ~5, ~5, 0 |
| All Reconciliation | 0.0 | **10.0** | 0.0 | 0, 10, 0 |

**Why you'd change this:** Your organization might have a regulatory push on one control type. For example, after an audit finding about reconciliation gaps, you'd crank up the Reconciliation slider to generate more reconciliation controls for review.

#### Section Emphasis Sliders

One slider per process area. Range: **0.0 to 10.0**, step: **0.5**. **Default: the section's risk multiplier from the config** (not 1.0).

For Community Bank Demo:
- Section 1.0 "Lending Operations" defaults to **1.8** (its `risk_profile.multiplier`)
- Section 2.0 "Settlement and Clearing" defaults to **2.4**

**What the number means:** Same proportional logic as type weights, but applied to sections:

```
controls_in_section_X = (weight_X / sum_of_all_weights) × target_count
```

**Why the defaults aren't 1.0:** The `risk_profile.multiplier` in the config encodes domain knowledge. Settlement and Clearing has a multiplier of 2.4 because it has higher inherent risk (rank 4) and regulatory intensity (rank 4). The defaults automatically give more controls to higher-risk areas.

**Practical examples:**

| Scenario | Lending (1.0) slider | Settlement (2.0) slider | Result (10 controls) |
|----------|---------------------|------------------------|---------------------|
| Default (risk-weighted) | 1.8 | 2.4 | ~4, ~6 |
| Equal emphasis | **1.0** | **1.0** | ~5, ~5 |
| Focus on Lending | **5.0** | 1.0 | ~8, ~2 |
| Settlement only | 0.0 | **5.0** | 0, 10 |

**Important interaction:** Type weights and section weights work together. The pipeline tries to satisfy both. If you asked for 10 controls, set Authorization to weight 5.0 (wanting ~7 Authorization controls), but also set only Settlement to 5.0 and Lending to 0.0, then you'd get ~7 Authorization controls all concentrated in Settlement, and ~3 other controls also in Settlement.

### 3.3 What Happens Under the Hood

When you click "Generate Controls", this is the flow:

```
┌──────────────────────────────────────────────────┐
│  1. init_node                                     │
│     - Loads DomainConfig from the selected YAML   │
│     - Detects LLM provider (ICA/OpenAI/Anthropic) │
│     - Calls build_assignment_matrix() with:       │
│       • target_count (your slider value)          │
│       • type_weights (your type sliders, if any)  │
│       • section_weights (your section sliders)    │
│     - Produces a list of N assignments            │
│     - Each assignment = {section, type, BU}       │
└───────────────────────┬──────────────────────────┘
                        ▼
     ┌──── Loop (runs once per assignment) ────┐
     │                                          │
     │  2. select_node — picks assignment[i]    │
     │  3. spec_node — generates specification  │
     │     (LLM with tools or deterministic)    │
     │  4. narrative_node — generates 5W prose   │
     │     (LLM with tools or deterministic)    │
     │  5. validate_node — 6-rule check          │
     │     (retries narrative up to 3 times)    │
     │  6. enrich_node — quality rating + refine │
     │  7. merge_node — appends record, i++     │
     │                                          │
     └──── repeats until i == target_count ─────┘
                        ▼
┌──────────────────────────────────────────────────┐
│  8. finalize_node                                 │
│     - Assigns control IDs (e.g., CTRL-0101-AUT-  │
│       001) using type codes from config           │
│     - Builds the plan_payload shown in the UI     │
└──────────────────────────────────────────────────┘
```

The **assignment matrix** is the key concept. It's a pre-computed list that answers: "For each of the N controls I need to generate, which section does it belong to, what type is it, and which BU owns it?" The distribution sliders directly shape this matrix.

### 3.4 How Business Units Get Assigned

You'll notice there are no BU sliders. Business units are assigned automatically:

1. For each section, the pipeline finds BUs whose `primary_sections` include that section
2. If multiple BUs match, it round-robins through them
3. If no BU has that section as primary, it cycles through all BUs

Example: In Community Bank Demo, Section 2.0 "Settlement and Clearing" is primary for both BU-001 (Retail Banking) and BU-002 (Operations). Controls in that section alternate between those two BUs.

### 3.5 How the Builders Work

The pipeline operates in two modes depending on whether an LLM API key is configured:

#### Deterministic Mode (no API key)

Template-based generation from the config's registry data:

**Spec builder** picks:
- **Who** → a role from the section's `registry.roles` (e.g., "Loan Officer")
- **What** → the control type's `definition` (e.g., "performs reconciliation control activities")
- **When** → an event trigger from `registry.event_triggers` (e.g., "at each monthly portfolio review")
- **Where** → a system from `registry.systems` (e.g., "Loan Origination System")
- **Why** → a risk statement referencing the section name
- **Evidence** → an artifact from `registry.evidence_artifacts`
- **Placement** → from the control type's `placement_categories` (e.g., Preventive)
- **Method** → Automated for Preventive, Manual for Detective

**Narrative builder** composes the `full_description` from the 5W fields:
```
"At each monthly portfolio review, the Loan Officer performs reconciliation 
control activities within the Loan Origination System to mitigate risk of 
control failures in Lending Operations, with results documented via loan 
approval documentation."
```

**Frequency** is derived by matching the `when` text against the config's `frequency_tiers` keywords. "monthly portfolio review" matches the keyword "monthly" → frequency = "Monthly".

#### LLM Mode (OpenAI or Anthropic key configured)

When an LLM provider is detected, each agent node calls the LLM instead of using templates:

- **SpecAgent** generates a locked specification using the domain context. With OpenAI/Anthropic, it uses slim prompts and is forced to call `placement_lookup`, `method_lookup`, `evidence_rules_lookup`, and `taxonomy_validator` tools before producing JSON.
- **NarrativeAgent** converts the spec into 5W prose. With tool-calling providers, it calls `exemplar_lookup` and `frequency_lookup` before writing the narrative.
- **EnricherAgent** refines the narrative and assigns a quality rating from the config's `quality_ratings` list (e.g., "Effective", "Strong", "Needs Improvement").
- **Validator** runs the same 6 deterministic rules. If validation fails, the NarrativeAgent is retried up to 3 times with targeted instructions.

With ICA (no tool support), agents receive "fat" prompts that inline all domain data directly. With OpenAI/Anthropic, agents receive "slim" prompts and must call tools — reducing token usage by ~55-60%.

Every agent falls back to deterministic mode if the LLM call fails, ensuring the pipeline always produces output.

---

## 4. Real-World Examples

### 4.1 Scenario: Annual Audit Preparation

**Context:** A community bank needs to demonstrate its control framework to regulators. The compliance officer needs a quick draft of controls across all process areas to review.

**Steps:**
1. Select **Community Bank Demo** config
2. Set target count to **20** (enough to cover both sections meaningfully)
3. Leave distribution defaults (risk-weighted — Settlement gets more controls because higher risk)
4. Click Generate
5. Download CSV, open in Excel, review/edit each control with the audit team

**What you get:** 20 controls distributed ~8 to Lending (multiplier 1.8) and ~12 to Settlement (multiplier 2.4), spread across Authorization, Reconciliation, and Exception Reporting types. Each control has a realistic-sounding narrative built from the registry data for that section.

### 4.2 Scenario: Post-Audit Remediation on Reconciliation Controls

**Context:** An OCC examiner flagged that the bank's reconciliation controls are insufficient. The risk team needs to draft additional reconciliation controls specifically for Settlement.

**Steps:**
1. Select **Community Bank Demo** config
2. Set target count to **15**
3. Open **Customize Distribution**
4. Set **Reconciliation** slider to **8.0**, Authorization to **1.0**, Exception Reporting to **1.0**
5. Set **Settlement and Clearing** slider to **8.0**, Lending Operations to **1.0**
6. Click Generate

**What you get:** ~12 of the 15 controls are Reconciliation type, and ~13 are in Settlement. The narratives reference Settlement-specific roles (Settlement Analyst, Operations Manager), systems (Payment Processing System, General Ledger System), and evidence (daily settlement reconciliation report). This gives the risk team a concentrated draft to refine.

### 4.3 Scenario: Testing a New Organization's Config

**Context:** You're building a config for a credit union that has different control types (e.g., "Member Verification" instead of "Authorization") and different process areas.

**Steps:**
1. Create a new YAML file based on the community bank demo structure (see [Section 6](#6-customizing-config-profiles))
2. In the Modular tab, use the **Upload custom YAML** button
3. If the YAML has validation errors (e.g., a BU references a control type name with a typo), you'll see a clear error message immediately
4. Once it loads, the preview metrics update to show your custom counts
5. Generate a small batch (5-10) to verify the output looks correct
6. Iterate: fix the YAML, re-upload, regenerate

### 4.4 Scenario: Full Banking Standard — Large-Scale Generation

**Context:** You need to produce a comprehensive control register with hundreds of controls across all 13 APQC process areas.

**Steps:**
1. Select **Banking Standard** config (25 types, 17 BUs, 13 sections)
2. Set target count to **200**
3. Open Customize Distribution — you'll see 25 type sliders and 13 section sliders
4. Increase sliders for high-priority areas (e.g., crank "Lending Operations" and "BSA/AML" sections higher)
5. Decrease or zero-out control types that aren't relevant to the current exercise
6. Click Generate

**What you get:** 200 controls with control IDs like `CTRL-0101-AUT-001`, realistic narratives referencing domain-specific roles and systems, and proper frequency assignments. Download as CSV for your GRC tool or JSON for further programmatic processing.

### 4.5 Scenario: Comparing Two Config Profiles

**Context:** You want to see how the community bank config and the full banking standard differ in output.

**Steps:**
1. Select **Community Bank Demo**, generate 10 controls, download CSV
2. Select **Banking Standard**, generate 10 controls, download CSV
3. Compare: the banking standard output will reference more diverse types, BUs, and sections, with different registry vocabulary (different roles, systems, evidence artifacts)

This demonstrates the core value of config-driven generation: **same pipeline code, completely different output** based on which YAML you feed it.

---

## 5. Understanding the Output

### 5.1 Output Columns

| Column | Description | Example |
|--------|-------------|---------|
| `control_id` | Unique ID: `CTRL-{section}{subsection}-{type_code}-{seq}` | `CTRL-0101-REC-001` |
| `hierarchy_id` | Position in the process hierarchy | `1.0.1.1` |
| `leaf_name` | Human-readable label | `Lending Operations – Reconciliation` |
| `selected_level_1` | Placement category | `Detective` |
| `selected_level_2` | Control type name | `Reconciliation` |
| `business_unit_id` | BU identifier | `BU-001` |
| `business_unit_name` | BU name | `Retail Banking` |
| `who` | Role performing the control | `Loan Officer` |
| `what` | Action performed | `performs reconciliation control activities` |
| `when` | Timing/trigger | `at each monthly portfolio review` |
| `frequency` | Derived frequency tier | `Monthly` |
| `where` | System or location | `Loan Origination System` |
| `why` | Risk addressed | `to mitigate risk of control failures in Lending Operations` |
| `full_description` | Prose narrative combining all 5W fields | Full sentence |
| `quality_rating` | Quality assessment (deterministic: always "Satisfactory") | `Satisfactory` |
| `evidence` | Evidence artifact | `loan approval documentation` |

### 5.2 Control ID Format

```
CTRL-{L1}{L2}-{TYPE_CODE}-{SEQ}
```

- `L1`, `L2`: First two parts of the hierarchy ID, zero-padded to 2 digits
- `TYPE_CODE`: 3-letter code from the config (e.g., `REC`, `AUT`, `EXR`)
- `SEQ`: Sequence number per type, zero-padded to 3 digits

Example: The second Reconciliation control in section 2.0 = `CTRL-0200-REC-002`

### 5.3 Quality Rating

- **Deterministic mode:** All controls get `"Satisfactory"` since there's no LLM-generated content to evaluate.
- **LLM mode:** The EnricherAgent assigns a quality rating from the config's `quality_ratings` list (e.g., "Effective", "Strong", "Needs Improvement", "Satisfactory"). The rating reflects the agent's assessment of narrative clarity, evidence specificity, and 5W completeness.

---

## 6. Customizing Config Profiles

### 6.1 Creating a New Config

Copy `config/profiles/community_bank_demo.yaml` and modify it. The minimum required structure:

```yaml
name: "my-org"
description: "Description of my organization"

control_types:
  - name: "My Control Type"
    definition: "What this control type does"
    code: MCT       # 3-letter code (optional — auto-generated if blank)
    min_frequency_tier: Monthly    # optional
    placement_categories: [Detective]   # must match a known placement
```

Everything else (business_units, process_areas, placements, methods, frequency_tiers, narrative) has sensible defaults. Add sections as you need more specificity:

```yaml
process_areas:
  - id: "1.0"
    name: "My Process Area"
    domain: "my_domain"
    risk_profile:
      multiplier: 1.5     # controls how many controls are allocated here
    registry:
      roles: ["Analyst", "Manager"]
      systems: ["My System"]
      evidence_artifacts: ["My Report"]
      event_triggers: ["at each monthly review"]
```

### 6.2 Validation On Load

The config is validated immediately when selected. Cross-reference checks catch:

| Error | Example |
|-------|---------|
| BU references nonexistent control type | `key_control_types: ["Reconiliation"]` (typo) |
| BU references nonexistent section | `primary_sections: ["99.0"]` |
| Control type references nonexistent placement | `placement_categories: ["Proactive"]` (should be "Preventive") |
| Control type references nonexistent frequency tier | `min_frequency_tier: "Bimonthly"` |
| Section affinity references nonexistent type | `HIGH: ["Auth"]` (should be "Authorization") |

All errors are reported at once, not one at a time.

### 6.3 Saving to the Profiles Directory

To make a config appear in the dropdown permanently, save it to `config/profiles/your_config.yaml`. The filename (minus extension) becomes the display name in the dropdown (underscores and hyphens become spaces, title-cased).

---

## 7. Troubleshooting

### "No config profiles found"

The app can't find `config/profiles/`. Make sure you're running `streamlit run` from the repo root directory, not from `src/` or another subdirectory.

### Config validation error on upload

Read the error message — it lists every cross-reference problem. Fix the YAML and re-upload. Common issues:
- Typos in control type names (names must match **exactly**, case-sensitive)
- Referencing a section ID in a BU that doesn't exist in `process_areas`
- Using a placement name that isn't in the `placements` list

### All controls have the same narrative

This happens when a process area's registry has only one entry in its lists (one role, one system, etc.). Add more variety to the registry for richer output. The deterministic builder selects entries based on a hash of `section_id + control_type`, so more registry entries = more diverse narratives.

### Controls not distributed as expected

The distribution is proportional, not exact. With small target counts (e.g., 5 controls across 3 types), rounding means you won't get perfect proportions. Increase the target count for more precise distribution.

### Want to reset sliders to defaults

Refresh the browser page (`Cmd+R` / `Ctrl+R`). Streamlit resets all widget state on page reload.

### EnricherAgent falls back to deterministic

If you see "enrich_node LLM failed — falling back to deterministic" in logs, this is graceful degradation. The control still gets generated with a "Satisfactory" rating. Common causes:
- Transient API timeout (especially for the last control in a batch)
- Rate limiting from the provider

### LLM mode: SpecAgent calls 4 tools every time

This is expected when using OpenAI/Anthropic. The slim prompt strategy uses `tool_choice="required"` to force at least one tool call round. SpecAgent typically calls `taxonomy_validator`, `placement_lookup`, `method_lookup`, and `evidence_rules_lookup` in parallel on round 1, then produces JSON on round 2.