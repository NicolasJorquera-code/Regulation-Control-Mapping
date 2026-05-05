# Risk Inventory Builder Demo Frontend Deep Dive

This document is a detailed handoff for the current Risk Inventory Builder demo frontend and its supporting data generation path. It is written for a highly capable downstream system that needs to understand the UI, object graph, fixture relationships, generated fields, deterministic calculations, provenance boundaries, and known implementation quirks without rediscovering the codebase from scratch.

## 2026-05 Workbench Update

The current Risk Inventory Builder direction is now a simplified executive workbench, not a many-tab dashboard. The top-level demo tabs are:

- `Knowledge Base`
- `Risk Inventory`
- `Control Mapping`
- `Gap Analysis`
- `Review & Challenge`
- `Executive Report`

The former `Process Map`, `Residual Risk`, `KRI Program`, and `Agent Run Trace` tabs are intentionally removed from the top-level navigation. Their useful content is consolidated into `Risk Inventory`, `Review & Challenge`, and the executive workbook source trace. The user selects a risk in the left pane and reviews the full risk profile: statement, root causes, impact, frequency, inherent risk, residual risk, management response, mitigation plan, controls, gaps, synthetic controls, KRIs, evidence, issues, review/challenge, and an impact-by-frequency heatmap.

When no process is selected, `Risk Inventory` shows the portfolio view: a business-unit-by-enterprise-risk-category heatmap plus the aggregated risk table.

Terminology update: user-facing labels should say `Frequency`, not `Likelihood`. The internal `LikelihoodAssessment` model and deterministic scoring tests remain backward-compatible.

