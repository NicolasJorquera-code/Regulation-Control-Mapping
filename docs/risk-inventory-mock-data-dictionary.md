# Risk Inventory Mock Data Dictionary

This generic demo data pack uses fictional archetypes rather than named institutions. The core entities are business units, processes, controls, risk records, KRIs, evidence artifacts, issues, regulatory obligations, and risk appetite thresholds.

## Core Files

- `workspace.yaml`: Large Global Bank default workspace with all five business units and ten processes.
- `workspace_local_regional_bank.yaml`: smaller regional subset using the same modular source packs.
- `workspace_digital_payments_institution.yaml`: payments and cyber concentrated subset.
- `packs/*.yaml`: reusable source packs for business units, processes, run fixtures, KRIs, evidence, issues, obligations, and appetite.

## Scoring

Impact and likelihood are matrix-calculated into inherent risk. Control design and operating ratings are aggregated conservatively into a control environment rating. Residual risk is then matrix-calculated from inherent risk and control environment.

## Generic Data Rules

No institution names, individual names, tenant names, or branded fictional system names are used. Owners are role labels. Systems are generic platform labels. Regulatory rails and frameworks may appear when they explain the risk context.
