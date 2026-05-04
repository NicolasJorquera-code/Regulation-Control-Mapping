# Risk Inventory Builder

Risk Inventory Builder extends ControlNexus from control generation and gap analysis into an executive risk inventory workbench. It is designed for a financial-services demo audience, but the code and YAML knowledge packs remain institution-agnostic and use only fictional sample data.

The core product question is:

```text
Given business-unit context, process evidence, policies, obligations, issues,
controls, KRIs, taxonomies, and scoring matrices, what risks should exist,
how material are they, what controls address them, what gaps remain, and what
residual exposure needs review?
```

## Architecture

The capability is additive and reuses the existing ControlNexus architecture:

- `src/controlnexus/risk_inventory/` contains the risk inventory object graph, calculators, validators, knowledge-pack loader, deterministic workflow services, agent tools, and Excel export.
- Modular YAML knowledge packs under `sample_data/risk_inventory_demo/packs/` provide business units, processes, controls, issues, KRIs, obligations, evidence, taxonomies, appetite, and run fixtures.
- Streamlit renders the `Risk Inventory Builder` tab as a compact executive workbench.
- Pydantic models validate loaded data and preserve backward-compatible `Procedure` aliases while presenting `Process` in the UI.

The typed `RiskInventoryRun` object is the system of record. Streamlit session state captures review edits for the current demo session. Excel is an export/reporting layer.

```text
Knowledge Pack
-> Validation
-> Taxonomy Applicability
-> Risk Statement
-> Exposure Metrics
-> Impact + Frequency
-> Inherent Risk Matrix
-> Control Coverage Mapping
-> Gap Analysis + Synthetic Control Recommendations
-> Residual Risk Matrix
-> KRI Recommendation
-> Review & Challenge
-> Executive Report / Excel Export
```

## Deterministic Scoring

Scoring matrices are config-driven under `config/risk_inventory/`:

- `impact_scales.yaml`
- `frequency_scale.yaml`
- `likelihood_scale.yaml` for backward-compatible internal loaders and tests
- `inherent_risk_matrix.yaml`
- `control_effectiveness_criteria.yaml`
- `residual_risk_matrix.yaml`
- `management_response_rules.yaml`

The UI and executive exports use `Frequency` as the user-facing event-rate term. Internal calculators may still use `LikelihoodAssessment` to avoid breaking existing deterministic scoring behavior.

LLM agents may recommend rationale, mappings, statements, KRIs, and synthetic controls. They cannot silently override impact, frequency, inherent risk, control environment, residual risk, or management response calculations.

## Demo Mode

The Risk Inventory Builder includes a `Demo Mode` toggle. When enabled, it loads the generic `Large Global Bank` workspace:

- 5 business units
- 10 processes
- 10 deterministic risk inventory runs
- 84 controls across the reusable fixture pack
- KRIs, issues, evidence, obligations, root causes, appetite, trace events, and workbook export data

The top-level demo tabs are intentionally reduced:

- `Knowledge Base`
- `Risk Inventory`
- `Control Mapping`
- `Gap Analysis`
- `Review & Challenge`
- `Executive Report`

The former `Process Map`, `Residual Risk`, `KRI Program`, and `Agent Run Trace` tabs are consolidated into the workbench and export story. Selecting a process opens an executive command view with a left risk queue, central risk dossier, right decision stack, controls, gaps, KRIs, evidence, mitigation, review, and an impact-by-frequency heatmap. With no process focus selected, the view shows portfolio BU risk differences, a business-unit-by-risk-category heatmap, divergence drivers, and aggregated inventory.

## Knowledge Packs

Demo data is loaded from:

```text
sample_data/risk_inventory_demo/workspace.yaml
sample_data/risk_inventory_demo/packs/
```

The `Knowledge Base` tab focuses on the modular source packs: profile archetype, business units, processes, taxonomies, controls, obligations, and KRI library. It also surfaces the business-unit risk capture matrix so the demo makes clear how different BUs capture different risk types without adding a new tab.

## Executive Workbook

Demo Mode exports a full-workspace Excel artifact by default. It includes a cover page, executive summary, BU heatmap, BU risk breakdown, process inventory, risk dossiers, control gaps, synthetic control recommendations, KRI dashboard, reviewer workflow, source trace, and configuration snapshot. Reviewer decisions captured in Streamlit session state are merged into the workbook.

APQC is optional process-normalization metadata only. A process can include:

```yaml
apqc_crosswalk:
  framework: "APQC Banking PCF"
  version: "7.2.2"
  process_id: "optional"
  process_name: "optional"
  confidence: 0.0
  rationale: "optional"
```

APQC crosswalks can help normalize process names and support traceability, but policy documents, process documents, controls, obligations, issues/events, evidence, KRIs, taxonomies, and scoring YAML drive risk identification and scoring.

## Document Ingestion

The `Input / Upload` tab accepts PDF, TXT, and Markdown policy or process documents. The document is parsed locally and converted into reviewable process context before the graph runs.

The deterministic document analyzer extracts:

- process name, product, business unit, systems, and stakeholders
- likely risk categories
- control activity cues
- exposure cues such as volumes, dollar amounts, rates, and frequencies
- obligations such as review, approval, escalation, and reporting requirements
- source document metadata and extracted text preview

This is not treated as final truth. Business users can edit extracted context before running the workflow.

## Running

```bash
streamlit run src/controlnexus/ui/app.py
```

Open `Risk Inventory Builder` and enable `Demo Mode` to inspect the full `Large Global Bank` workspace immediately.

## Testing

```bash
pytest tests/test_risk_inventory.py -v
pytest tests/ -v
ruff check src tests
mypy src/controlnexus --ignore-missing-imports
```