APQC update: APQC is optional process-normalization metadata only. It can appear in source trace or technical metadata when a process includes `apqc_crosswalk`, but policy/process documents, controls, obligations, issues/events, evidence, KRIs, taxonomies, and scoring YAML drive the risk engine. Useful APQC framing references are [APQC Process Frameworks](https://www.apqc.org/process-frameworks), [APQC Cross-Industry PCF](https://www.apqc.org/resource-library/resource-listing/apqc-process-classification-framework-pcf-cross-industry-pdf-6), and [APQC Banking PCF](https://www.apqc.org/resource-library/resource-listing/apqc-process-classification-framework-pcf-banking-pcf-pdf-1).

## 1. Scope And Snapshot

This document describes the current Streamlit implementation in:

- `src/controlnexus/ui/app.py`
- `src/controlnexus/ui/risk_inventory_tab.py`
- `src/controlnexus/risk_inventory/models.py`
- `src/controlnexus/risk_inventory/demo.py`
- `src/controlnexus/risk_inventory/graph.py`
- `src/controlnexus/risk_inventory/document_ingest.py`
- `src/controlnexus/risk_inventory/calculators.py`
- `src/controlnexus/risk_inventory/validator.py`
- `src/controlnexus/risk_inventory/export.py`
- `sample_data/risk_inventory_demo/*.yaml`
- `config/risk_inventory/*.yaml`

The frontend is a Streamlit application. It is not a React or Next.js frontend. All frontend behavior is expressed as Python render functions, Streamlit widgets, session state, dataframe renderers, custom HTML snippets, and inline CSS.

The demo is currently a deterministic, fixture-backed experience. It presents multi-business-unit workspace data, per-process risk inventory runs, risk-to-control mappings, residual risk calculations, KRI recommendations, review/challenge fields, source trace, and Excel export. Demo Mode does not require LLM credentials.

Important current-state note: the UI still uses a top-level `Business Unit` selector followed by a `Process Focus` selector. Once a process is selected, `Risk Inventory` now uses a single selected risk id in Streamlit session state and renders a workbench-style table/detail experience.

## 2. High-Level Product Intent

Risk Inventory Builder answers this product question:

```text
Given a process, product, business context, taxonomy, and available control data,
what risks should exist in the risk inventory, how should they be described,
how material are they, what controls address them, and what residual exposure remains?
```

The demo frontend is intended to make three things visible:

1. The process or workspace context being assessed.
2. The resulting risk inventory and how each risk was scored.
3. The evidence, controls, KRIs, and deterministic configuration that make the output defensible rather than an unsupported AI narrative.

In the current implementation, the provenance story is present in the data model and in multiple tabs, but it is distributed across the UI rather than centralized in a dedicated Source Trace tab.

## 3. Application Entry Flow

### 3.1 Streamlit App Entrypoint

The Streamlit application starts in `src/controlnexus/ui/app.py`.

`main()` does the following:

1. Calls `st.set_page_config(...)`.
2. Loads global styling via `load_custom_css()`.
3. Initializes `st.session_state.active_tab` if missing.
4. Renders the masthead.
5. Creates the primary app tabs:
   - `Risk Inventory Builder`
   - `Control Builder`
   - `ControlForge Modular`
   - `Analysis`
   - `Playground`
6. Calls `_render_risk_inventory_tab()` inside the first tab.

`_render_risk_inventory_tab()` imports and calls `render_risk_inventory_tab()` from `src/controlnexus/ui/risk_inventory_tab.py`.

### 3.2 Risk Inventory Builder Entrypoint

`render_risk_inventory_tab()` is the top-level render function for this frontend.

It performs these actions:

1. Injects Risk Inventory-specific CSS through `_inject_risk_inventory_css()`.
2. Renders the hero area:
   - eyebrow: `Risk Inventory Builder`
   - heading: `Convert process evidence into a risk inventory`
   - supporting copy about the bank knowledge base, business unit risk profiles, process document ingestion, and the two-tier taxonomy.
3. Renders a right-side `Demo Mode` toggle.
4. If `Demo Mode` is enabled, calls `_render_demo_workspace()`.
5. If `Demo Mode` is disabled, calls `_render_user_workflow()`.

The toggle is bound to Streamlit session state key `demo_mode`.

## 4. Demo Workspace Data Loading

### 4.1 Session State Cache

`_render_demo_workspace()` checks whether `risk_inventory_workspace` exists in `st.session_state`.

If absent:

```python
st.session_state["risk_inventory_workspace"] = load_demo_workspace().model_dump()
```

It then reconstructs the typed object graph:

```python
workspace = RiskInventoryWorkspace.model_validate(st.session_state["risk_inventory_workspace"])
```

This means the UI stores plain dictionaries in session state but uses Pydantic models for rendering.

### 4.2 Workspace Loader

`load_demo_workspace()` in `src/controlnexus/risk_inventory/demo.py` reads:

```text
sample_data/risk_inventory_demo/workspace.yaml
```

It builds a `RiskInventoryWorkspace` with:

- workspace metadata
- business units
- procedures
- level 1 risk taxonomy
- level 2 risk taxonomy loaded from config
- control taxonomy
- root-cause taxonomy
- bank controls aggregated from run fixtures
- KRI library
- per-process `RiskInventoryRun` objects

### 4.3 Workspace YAML Contents

`workspace.yaml` declares:

- `workspace_id`: `WS-DEMO-BANK`
- bank id and name
- enterprise level 1 risk taxonomy
- root cause taxonomy
- control taxonomy
- business units
- procedures
- run fixtures
- KRI library

The workspace fixture currently models three business units:

| Business Unit ID | Business Unit | Procedure Count | Current Run Count |
| --- | --- | ---: | ---: |
| `BU-PAYOPS` | Payment Operations | 2 | 1 |
| `BU-RETAIL` | Retail Banking & Onboarding | 1 | 1 |
| `BU-COMMLEND` | Commercial Lending | 1 | 1 |

The workspace declares four procedures:

| Procedure ID | Process | Business Unit | Has Run Fixture |
| --- | --- | --- | --- |
| `PROC-PAY-EXCEPTION` | Payment Exception Handling | Payment Operations | Yes |
| `PROC-PAY-RECON` | End-of-Day Wire Reconciliation | Payment Operations | No |
| `PROC-CUST-ONBOARD` | Retail Customer Onboarding (CIP / KYC) | Retail Banking & Onboarding | Yes |
| `PROC-CL-UNDERWRITE` | Commercial Loan Underwriting & Risk Rating | Commercial Lending | Yes |

The UI can list `End-of-Day Wire Reconciliation` as a procedure in the Knowledge Base, but it does not have a corresponding generated risk run. If selected through the current process selector path, it will not produce a process-specific run.

### 4.4 Run Fixtures

`workspace.yaml` loads these run fixture files:

```yaml
run_fixtures:
  - fixture: "payment_exception_handling.yaml"
  - fixture: "customer_onboarding.yaml"
  - fixture: "commercial_loan_underwriting.yaml"
```

Each fixture contains:

- a scenario block
- controls
- risks
- risk appetite framework
- executive summary

Current fixture counts:

| Fixture | Process | Controls | Risks |
| --- | --- | ---: | ---: |
| `payment_exception_handling.yaml` | Payment Exception Handling | 7 | 6 |
| `customer_onboarding.yaml` | Retail Customer Onboarding (CIP / KYC) | 5 | 4 |
| `commercial_loan_underwriting.yaml` | Commercial Loan Underwriting & Risk Rating | 5 | 4 |

### 4.5 Risk Run Loader

Each fixture is converted into a `RiskInventoryRun` by `load_demo_risk_inventory()`.

High-level loader sequence:

1. Resolve fixture path.
2. Read YAML payload.
3. Extract `scenario`.
4. Build a `controls` dictionary keyed by `control_id`.
5. Load the level 2 risk taxonomy from `config/risk_inventory/risk_taxonomy_crosswalk.yaml`.
6. Load scoring config through `MatrixConfigLoader`.
7. Instantiate:
   - `InherentRiskCalculator`
   - `ControlEnvironmentCalculator`
   - `ResidualRiskCalculator`
8. Build `ProcessContext` from the scenario.
9. Iterate over fixture risks and build `RiskInventoryRecord` objects.
10. Build `ExecutiveSummary`.
11. Build `RiskInventoryRun`.
12. Validate the run with `RiskInventoryValidator`.

### 4.6 Current Source Document Quirk

`load_demo_risk_inventory()` currently sets:

```python
source_documents=["demo fixture: payment_exception_handling.yaml"]
```

This is hard-coded for every demo run.

As a result:

- Payment Exception Handling correctly reports `demo fixture: payment_exception_handling.yaml`.
- Retail Customer Onboarding also reports `demo fixture: payment_exception_handling.yaml`, even though its real fixture is `customer_onboarding.yaml`.
- Commercial Loan Underwriting also reports `demo fixture: payment_exception_handling.yaml`, even though its real fixture is `commercial_loan_underwriting.yaml`.

The accurate fixture path is available in `run.run_manifest["fixture"]`. The UI should prefer `run_manifest.fixture` for audit-grade provenance until `source_documents` is corrected.

## 5. Core Object Graph And Relationships

The system of record is the Pydantic object graph in `src/controlnexus/risk_inventory/models.py`.

### 5.1 Workspace-Level Model

`RiskInventoryWorkspace` contains:

- `workspace_id`
- `bank_id`
- `bank_name`
- `business_units`
- `procedures`
- `risk_taxonomy_l1`
- `risk_taxonomy_l2`
- `control_taxonomy`
- `root_cause_taxonomy`
- `bank_controls`
- `kri_library`
- `runs`
- `created_at`

Important methods:

- `procedures_for_bu(bu_id)`
- `run_for_procedure(procedure_id)`
- `kris_for_taxonomy(taxonomy_id)`

### 5.2 Business Unit Relationship

`BusinessUnit` fields:

- `bu_id`
- `bu_name`
- `description`
- `head`
- `employee_count`
- `risk_profile_summary`
- `procedure_ids`

Relationship:

```text
BusinessUnit.bu_id -> Procedure.bu_id
BusinessUnit.procedure_ids -> Procedure.procedure_id values
```

The UI uses `workspace.procedures_for_bu(bu_id)` to filter procedures by business unit.

### 5.3 Procedure Relationship

`Procedure` fields:

- `procedure_id`
- `procedure_name`
- `bu_id`
- `process_id`
- `description`
- `owner`
- `last_reviewed`
- `cadence`
- `criticality`
- `related_systems`

Relationship:

```text
Procedure.process_id -> RiskInventoryRun.input_context.process_id
Procedure.procedure_id -> RiskInventoryWorkspace.run_for_procedure(procedure_id)
```

`run_for_procedure()` first finds the `Procedure`, then finds the run whose `input_context.process_id` matches `Procedure.process_id`.

### 5.4 Run Relationship

`RiskInventoryRun` fields:

- `run_id`
- `tenant_id`
- `bank_id`
- `input_context`
- `records`
- `executive_summary`
- `validation_findings`
- `config_snapshot`
- `export_paths`
- `events`
- `errors`
- `warnings`
- `run_manifest`
- `demo_mode`
- `created_at`

Relationship:

```text
RiskInventoryRun.input_context -> one process
RiskInventoryRun.records -> all risk records generated for that process
RiskInventoryRun.executive_summary -> process-level summary
RiskInventoryRun.validation_findings -> run-level validation output
RiskInventoryRun.config_snapshot -> scoring and configuration snapshot
RiskInventoryRun.run_manifest -> run provenance and execution metadata
```

### 5.5 Risk Record Relationship

`RiskInventoryRecord` is the primary per-risk object.

Fields:

- `risk_id`
- `process_id`
- `process_name`
- `product`
- `taxonomy_node`
- `applicability`
- `risk_statement`
- `exposure_metrics`
- `impact_assessment`
- `likelihood_assessment`
- `inherent_risk`
- `control_mappings`
- `control_environment`
- `residual_risk`
- `review_challenges`
- `evidence_references`
- `validation_findings`
- `risk_appetite`
- `action_plan`
- `coverage_gaps`
- `demo_record`

Relationship:

```text
RiskInventoryRecord.taxonomy_node.id -> RiskTaxonomyNode.id
RiskInventoryRecord.control_mappings[*].control_id -> fixture control_id
RiskInventoryRecord.evidence_references[*] -> fixture evidence_references
RiskInventoryRecord.exposure_metrics[*] -> fixture exposure_metrics or taxonomy defaults
RiskInventoryRecord.residual_risk -> deterministic residual matrix result
RiskInventoryRecord.review_challenges -> business review state
RiskInventoryRecord.action_plan -> management action plan from fixture
```

### 5.6 KRI Relationship

`KRIDefinition` fields:

- `kri_id`
- `kri_name`
- `risk_taxonomy_id`
- `metric_definition`
- `formula`
- `unit`
- `measurement_frequency`
- `data_source`
- `owner`
- `thresholds`
- `rationale`
- `escalation_path`
- `use_cases`
- `placement_guidance`

Relationship:

```text
KRIDefinition.risk_taxonomy_id -> RiskInventoryRecord.taxonomy_node.id
```

The UI calls:

```python
workspace.kris_for_taxonomy(record.taxonomy_node.id)
```

This means KRIs are recommended by risk taxonomy node, not by process id, business unit, or individual risk id.

## 6. Demo UI Structure

### 6.1 Demo Notice

When Demo Mode is active, `_render_demo_workspace()` renders a blue notice:

```text
Demo Mode - Demo Bank workspace loaded
(3 business units - 4 processes - N KRIs).
```

The counts come from:

- `len(workspace.business_units)`
- `len(workspace.procedures)`
- `len(workspace.kri_library)`

### 6.2 Scope Selector

The current demo selector is a two-step selector:

1. `Business Unit`
2. `Process Focus`

The business unit options are:

- `All Business Units`
- one option per `workspace.business_units[*].bu_name`

If `All Business Units` is chosen, `procedure_pool = workspace.procedures`.

If a specific business unit is chosen, the procedure pool is:

```python
workspace.procedures_for_bu(selected_bu.bu_id)
```

The process focus options are:

- `Workspace Dashboard (no process focus)`
- one option per procedure in `procedure_pool`

If the user chooses `Workspace Dashboard (no process focus)`, there is no selected run. Several tabs render workspace rollups or empty panels.

If the user chooses a process, `_render_demo_workspace()` finds the selected procedure and calls:

```python
selected_run = workspace.run_for_procedure(selected_proc.procedure_id)
```

### 6.3 Scope Controls

The former dominant scope metric strip has been removed. Scope is now expressed through compact Business Unit and Process Focus selectors. Knowledge-pack readiness is no longer rendered in the frontend.

### 6.4 Demo Tabs

The current demo creates these top-level tabs:

1. `Knowledge Base`
2. `Risk Inventory`
3. `Control Mapping`
4. `Gap Analysis`
5. `Review & Challenge`
6. `Executive Report`

There is no dedicated `Residual Risk`, `KRI Program`, or `Agent Run Trace` top-level tab. Residual risk and KRI content now render inside the selected risk profile. Source trace appears inside selected risk detail, review dossiers, and the Excel workbook.

## 7. Knowledge Base Tab

`_render_knowledge_base(workspace)` renders a read-only view of supplied bank data.

It contains these sub-tabs:

1. `Business Units`
2. `Processes`
3. `Risk Taxonomy (2-Tier)`
4. `Control Taxonomy`
5. `Controls Register`
6. `Obligations`
7. `KRI Library`

### 7.1 Business Units Sub-Tab

Rows are generated from `workspace.business_units`.

Columns:

- `Business Unit ID` from `bu.bu_id`
- `Business Unit` from `bu.bu_name`
- `Head` from `bu.head`
- `Employees` from `bu.employee_count`
- `Process Count` from `len(workspace.procedures_for_bu(bu.bu_id))`
- `Description` from `bu.description`
- `Risk Profile` from `bu.risk_profile_summary`

### 7.2 Processes Sub-Tab

Rows are generated from `workspace.procedures`.

Columns:

- `Process ID` from `p.procedure_id`
- `Process` from `p.procedure_name`
- `Business Unit` from lookup by `p.bu_id`
- `Owner` from `p.owner`
- `Criticality` from `p.criticality`
- `Review Cadence` from `p.cadence`
- `Last Reviewed` from `p.last_reviewed`
- `Systems` from `", ".join(p.related_systems)`

### 7.3 Risk Taxonomy Sub-Tab

This sub-tab has two tables.

Level 1 table rows are generated from `workspace.risk_taxonomy_l1`.

Columns:

- `Level 1 Code`
- `Enterprise Risk Category`
- `Definition`
- `Risk Subcategory Count`

Level 2 table rows are generated from `workspace.risk_taxonomy_l2`.

Columns:

- `Level 2 Code` from `node.id`
- `Enterprise Risk Category` from level 1 lookup or `node.level_1_category`
- `Risk Subcategory` from `node.level_2_category`
- `Definition` from `node.definition`
- `Regulatory Relevance` from `node.regulatory_relevance`

### 7.4 Control Taxonomy Sub-Tab

Rows are generated from `workspace.control_taxonomy`.

Columns:

- `Code`
- `Family`
- `Control Family`
- `Description`
- `Typical Evidence`

### 7.5 Controls Register Sub-Tab

Rows are generated from `workspace.bank_controls`.

`bank_controls` is not read directly from `workspace.yaml`. It is aggregated by `load_demo_workspace()` from each run fixture's `controls` list, keyed by `control_id`.

Columns:

- `Control ID`
- `Control`
- `Control Type`
- `Owner`
- `Frequency`
- `Design Effectiveness`
- `Operating Effectiveness`
- `Control Description`

### 7.6 KRI Library Sub-Tab

Rows are generated from `workspace.kri_library`.

The risk subcategory label is resolved through:

```python
l2_lookup = {node.id: node.level_2_category for node in workspace.risk_taxonomy_l2}
```

Columns:

- `KRI ID`
- `KRI`
- `Risk Subcategory`
- `Owner`
- `Frequency`
- `Green`
- `Amber`
- `Red`

## 8. Risk Inventory Tab

`_render_risk_inventory_combined(run, workspace)` is the current process-level and selected-risk risk inventory view.

Despite the function name, this view currently operates as a per-risk selector view:

1. Calls `_risk_selector(run, "ri_inventory_select")`.
2. Renders `_render_risk_header(record)`.
3. Renders rating tiles.
4. Renders risk statement and why-it-matters panels.
5. Renders impact dimensions.
6. Renders KRI recommendations.

### 8.1 Risk Selector

`_risk_selector()` creates one option per `run.records`.

Option text:

```text
{risk_id} - {level_2_category} ({level_1_category})
```

The selected index is mapped back into `run.records[index]`.

### 8.2 Risk Header

`_render_risk_header(record)` renders:

- `Risk Record` kicker
- `record.risk_id`
- `record.taxonomy_node.level_2_category`
- enterprise risk category chip
- risk subcategory chip
- process chip
- inherent risk badge
- residual risk badge
- management response badge

The header does not show source citations directly.

### 8.3 Rating Tiles

The tab renders four rating tiles:

- `Inherent Risk` from `record.inherent_risk.inherent_rating.value`
- `Control Environment` from `record.control_environment.control_environment_rating.value`
- `Residual Risk` from `record.residual_risk.residual_rating.value`
- `Management Response` from `record.residual_risk.management_response.response_type.value.title()`

### 8.4 Executive Risk Statement

The statement text is generated by `_risk_statement_display(record)`.

It starts from:

```python
record.risk_statement.risk_description
```

Then it appends root-cause language if needed:

```text
Root-cause lens: {first three causes}
```

Source of causes:

1. `record.risk_statement.causes`
2. fallback to `record.taxonomy_node.typical_root_causes`

The fixture loader also already applies `_with_root_cause_verbiage()` to `risk_statement.risk_description`, so the root-cause lens may already be embedded before the UI runs.

### 8.5 Risk Event

Rendered from:

```python
record.risk_statement.risk_event
```

In demo fixtures, this usually comes from `risks[*].risk_event`.

Fallback in `load_demo_risk_inventory()`:

1. `node.example_risk_statements[0]`, if available
2. generated `_risk_description(node, context)`

### 8.6 Affected Stakeholders

Rendered from:

```python
record.risk_statement.affected_stakeholders
```

In demo generation, this comes from the fixture if supplied, otherwise from `context.stakeholders`.

### 8.7 Root-Cause Note

`_render_root_cause_deferred_note()` tells the user that root-cause taxonomy is relevant but the detailed root-cause taxonomy UI is intentionally deferred.

It shows the count of configured root-cause taxonomy entries if `workspace` is provided.

### 8.8 Why It Matters

This panel shows:

- `Impact`: `int(record.impact_assessment.overall_impact_score)`
- `Frequency`: `int(record.likelihood_assessment.likelihood_score)`
- `Mapped Controls`: `len(record.control_mappings)`
- frequency rationale from `record.likelihood_assessment.rationale`

### 8.9 Impact Dimensions

Rows are generated from `record.impact_assessment.dimensions`.

Columns:

- `Impact Dimension`
- `Impact Score`
- `Assessment Rationale`

### 8.10 KRI Recommendations

The Risk Inventory tab calls:

```python
_render_kri_recommendations(record, workspace, include_program_design=False)
```

If workspace is available, candidate KRIs are:

```python
workspace.kris_for_taxonomy(record.taxonomy_node.id)
```

If no candidates exist, the UI shows deterministic KRI design guidance using exposure metrics as the starting point.

If candidates exist, each KRI card shows:

- KRI ID
- KRI name
- Owner
- Frequency
- Source
- Definition
- Formula
- Unit
- Green threshold
- Amber threshold
- Red threshold
- CRO rationale
- Escalation path
- Placement guidance

## 9. Control Mapping Tab

The Control Mapping tab has two modes:

1. Workspace rollup mode when no process focus is selected.
2. Selected process mode when a run exists.

### 9.1 Workspace Rollup Mode

If there is no selected run, the demo calls:

```python
_render_workspace_control_mapping(workspace, selected_bu_id)
```

This flattens available process runs into rows with `_workspace_control_mapping_rows()`.

Each row represents one risk record and includes:

- `Business Unit ID`
- `Business Unit`
- `Process ID`
- `Process`
- `Risk Record ID`
- `Enterprise Risk Category`
- `Risk Subcategory`
- `Residual Risk Rating`
- `Mapped Controls`
- `Coverage Status`

Coverage status is calculated by `_record_coverage_status(record)`:

- `Coverage Gap` if no controls are mapped.
- `Gaps Noted` if `record.coverage_gaps` contains non-root-cause gaps.
- `Strong Coverage` if all mapping coverage values are strong/full.
- `Mixed Coverage` if any mapping is strong/full.
- `Partial Coverage` otherwise.

The rollup then renders:

- metric cards
- BU x L1 risk category matrix
- risk type detail table
- coverage status table
- risk-to-control detail table

### 9.2 Process Mode

If a selected run exists, the tab calls `_render_control_mapping(run)`.

It first renders `_render_control_mapping_run_summary(run)`:

- Risk Records
- Mapped Controls
- Control Types
- High+ Residual
- count of full/strong coverage mappings

Then it calls `_risk_selector(run, "ri_mapping_select")`.

This means the selected risk in the Control Mapping tab is independent from the selected risk in the Risk Inventory tab because each tab uses a different Streamlit widget key.

For the selected risk, the UI renders a control card per `record.control_mappings`.

Each control card shows:

- `mapping.control_id`
- `mapping.control_name`
- `mapping.control_type`
- `mapping.mitigation_rationale`
- coverage assessment badge
- design effectiveness badge
- operating effectiveness badge

Finally, the tab renders all mapped controls in the process using `_run_control_mapping_rows(run)`.

## 10. Residual Risk Detail

There is no longer a top-level `Residual Risk` tab. Residual risk content is rendered inside the selected `Risk Inventory` profile under the snapshot row, scoring rationale, controls/coverage, mitigation plan, and review/challenge expanders.

The legacy `_render_residual_risk(run, workspace)` helper remains in code as a compatibility/reference helper, but it is not part of the active demo tab list.

It:

1. Calls `_risk_selector(run, "ri_residual_select")`.
2. Renders `_render_risk_header(record)`.
3. Shows rating tiles.
4. Writes residual rationale.
5. Shows recommended action.
6. Renders control coverage.
7. Renders effectiveness detail.
8. Renders review/challenge summary.

### 10.1 Residual Risk Rating Inputs

The residual rating comes from:

```python
record.residual_risk.residual_rating.value
```

That value is generated by `ResidualRiskCalculator.calculate()` from:

- `record.inherent_risk.inherent_label`
- `record.control_environment.control_environment_rating`
- `config/risk_inventory/residual_risk_matrix.yaml`
- `config/risk_inventory/management_response_rules.yaml`

### 10.2 Control Coverage Section

`_render_control_coverage(record)` displays:

- mapped control count
- strong/satisfactory count
- control type count
- mapped control table
- coverage by control type table
- coverage gaps

Coverage gaps are taken from `record.coverage_gaps` after filtering out root-cause-only wording.

### 10.3 Effectiveness Detail Section

`_render_effectiveness_detail(record)` displays:

- count of strong design controls
- count of controls needing operating improvement
- total open issue count
- high/critical open issue count
- effectiveness by control table
- open issue table if any issues exist

Control effectiveness fields come from `ControlMapping.design_effectiveness`, `ControlMapping.operating_effectiveness`, and `ControlMapping.evidence_quality`.

### 10.4 Review Summary

`_render_residual_review_summary(record)` reads the first review challenge:

```python
review = record.review_challenges[0]
```

It renders:

- review status
- approval status
- reviewer
- reviewer comments
- fields requiring review

## 11. Review & Challenge Tab

`_render_review(run)` is currently selected-risk oriented.

It:

1. Calls `_risk_selector(run, "ri_review_select")`.
2. Renders the risk header.
3. Reads the first `ReviewChallengeRecord`.
4. Renders a `Review Status` selectbox.
5. Renders a `Challenge Comments` text area.
6. Renders fields requiring review.
7. Renders validation findings for that record.

Important implementation detail:

The Streamlit widgets collect user input into widget state, but the code does not currently write changes back into the underlying `RiskInventoryRun` object. This makes the review UI interactive as a frontend surface, but not persisted into the risk inventory model.

## 12. Executive Report Tab

`_render_executive(run)` renders:

- summary metric cards
- executive summary headline
- key messages
- top residual risks
- recommended actions
- executive risk table
- Excel workbook download button

The executive summary comes from `run.executive_summary`.

In demo mode, that summary is loaded from fixture `executive_summary` if present, otherwise generated from the records.

The download button uses:

```python
risk_inventory_excel_bytes(run)
```

## 13. Non-Demo User Workflow

When Demo Mode is disabled, `_render_user_workflow()` creates these tabs:

1. `Overview`
2. `Input / Upload`
3. `Risk Inventory`
4. `Control Mapping`
5. `Residual Risk`
6. `Review & Challenge`
7. `Executive Report`

Before a run exists, most tabs show empty states.

### 13.1 Overview

If no user run exists, `_render_overview_user(None)` renders `_render_empty_state()`.

If a run exists, it renders:

- summary metrics
- pipeline stages
- executive takeaway
- residual distribution
- Excel download

### 13.2 Input / Upload

`_render_input_and_maybe_run()` drives user-supplied workflow creation.

It includes:

- existing bank knowledge placeholder tables
- process document upload
- structured context upload
- control upload
- review extracted context fields
- document analysis preview
- control preview
- run button

### 13.3 Process Document Upload

`_document_upload()` accepts:

- PDF
- TXT
- Markdown

It calls:

```python
analyze_process_document(filename, content)
```

If the user clicks `Load sample process document`, it reads:

```text
sample_data/risk_inventory_demo/payment_exception_policy.md
```

### 13.4 Document Analysis Generation

`analyze_process_document()` creates `DocumentAnalysis`.

Generated fields include:

- `filename`
- `text`
- `process_id`
- `process_name`
- `product`
- `business_unit`
- `description`
- `systems`
- `stakeholders`
- `detected_risk_categories`
- `detected_controls`
- `exposure_cues`
- `obligations`
- `document_stats`

The analyzer is deterministic and rule-based. It extracts labeled values, uses keyword inference, detects common control phrases, identifies exposure cues with regex, and captures obligation-like sentences.

### 13.5 Structured Context Upload

`_structured_context_upload()` accepts JSON/YAML and returns a dictionary.

This dictionary overrides or supplements the extracted defaults in `_context_defaults()`.

### 13.6 Control Upload

`_control_upload()` accepts:

- Excel (`.xlsx`, `.xls`)
- JSON
- YAML

If no file is provided, the user can use starter payment controls. Those are loaded from `payment_exception_handling.yaml`.

Excel input is ingested through `ingest_excel(tmp_path)` and converted to a minimal control inventory with:

- `control_id`
- `control_name`
- `control_type`
- `description`
- default `design_rating`
- default `operating_rating`

### 13.7 User Run Execution

When the user clicks `Run Risk Inventory Workflow`, `_render_input_and_maybe_run()` builds `process_context` and invokes:

```python
build_risk_inventory_graph().compile().invoke(...)
```

Input state includes:

- `run_id`
- `tenant_id`
- `process_context`
- `control_inventory`
- `max_risks`

The resulting `final_report` is stored in:

```python
st.session_state["risk_inventory_user_run"]
```

## 14. Non-Demo Graph Generation Path

The deterministic graph lives in `src/controlnexus/risk_inventory/graph.py`.

Node sequence:

```text
context_ingestion
-> taxonomy_applicability
-> risk_statement_generation
-> exposure_metrics
-> impact_assessment
-> likelihood_assessment
-> inherent_risk_calculator
-> control_mapping
-> control_effectiveness
-> control_environment_calculator
-> residual_risk_calculator
-> review_challenge
-> final_assembly
-> excel_export
-> END
```

### 14.1 Context Ingestion

`context_ingestion_node()` validates raw input as `ProcessContext`.

Generated output:

- `input_context`

### 14.2 Taxonomy Applicability

`taxonomy_applicability_node()` loads taxonomy nodes and matches them to process text using `find_applicable_nodes()`.

Generated output:

- `taxonomy_nodes`

Matching logic:

```text
If any configured applicable process pattern appears in the process text,
select that taxonomy node.
If no node matches and include_all_if_none is true, return all nodes.
```

### 14.3 Risk Statement Generation

`risk_statement_generation_node()` creates an initial risk record shell for each selected taxonomy node.

Generated fields:

- `risk_id`
- `process_id`
- `process_name`
- `product`
- `taxonomy_node`
- `applicability`
- `risk_statement`

The risk statement is deterministic and process-specific. It combines the process name, product, taxonomy node category, root cause, and contextual consequences.

### 14.4 Exposure Metrics

`exposure_metrics_node()` creates exposure metrics from `node.common_exposure_metrics`.

Generated fields:

- `metric_name`
- `metric_value`
- `description`
- `source`
- `supports`

The metric value is inferred from process context using `_metric_value_from_context()`. It tries to extract dollars, percentages, counts, or daily exposure wording.

### 14.5 Impact Assessment

`impact_assessment_node()` creates impact dimension scores.

It uses taxonomy node `likely_impact_dimensions`.

Likely dimensions get `SIGNIFICANT`; other dimensions get `MEANINGFUL`.

Overall impact equals the maximum dimension score.

### 14.6 Likelihood Assessment

`likelihood_assessment_node()` assigns:

- `MEDIUM_HIGH` if the process description contains `daily`, `high-value`, or `payment`
- otherwise `MEDIUM_LOW`

It generates a rationale and a default assumption.

### 14.7 Inherent Risk Calculator

`inherent_risk_calculator_node()` calculates inherent risk using:

- impact score
- likelihood score
- configured inherent risk matrix

Output is `InherentRiskAssessment`.

### 14.8 Control Mapping

`control_mapping_node()` matches controls to taxonomy node guidance using `_match_controls()`.

Matching considers:

- taxonomy common controls
- taxonomy related control types
- control names
- control descriptions
- control type

Generated output is `control_mappings`.

### 14.9 Control Effectiveness

`control_effectiveness_node()` currently passes records through unchanged for non-demo mode.

### 14.10 Control Environment

`control_environment_calculator_node()` aggregates mapped control design and operating ratings.

It takes the worse rating across mapped controls. If no ratings are available, `_worst()` returns `Inadequate`.

Generated output is `ControlEnvironmentAssessment`.

### 14.11 Residual Risk

`residual_risk_calculator_node()` calculates residual risk using:

- `InherentRiskAssessment`
- `ControlEnvironmentAssessment`
- residual matrix
- management response rules

### 14.12 Review Challenge

`review_challenge_node()` creates review challenge records.

It also creates a basic evidence reference:

- evidence type: `Process context`
- description: `Generated from supplied process context and control inventory.`
- source: `Risk Inventory Builder`

### 14.13 Final Assembly

`final_assembly_node()` builds the final `RiskInventoryRun`.

It adds:

- executive summary
- config snapshot
- run manifest
- validation findings

## 15. Demo Run Generation Details

For demo fixture paths, `load_demo_risk_inventory()` uses fixture values wherever available and deterministic fallbacks otherwise.

### 15.1 Process Context

Generated from fixture `scenario`:

- `process_id`
- `process_name`
- `product`
- `business_unit`
- `description`
- `systems`
- `stakeholders`
- `source_documents`

As noted above, `source_documents` is currently hard-coded and should be treated carefully.

### 15.2 Taxonomy Node

Each fixture risk has:

```yaml
taxonomy_node_id: "RIB-..."
```

The loader resolves it through:

```python
taxonomy = {node.id: node for node in load_risk_inventory_taxonomy()}
node = taxonomy[spec["taxonomy_node_id"]]
```

### 15.3 Impact Assessment

Fixture risk fields:

- `impact_scores`
- optional `impact_rationales`
- `overall_impact_score`
- optional `overall_impact_rationale`

If a dimension rationale is missing, `_impact_rationale()` generates fallback text.

### 15.4 Likelihood Assessment

Fixture risk fields:

- `likelihood_score`
- `likelihood_rating`
- `likelihood_rationale`
- `assumptions`

If absent, the loader generates generic payment-exception-oriented defaults.

### 15.5 Inherent Risk

Calculated by `InherentRiskCalculator`.

Inputs:

- `impact.overall_impact_score`
- `likelihood.likelihood_score`

Source config:

- `config/risk_inventory/inherent_risk_matrix.yaml`

### 15.6 Control Mapping

Each fixture risk has:

```yaml
mapped_controls:
  - CTRL-...
```

For each mapped control id, `_build_control_mapping(control, node)` creates:

- `control_id`
- `control_name`
- `control_type`
- `control_description`
- `mitigation_rationale`
- `mapped_root_causes`
- `coverage_assessment`
- `design_effectiveness`
- `operating_effectiveness`
- `open_issues`
- `evidence_quality`

Control mapping data comes from the fixture `controls` section.

### 15.7 Control Environment

The loader computes aggregate design and operating ratings:

- `_aggregate_design_rating(mappings)`
- `_aggregate_operating_rating(mappings)`

Each returns the worst rating among mapped controls.

Then `ControlEnvironmentCalculator` takes the worse of aggregate design and aggregate operating.

### 15.8 Residual Risk

Calculated by `ResidualRiskCalculator`.

Inputs:

- inherent risk
- control environment
- configured residual matrix
- management response rules
- fixture `recommended_action`

### 15.9 Evidence References

Fixture risk field:

```yaml
evidence_references:
  - evidence_id
    evidence_type
    description
    source
```

The same list is attached to:

- `record.applicability.evidence_refs`
- `record.evidence_references`

If the fixture has no references, the loader creates one default demo reference.

### 15.10 Exposure Metrics

Fixture risk field:

```yaml
exposure_metrics:
  - metric_name
    metric_value
    metric_unit
    description
    source
    supports
```

If fixture metrics are missing, `_build_exposure_metrics()` uses taxonomy `common_exposure_metrics` and generated demo values.

### 15.11 Review

Fixture risk field:

```yaml
review:
  review_status
  reviewer
  challenge_comments
  challenged_fields
  approval_status
```

The loader creates one `ReviewChallengeRecord` per risk.

### 15.12 Action Plan

Fixture risk field:

```yaml
action_plan:
  - action
    owner
    due_date
    status
    priority
```

The loader creates `ActionItem` entries.

The current UI does not render action plans prominently in the frontend. They are preserved in the model and exported.

### 15.13 Risk Appetite

Fixture risk field:

```yaml
risk_appetite:
  threshold
  statement
  status
  category
```

The loader creates a `RiskAppetite` object when present.

The current UI does not have a dedicated risk appetite tab.

## 16. Current Demo Inventory Summary

### 16.1 Payment Exception Handling

Run:

- `DEMO-RI-PAYEX-001`
- process id: `PROC-PAY-EXCEPTION`
- business unit: Payment Operations
- records: 6
- validation findings: 0

Risk records:

| Risk ID | Taxonomy ID | Category | Subcategory | Controls | Metrics | Evidence Refs | Residual |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `RI-DEMO-001` | `RIB-BPR` | Operational | Business Process Risk | 3 | 4 | 1 | Low-18 |
| `RI-DEMO-002` | `RIB-DM` | Operational | Data Management Risk | 2 | 3 | 1 | Low-18 |
| `RI-DEMO-003` | `RIB-CYB` | Cyber | IT Security / Cybersecurity Risk | 1 | 3 | 1 | High-36 |
| `RI-DEMO-004` | `RIB-RR` | Operational | Regulatory Reporting Risk | 2 | 3 | 1 | Medium-24 |
| `RI-DEMO-005` | `RIB-ORS` | Operational | Operational Resiliency Risk | 2 | 4 | 1 | Medium-24 |
| `RI-DEMO-006` | `RIB-TPR` | Operational | Third Party Risk | 1 | 3 | 1 | Low-12 |

### 16.2 Retail Customer Onboarding

Run:

- `DEMO-RI-CUSTONB-001`
- process id: `PROC-CUST-ONBOARD`
- business unit: Retail Banking & Onboarding
- records: 4
- validation findings: 3 warnings

Risk records:

| Risk ID | Taxonomy ID | Category | Subcategory | Controls | Metrics | Evidence Refs | Residual |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `RI-CONB-001` | `RIB-COM` | Regulatory Compliance | Compliance Risk | 3 | 3 | 1 | High-36 |
| `RI-CONB-002` | `RIB-EFR` | Operational | External Fraud Risk | 2 | 3 | 1 | Medium-27 |
| `RI-CONB-003` | `RIB-PRI` | Cyber | Privacy Risk | 2 | 3 | 1 | Low-18 |
| `RI-CONB-004` | `RIB-DM` | Operational | Data Management Risk | 2 | 2 | 1 | Low-18 |

Validation warnings are likelihood-rationale warnings: the validator wants likelihood rationales to explicitly reference frequency, exposure, history, or process drivers.

### 16.3 Commercial Loan Underwriting

Run:

- `DEMO-RI-CLUW-001`
- process id: `PROC-CL-UNDERWRITE`
- business unit: Commercial Lending
- records: 4
- validation findings: 4 warnings

Risk records:

| Risk ID | Taxonomy ID | Category | Subcategory | Controls | Metrics | Evidence Refs | Residual |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `RI-CLUW-001` | `RIB-MDL` | Operational | Model Risk | 2 | 3 | 1 | High-36 |
| `RI-CLUW-002` | `RIB-BPR` | Operational | Business Process Risk | 2 | 2 | 1 | Low-12 |
| `RI-CLUW-003` | `RIB-CON` | Operational | Contract Risk | 1 | 2 | 1 | Low-6 |
| `RI-CLUW-004` | `RIB-IFR` | Operational | Internal Fraud Risk | 2 | 1 | 1 | Low-18 |

Validation warnings are likelihood-rationale warnings.

## 17. Provenance And "Not Hallucination" Map

This section maps frontend-visible information to its origin.

| Information Type | Frontend Location | Model Field | Source |
| --- | --- | --- | --- |
| Business unit name | Scope selector, Knowledge Base | `BusinessUnit.bu_name`, `ProcessContext.business_unit` | `workspace.yaml` and scenario fixture |
| Business unit head | Knowledge Base | `BusinessUnit.head` | `workspace.yaml` |
| Process owner | Knowledge Base | `Procedure.owner` | `workspace.yaml` |
| Process systems | Knowledge Base, risk statement chips | `Procedure.related_systems`, `ProcessContext.systems` | `workspace.yaml` and scenario fixture |
| Process source documents | model only currently | `ProcessContext.source_documents` | hard-coded loader value; `run_manifest.fixture` is more accurate |
| Risk taxonomy category | all risk views | `RiskTaxonomyNode.level_1_category`, `level_2_category` | `config/risk_inventory/risk_taxonomy_crosswalk.yaml` |
| Root causes | risk statement | `RiskStatement.causes`, `RiskTaxonomyNode.typical_root_causes` | risk fixture or taxonomy |
| Risk description | Risk Inventory | `RiskStatement.risk_description` | risk fixture, loader fallback, root-cause append helper |
| Risk event | Risk Inventory | `RiskStatement.risk_event` | risk fixture or taxonomy example fallback |
| Exposure metrics | Excel export, KRI guidance | `ExposureMetric` | risk fixture or taxonomy metric fallback |
| Impact score | Risk Inventory, Excel | `ImpactAssessment` | risk fixture; fallback by loader |
| Frequency score | Risk Inventory, Excel | `LikelihoodAssessment` | risk fixture; fallback by loader or graph |
| Inherent risk | tiles, Excel | `InherentRiskAssessment` | deterministic matrix calculation |
| Mapped controls | Control Mapping | `ControlMapping` | risk fixture `mapped_controls` plus fixture controls |
| Control evidence quality | Risk Inventory profile | `EvidenceQuality` | fixture control `evidence_quality` |
| Open issues | Risk Inventory profile | `OpenIssue` | fixture control `open_issues` |
| Control environment | Residual Risk tab | `ControlEnvironmentAssessment` | deterministic worse-of control ratings |
| Residual risk | Risk Inventory, Residual Risk, Excel | `ResidualRiskAssessment` | deterministic residual matrix |
| Management response | badges, residual view, Excel | `ManagementResponse` | management response rules and fixture recommended action |
| KRI recommendations | Risk Inventory | `KRIDefinition` | `workspace.yaml` KRI library keyed by taxonomy node |
| Review status | Review tab | `ReviewChallengeRecord` | risk fixture or graph default |
| Validation findings | Review tab, Excel | `ValidationFinding` | `RiskInventoryValidator` |
| Excel workbook | Executive tab download | generated workbook | `risk_inventory_excel_bytes(run)` |

## 18. Export Surface

The Excel export is generated by `src/controlnexus/risk_inventory/export.py`.

`build_risk_inventory_workbook(run)` creates sheets:

- `Executive Summary`
- `Risk Inventory`
- `Inherent Risk Assessment`
- `Control Mapping`
- `Control Effectiveness`
- `Residual Risk Assessment`
- `Review and Challenge`
- `Scoring Matrices`
- `Configuration Snapshot`
- `Validation Findings`

This export is often more complete than the current frontend because it includes fields not prominently exposed in the UI, such as risk appetite and detailed inventory row fields.

## 19. Styling And Frontend Mechanics

The Risk Inventory Builder UI uses inline CSS injected by `_inject_risk_inventory_css()`.

Important UI classes:

- `.ri-hero`
- `.ri-toggle-panel`
- `.ri-notice`
- `.ri-scope-lens`
- `.ri-flow`
- `.ri-metric`
- `.ri-risk-card`
- `.ri-control-card`
- `.ri-statement`
- `.ri-deferred-note`
- `.ri-badge`
- `.ri-chip`
- `.ri-rating-tile`
- `.ri-fact-grid`
- `.ri-kri-card`

The table renderer `_render_table()` normalizes values, chooses row heights, and configures column widths/alignment using Streamlit column config.

This custom table renderer is used across the UI to improve readability over raw `st.dataframe(...)`.

## 20. Session State

Current session keys used by the Risk Inventory Builder include:

- `demo_mode`
- `risk_inventory_workspace`
- `risk_inventory_user_run`
- `risk_inventory_document_analysis`
- `ri_loaded_doc_name`
- `ri_demo_bu_choice`
- `ri_demo_proc_choice`
- `ri_process_name`
- `ri_process_id`
- `ri_product`
- `ri_bu`
- `ri_systems`
- `ri_stakeholders`
- `ri_description`
- `ri_inventory_select`
- `ri_mapping_select`
- `ri_residual_select`
- `ri_review_select`
- per-risk review widget keys
- Excel download keys

The demo workspace is cached as dictionaries in session state and revalidated as Pydantic models on render.

## 21. Current Implementation Gaps And Design Implications

### 21.1 Source Trace Is Implicit

The data model has enough provenance for a source trace view:

- `run.input_context.source_documents`
- `run.run_manifest.fixture`
- `record.evidence_references`
- `record.applicability.evidence_refs`
- `record.exposure_metrics[*].source`
- `mapping.evidence_quality`
- `mapping.open_issues`
- `workspace.kri_library[*].data_source`
- `run.config_snapshot`

However, the frontend does not currently have a dedicated `Source Trace` tab. Provenance appears in multiple places rather than in one audit-oriented view.

### 21.2 Source Documents Should Stay Fixture-Specific

`ProcessContext.source_documents` should continue to use the fixture name that generated each run, not a hard-coded payment exception fixture. `run.run_manifest["fixture"]` remains the reliable source of truth for which YAML fixture generated a run.

### 21.3 Business Unit Still Leads The Demo Interaction

The current demo starts with business unit selection and then process selection. The target mental model is process-first: show a process, then show its business owners and provenance. That requires changing the selector order and rendering process context as the primary object.

### 21.4 Risk Detail Is Consolidated But Can Be Made Richer

Per-risk details now live in the `Risk Inventory` workbench and reuse one selected risk id in session state. The next improvement is better table row selection and richer evidence/rationale grouping, especially when moving beyond Streamlit's native table limitations.

### 21.5 Review Edits Are Not Persisted Into The Run

Review status and challenge comments widgets do not currently update `RiskInventoryRun`.

### 21.6 Demo Process Should Keep A Run Fixture

The default demo target is one process, `PROC-PAY-EXCEPTION`, backed by `payment_exception_handling.yaml`. Broader workspace fixtures can remain available for explicit regression coverage, but the Demo Mode toggle should continue to open only the focused payment exception process.

### 21.7 Root-Cause Taxonomy UI Is Deferred

The root-cause taxonomy is loaded in the workspace model and referenced in risk statement text, but there is no complete root-cause detail UI.

## 22. Recommended Frontend Design Direction

The strongest next frontend design is the workbench now implemented in `Risk Inventory`:

1. Keep Business Unit and Process Focus as compact scope controls, not dominant page chrome.
2. Keep knowledge-pack readiness inside the `Knowledge Base` tab as an expander.
3. Use a single selected risk id in Streamlit session state.
4. Render a left-side risk list/table and a right-side consolidated risk detail profile.
5. Move risk-specific residual risk, KRI, evidence, issues, mitigation, control gaps, synthetic controls, and review/challenge content into expandable sections on the risk detail profile.
6. Show a per-risk impact-by-frequency heatmap in the detail panel.
7. Show a portfolio business-unit-by-risk-category heatmap when no process focus is selected.
8. Keep `Control Mapping` and `Gap Analysis` as process or workspace summary tabs.
9. Keep traceability visible in selected risk details, review dossiers, workbook source trace, and configuration snapshot.
10. Persist review edits into a review-state object and include them in the executive workbook.

The next meaningful frontend upgrade is not adding more tabs. It is improving selection ergonomics, richer detail expansion, stronger traceability, workbook polish, and eventually replacing Streamlit table limitations with a production web UI once the demo narrative is proven.

## 23. Minimum Data Contract For A Future ASI Consumer

A downstream system that wants to reason over this demo should treat these as canonical identifiers:

- Workspace: `RiskInventoryWorkspace.workspace_id`
- Business unit: `BusinessUnit.bu_id`
- Process: `Process.process_id`
- Legacy alias: `Procedure.procedure_id`
- Run: `RiskInventoryRun.run_id`
- Process context: `RiskInventoryRun.input_context.process_id`
- Risk record: `RiskInventoryRecord.risk_id`
- Taxonomy node: `RiskInventoryRecord.taxonomy_node.id`
- Control: `ControlMapping.control_id`
- KRI: `KRIDefinition.kri_id`
- Evidence reference: `EvidenceReference.evidence_id`
- Validation finding: `ValidationFinding.finding_id`

The most important joins are:

```text
BusinessUnit.bu_id
  -> Process.bu_id

Process.process_id
  -> RiskInventoryRun.input_context.process_id

RiskInventoryRun.records[*].taxonomy_node.id
  -> RiskInventoryWorkspace.kri_library[*].risk_taxonomy_id

RiskInventoryRecord.control_mappings[*].control_id
  -> fixture controls[*].control_id
  -> RiskInventoryWorkspace.bank_controls[*].control_id

RiskInventoryRecord.evidence_references[*]
  -> fixture risks[*].evidence_references[*]

RiskInventoryRecord.exposure_metrics[*]
  -> fixture risks[*].exposure_metrics[*]
```

## 24. Summary

The demo frontend is a Streamlit presentation layer over a deterministic Pydantic object graph. Demo Mode is powered by YAML fixtures and configuration files, not by live LLM calls. Risk scores are matrix-calculated. Controls, evidence quality, open issues, KRIs, and action plans are all available in the object graph. The current UI surfaces much of this information, but provenance is distributed across tabs and should be centralized for the "not hallucinated" story.

The deepest current truth is:

```text
workspace.yaml defines the demo bank, business units, procedures, taxonomies, and KRI library.
run fixture YAML files define scenarios, controls, risks, evidence, metrics, review records, and action plans.
demo.py converts those fixtures into RiskInventoryRun objects.
calculators.py deterministically computes inherent, control environment, and residual risk.
validator.py checks matrix consistency and rationale quality.
risk_inventory_tab.py renders the Streamlit frontend from those objects.
export.py projects the same run into Excel.
```
