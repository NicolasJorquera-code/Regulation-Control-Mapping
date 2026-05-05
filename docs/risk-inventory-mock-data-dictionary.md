# Risk Inventory Mock Data Dictionary

This reference data pack uses institution-neutral operating structures. The core entities are business units, processes, controls, risk records, KRIs, evidence artifacts, issues, regulatory obligations, and risk appetite thresholds.

## Core Files

- `payment_exception_handling.yaml`: default Demo Mode run fixture for the single-process Payment Exception Handling scenario.
- `workspace.yaml`: broader legacy workspace with all five business units and ten processes, available for explicit loader calls and regression tests.
- `workspace_local_regional_bank.yaml`: smaller regional subset using the same modular source packs.
- `workspace_digital_payments_institution.yaml`: payments and cyber concentrated subset.
- `packs/*.yaml`: reusable source packs for business units, processes, run fixtures, KRIs, evidence, issues, obligations, and appetite.

## Scoring

Impact and likelihood are matrix-calculated into inherent risk. Control design and operating ratings are aggregated conservatively into a control environment rating. Residual risk is then matrix-calculated from inherent risk and control environment.

## Generic Data Rules

Owners are role labels. Systems use enterprise platform labels. Regulatory rails and frameworks may appear when they explain the risk context.
