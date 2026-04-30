# Risk Inventory Builder

Risk Inventory Builder extends ControlNexus from control generation and gap analysis into a broader risk inventory and risk-to-control assessment platform.

The core product question is:

```text
Given a process, product, business context, taxonomy, and available control data,
what risks should exist in the risk inventory, how should they be described,
how material are they, what controls address them, and what residual exposure remains?
```

## Architecture

The capability is additive and reuses the existing ControlNexus architecture:

- `DomainConfig`, `RiskCatalogEntry`, `MitigationLink`, and control type metadata remain the control/risk configuration backbone.
- `src/controlnexus/risk_inventory/` contains the risk inventory object graph, calculators, validators, graph, demo loader, and Excel export.
- LangGraph orchestration follows the existing deterministic fallback style.
- Streamlit renders a first-class `Risk Inventory Builder` tab ahead of existing ControlNexus tabs.

The Pydantic `RiskInventoryRun` object is the system of record. Excel is an export/reporting layer.

```text
Process Context
-> Taxonomy Applicability
-> Risk Statement
-> Exposure Metrics
-> Impact + Likelihood
-> Inherent Risk Matrix
-> Control Mapping
-> Design / Operating Effectiveness
-> Control Environment
-> Residual Risk Matrix
-> Review & Challenge
-> Executive Report / Excel Export
```

## Deterministic Scoring

Scoring matrices are config-driven under `config/risk_inventory/`:

- `impact_scales.yaml`
- `likelihood_scale.yaml`
- `inherent_risk_matrix.yaml`
- `control_effectiveness_criteria.yaml`
- `residual_risk_matrix.yaml`
- `management_response_rules.yaml`

LLM agents may recommend rationale, mappings, and narrative text, but inherent and residual ratings are calculated by deterministic Python services.

## Demo Mode

The frontend includes a `Demo Mode` toggle in the Risk Inventory Builder tab.

When enabled, it loads deterministic Payment Exception Handling sample data from:

```text
sample_data/risk_inventory_demo/payment_exception_handling.yaml
```

The demo includes process context, systems, stakeholders, six realistic risk records, exposure metrics, impact and likelihood scores, inherent risk, mapped controls, control effectiveness, residual risk, review comments, executive summary, validation findings, and Excel export-ready output.

No LLM credentials are required.

## Document Ingestion

The `Input / Upload` tab accepts PDF, TXT, and Markdown policy/procedure files. The document is parsed locally and converted into a reviewable process context before the graph runs.

The deterministic document analyzer extracts:

- process name, product, business unit, systems, and stakeholders
- likely risk categories
- control activity cues
- exposure cues such as volumes, dollar amounts, rates, and frequencies
- obligations such as review, approval, escalation, and reporting requirements
- source document metadata and extracted text preview

This is not treated as final truth. Business users can edit the extracted context before running the workflow.

## Running

```bash
streamlit run src/controlnexus/ui/app.py
```

Open the `Risk Inventory Builder` tab and enable `Demo Mode` to inspect a completed inventory immediately.

## Testing

```bash
pytest tests/test_risk_inventory.py -v
pytest tests/ -v
ruff check src tests
mypy src/controlnexus --ignore-missing-imports
```
