# ASI Prompt: Generate A Rich Bank Executive Mock Data Repository

You are an expert risk-data architect, operational-risk practitioner, bank-control designer, and synthetic-data generator. Your task is to create a repo-ready mock data pack for a fictional U.S. financial-services demo called **Risk Inventory Builder**.

The target audience is senior bank executives: CRO, COO, CISO, Chief Credit Officer, Head of Retail Banking, Treasurer, Internal Audit, and Board Risk Committee observers. The data must feel credible, internally consistent, and high quality enough for an executive presentation. It must remain fictional and must not include real customer data, real institution data, real employee names, or confidential regulatory exam content.

## Attach These Files Before You Start

Attach these repository files to give yourself the implementation contract. If you cannot attach them, read them in the repo before generating output.

- `docs/risk-inventory-demo-frontend-deep-dive.md`
- `docs/RISK_INVENTORY_BUILDER.md`
- `src/controlnexus/risk_inventory/models.py`
- `src/controlnexus/risk_inventory/demo.py`
- `src/controlnexus/ui/risk_inventory_tab.py`
- `config/risk_inventory/risk_taxonomy_crosswalk.yaml`
- `config/risk_inventory/inherent_risk_matrix.yaml`
- `config/risk_inventory/residual_risk_matrix.yaml`
- `config/risk_inventory/management_response_rules.yaml`
- `sample_data/risk_inventory_demo/workspace.yaml`
- `sample_data/risk_inventory_demo/packs/business_units.yaml`
- `sample_data/risk_inventory_demo/packs/processes.yaml`
- `sample_data/risk_inventory_demo/packs/run_fixtures.yaml`
- `sample_data/risk_inventory_demo/packs/regulatory_obligations.yaml`
- `sample_data/risk_inventory_demo/packs/evidence_artifacts.yaml`
- `sample_data/risk_inventory_demo/packs/issues.yaml`
- `sample_data/risk_inventory_demo/packs/risk_appetite_framework.yaml`
- `sample_data/risk_inventory_demo/payment_exception_handling.yaml`
- `sample_data/risk_inventory_demo/customer_onboarding.yaml`
- `sample_data/risk_inventory_demo/commercial_loan_underwriting.yaml`

## Product Context

Risk Inventory Builder converts process evidence into a bank risk inventory. In demo mode it loads deterministic YAML fixtures and renders a Streamlit executive workbench. It does not require LLM credentials.

The main demo tabs are:

- `Knowledge Base`
- `Risk Inventory`
- `Control Mapping`
- `Control Gap Lab`
- `Review & Challenge`
- `Agent Run Trace`
- `Executive Report`

The most important executive view is the portfolio view shown when no process is selected. It aggregates all process runs into a **Business Unit x Enterprise Risk Category heatmap** and an aggregated risk table. The data you create must make the business-unit risk differences obvious in that heatmap.

The current workspace already has five business units and ten processes, but only three full hand-authored process fixtures. Missing process fixtures are currently generated synthetically by code, which makes the demo less realistic. Replace that weakness with a rich, hand-authored mock-data repository.

## Current Bank And Workspace

Use this fictional institution:

- Profile name: `Large Global Bank`
- Profile id: `DEMO-FS-LARGE-GLOBAL`
- Workspace id: `WS-NORTHSTAR-FS`
- Fictional U.S. financial-services institution operating across payments, retail banking, commercial credit, treasury operations, and technology/cyber.
- Demonstration only; not based on or traceable to any real institution.

Keep these five business units:

| Business Unit ID | Business Unit | Process IDs |
| --- | --- | --- |
| `BU-PAYOPS` | Payment Operations | `PROC-PAY-EXCEPTION`, `PROC-PAY-RECON` |
| `BU-RETAIL` | Retail Banking & Onboarding | `PROC-CUST-ONBOARD`, `PROC-RETAIL-DISPUTES` |
| `BU-COMMLEND` | Commercial Lending | `PROC-CL-UNDERWRITE`, `PROC-COVENANT-MONITOR` |
| `BU-TREASURY` | Treasury & Liquidity Operations | `PROC-LIQUIDITY-STRESS`, `PROC-SECURITIES-SETTLE` |
| `BU-TECHCYBER` | Technology & Cyber Operations | `PROC-ACCESS-RECERT`, `PROC-VULN-REMEDIATION` |

Keep these ten process names unless a small wording improvement is needed:

- `Payment Exception Handling`
- `End-of-Day Wire Reconciliation`
- `Retail Customer Onboarding (CIP / KYC)`
- `Retail Deposit Dispute Intake and Resolution`
- `Commercial Loan Underwriting & Risk Rating`
- `Commercial Covenant Monitoring`
- `Liquidity Stress Monitoring and Escalation`
- `Securities Trade Settlement and Collateral Operations`
- `Privileged Access Recertification`
- `Critical Vulnerability Remediation`

## Enterprise Risk Taxonomy

Use only the L2 risk taxonomy node IDs already supported by `config/risk_inventory/risk_taxonomy_crosswalk.yaml`.

Valid L1/L2 categories:

| L2 ID | L1 Category | L2 Category |
| --- | --- | --- |
| `RIB-BPR` | Operational | Business Process Risk |
| `RIB-IFR` | Operational | Internal Fraud Risk |
| `RIB-EFR` | Operational | External Fraud Risk |
| `RIB-ORS` | Operational | Operational Resiliency Risk |
| `RIB-TPR` | Operational | Third Party Risk |
| `RIB-MDL` | Operational | Model Risk |
| `RIB-HCM` | Talent | Human Capital Risk |
| `RIB-PHYAS` | Operational | Physical Assets Risk |
| `RIB-DM` | Operational | Data Management Risk |
| `RIB-IT` | Operational | Information Technology Risk |
| `RIB-PCM` | Operational | Project and Change Management Risk |
| `RIB-PRI` | Cyber | Privacy Risk |
| `RIB-CYB` | Cyber | IT Security / Cybersecurity Risk |
| `RIB-PHYS` | Operational | Physical Security Risk |
| `RIB-CON` | Operational | Contract Risk |
| `RIB-LIT` | Operational | Litigation Risk |
| `RIB-IP` | Operational | Intellectual Property Risk |
| `RIB-EMP` | Talent | Employment Practices Risk |
| `RIB-COM` | Regulatory Compliance | Compliance Risk |
| `RIB-RR` | Operational | Regulatory Reporting Risk |

Important UI terminology: user-facing text should say **Frequency**, not Likelihood, but fixture YAML still uses the field name `likelihood_score`.

## Required Output

Create a complete mock data repository under `sample_data/risk_inventory_demo/` and `sample_data/risk_inventory_demo/packs/`.

Minimum file set:

- Update `sample_data/risk_inventory_demo/workspace.yaml`
- Update `sample_data/risk_inventory_demo/packs/business_units.yaml`
- Update `sample_data/risk_inventory_demo/packs/processes.yaml`
- Update `sample_data/risk_inventory_demo/packs/run_fixtures.yaml`
- Update `sample_data/risk_inventory_demo/packs/regulatory_obligations.yaml`
- Update `sample_data/risk_inventory_demo/packs/evidence_artifacts.yaml`
- Update `sample_data/risk_inventory_demo/packs/issues.yaml`
- Update `sample_data/risk_inventory_demo/packs/risk_appetite_framework.yaml`
- Create `sample_data/risk_inventory_demo/packs/kri_library.yaml`
- Create or update ten process run fixture files, one per process:
  - `sample_data/risk_inventory_demo/payment_exception_handling.yaml`
  - `sample_data/risk_inventory_demo/end_of_day_wire_reconciliation.yaml`
  - `sample_data/risk_inventory_demo/customer_onboarding.yaml`
  - `sample_data/risk_inventory_demo/retail_deposit_disputes.yaml`
  - `sample_data/risk_inventory_demo/commercial_loan_underwriting.yaml`
  - `sample_data/risk_inventory_demo/commercial_covenant_monitoring.yaml`
  - `sample_data/risk_inventory_demo/liquidity_stress_monitoring.yaml`
  - `sample_data/risk_inventory_demo/securities_trade_settlement.yaml`
  - `sample_data/risk_inventory_demo/privileged_access_recertification.yaml`
  - `sample_data/risk_inventory_demo/critical_vulnerability_remediation.yaml`
- Add a short data dictionary at `docs/risk-inventory-mock-data-dictionary.md`
- Add an executive scenario guide at `docs/risk-inventory-demo-executive-scenarios.md`

Update `workspace.yaml` so `knowledge_pack.files` includes the new `kri_library` sidecar:

```yaml
knowledge_pack:
  files:
    business_units: "packs/business_units.yaml"
    processes: "packs/processes.yaml"
    run_fixtures: "packs/run_fixtures.yaml"
    regulatory_obligations: "packs/regulatory_obligations.yaml"
    evidence_artifacts: "packs/evidence_artifacts.yaml"
    issues: "packs/issues.yaml"
    risk_appetite_framework: "packs/risk_appetite_framework.yaml"
    kri_library: "packs/kri_library.yaml"
```

Every process in `processes.yaml` must have a corresponding entry in `packs/run_fixtures.yaml`. The demo should no longer depend on auto-generated synthetic process runs. It is acceptable to set `auto_generate_missing_runs: false` once all ten fixtures exist.

## Quantity Targets

Create enough data to feel like a true executive-grade risk repository, not a thin UI mock.

Hard minimums:

- Business units: exactly 5
- Processes: exactly 10
- Full run fixtures: exactly 10
- Risk records: 70 to 78 total
- Risk records per process: 6 to 8
- Controls per process fixture: 7 to 10
- Distinct controls across the repository: 75 to 95
- Exposure metrics per risk: 4 to 6
- Risk evidence references per risk: 2 to 4
- Evidence artifacts in `packs/evidence_artifacts.yaml`: 80 to 110
- Open issues in `packs/issues.yaml`: 32 to 45
- Regulatory obligations in `packs/regulatory_obligations.yaml`: 28 to 40
- KRIs in `packs/kri_library.yaml`: 45 to 60
- Action-plan items per risk: 1 to 3
- Review/challenge record per risk: exactly 1
- At least 20 controls must have an open issue.
- At least 30 controls must have `Improvement Needed` for either design or operating effectiveness.
- At least 15 controls must be `Strong` design and `Strong` operating, so the demo does not look artificially negative.

Do not make every process have the same number of risks or controls. Unevenness is part of realism.

## Make The Business Unit Risk Breakdown Obvious

The front end heatmap aggregates by `Business Unit` and L1 `Enterprise Risk Category`. Make the risk mix visibly different by business unit. Use these target distributions and signatures:

| Business Unit | Total Risks | Primary Heatmap Signature | High+ Residual Pattern |
| --- | ---: | --- | --- |
| Payment Operations | 14-16 | Operational-heavy: Business Process, Data Management, Resiliency, Third Party | 3-5 high+ residual, concentrated in Operational and Cyber access |
| Retail Banking & Onboarding | 14-16 | Regulatory Compliance + Cyber/Privacy + External Fraud | 4-6 high+ residual, concentrated in Compliance, Privacy, and External Fraud |
| Commercial Lending | 12-15 | Operational Model/Data/Contract + Regulatory Compliance | 2-4 high+ residual, concentrated in Model Risk and Covenant/Compliance process gaps |
| Treasury & Liquidity Operations | 14-16 | Operational Resiliency + Data Management + Third Party + Regulatory Reporting | 3-5 high+ residual, concentrated in Resiliency, Data, and Regulatory Reporting |
| Technology & Cyber Operations | 14-16 | Cyber + Information Technology + Change Management | 5-7 high+ residual, concentrated in Cyber and IT/Change |

Across the entire portfolio:

- Use all four L1 categories: Operational, Cyber, Regulatory Compliance, Talent.
- Operational should be the largest portfolio category, but not so dominant that the other columns disappear.
- Cyber should visibly spike for Technology & Cyber Operations and Retail Banking & Onboarding.
- Regulatory Compliance should visibly spike for Retail Banking & Onboarding and Treasury & Liquidity Operations.
- Talent should appear selectively as capacity/training risk, not as a generic filler category.
- Include 1 to 2 Critical residual risks total across the portfolio. More than that will feel melodramatic.
- Include 22 to 30 High residual risks total.
- Include enough Low/Medium residual risks to show the control environment works in places.

The `risk_profile_summary` for each business unit must explicitly preview its heatmap signature using executive language and numbers. Example style:

```yaml
risk_profile_summary: "Operational concentration with 15 material risks across payments; high residual exposure is concentrated in exception aging, data reconciliation, and privileged queue access."
```

## Process-Level Risk Mix

Use this process-level target mix. The exact taxonomy IDs may vary if the rationale is strong, but stay close enough that the executive heatmap tells a clear story.

| Process | Target Risk Count | Required L2 Nodes |
| --- | ---: | --- |
| Payment Exception Handling | 7-8 | `RIB-BPR`, `RIB-DM`, `RIB-CYB`, `RIB-ORS`, `RIB-TPR`, `RIB-RR`, optional `RIB-IFR` |
| End-of-Day Wire Reconciliation | 7-8 | `RIB-DM`, `RIB-BPR`, `RIB-IFR`, `RIB-RR`, `RIB-IT`, `RIB-TPR`, optional `RIB-ORS` |
| Retail Customer Onboarding (CIP / KYC) | 7-8 | `RIB-COM`, `RIB-EFR`, `RIB-PRI`, `RIB-CYB`, `RIB-DM`, `RIB-BPR`, optional `RIB-HCM` |
| Retail Deposit Dispute Intake and Resolution | 7-8 | `RIB-COM`, `RIB-BPR`, `RIB-LIT`, `RIB-RR`, `RIB-DM`, `RIB-TPR`, optional `RIB-EMP` |
| Commercial Loan Underwriting & Risk Rating | 6-7 | `RIB-MDL`, `RIB-BPR`, `RIB-CON`, `RIB-DM`, `RIB-COM`, optional `RIB-IFR` |
| Commercial Covenant Monitoring | 6-8 | `RIB-BPR`, `RIB-DM`, `RIB-COM`, `RIB-RR`, `RIB-CON`, optional `RIB-HCM` |
| Liquidity Stress Monitoring and Escalation | 7-8 | `RIB-ORS`, `RIB-DM`, `RIB-RR`, `RIB-BPR`, `RIB-TPR`, `RIB-IT`, optional `RIB-HCM` |
| Securities Trade Settlement and Collateral Operations | 7-8 | `RIB-BPR`, `RIB-DM`, `RIB-TPR`, `RIB-IT`, `RIB-RR`, `RIB-ORS`, optional `RIB-IFR` |
| Privileged Access Recertification | 7-8 | `RIB-CYB`, `RIB-IT`, `RIB-PCM`, `RIB-DM`, `RIB-RR`, optional `RIB-HCM` |
| Critical Vulnerability Remediation | 7-8 | `RIB-CYB`, `RIB-IT`, `RIB-PCM`, `RIB-TPR`, `RIB-ORS`, `RIB-RR`, optional `RIB-HCM` |

## YAML Fixture Contract

Each process fixture must follow this shape because `load_demo_risk_inventory()` reads these fields:

```yaml
version: "1.2.0"
risk_appetite_framework:
  statement: "..."
  effective_date: "2026-01-01"
  approver: "Board Risk Committee"
  category_thresholds:
    operational: "Medium"
    cyber: "Low"
    compliance: "Low"
    talent: "Medium"
  escalation_rules:
    - "..."
scenario:
  run_id: "DEMO-RI-<PROCESS>-001"
  tenant_id: "generic-demo"
  process_id: "PROC-..."
  process_name: "..."
  product: "..."
  business_unit: "..."
  description: "..."
  systems:
    - "..."
  stakeholders:
    - "..."
controls:
  - control_id: "CTRL-..."
    control_name: "..."
    control_type: "..."
    owner: "..."
    frequency: "Daily | Weekly | Monthly | Quarterly | Per transaction | Event-driven"
    description: "..."
    design_rating: "Strong | Satisfactory | Improvement Needed | Inadequate"
    operating_rating: "Strong | Satisfactory | Improvement Needed | Inadequate"
    design_rationale: "..."
    operating_rationale: "..."
    design_criteria_results:
      mapped_to_root_cause: true
      formalized: true
      sufficient_frequency: true
      preventive_or_detective_fit: true
    operating_criteria_results:
      operated_consistently: true
      evidence_available: true
      management_review: true
    risk_mitigations:
      RIB-BPR: "..."
    coverage_by_risk:
      RIB-BPR: "strong | partial | weak"
    mapped_root_causes_per_risk:
      RIB-BPR:
        - "..."
    open_issues:
      - issue_id: "IS-..."
        description: "..."
        severity: "Low | Medium | High | Critical"
        age_days: 0
        owner: "..."
        status: "Open | In Remediation | Closed"
    evidence_quality:
      rating: "Strong | Adequate | Limited | Needs Refresh"
      last_tested: "2026-03-31"
      sample_size: 40
      exceptions_noted: 2
      notes: "..."
risks:
  - taxonomy_node_id: "RIB-..."
    risk_id: "RI-..."
    risk_description: "..."
    risk_event: "..."
    applicability_rationale: "..."
    confidence: 0.86
    causes:
      - "..."
    consequences:
      - "..."
    affected_stakeholders:
      - "..."
    impact_scores:
      financial_impact: 3
      regulatory_impact: 2
      reputational_impact: 3
    impact_rationales:
      financial_impact: "..."
      regulatory_impact: "..."
      reputational_impact: "..."
    overall_impact_score: 3
    overall_impact_rationale: "..."
    likelihood_score: 3
    likelihood_rating: "Medium High"
    likelihood_rationale: "Use the word frequency in prose where user-facing."
    assumptions:
      - "..."
    mapped_controls:
      - "CTRL-..."
    exposure_metrics:
      - metric_name: "..."
        metric_value: "..."
        metric_unit: "..."
        description: "..."
        source: "..."
        supports: ["impact", "likelihood"]
    evidence_references:
      - evidence_id: "EVID-..."
        evidence_type: "..."
        description: "..."
        source: "sample_data/risk_inventory_demo/<fixture>.yaml"
    risk_appetite:
      threshold: "Low | Medium | High"
      statement: "..."
      status: "within | at_threshold | outside"
      category: "..."
    recommended_action: "..."
    action_plan:
      - action: "..."
        owner: "..."
        due_date: "2026-06-30"
        status: "Planned | In Progress | Complete"
        priority: "Low | Medium | High"
    coverage_gaps:
      - "..."
    review:
      review_status: "Pending Review | Challenged | Approved"
      reviewer: "..."
      challenge_comments: "..."
      challenged_fields: ["impact_scores", "control_mapping", "residual_risk"]
      ai_original_value: "..."
      reviewer_adjusted_value: "..."
      reviewer_rationale: "..."
      approval_status: "Draft | Approved | Rejected"
executive_summary:
  headline: "..."
  key_messages:
    - "..."
  top_residual_risks:
    - "..."
  recommended_actions:
    - "..."
```

## Scoring Rules

Use scores that produce internally coherent inherent and residual risk under the configured matrices.

Impact and frequency scores:

- `1`: minimal / low
- `2`: meaningful / medium-low
- `3`: significant / medium-high
- `4`: severe / high

Ratings are matrix-calculated by the app, but your fixture scores and control effectiveness should be intentionally chosen to produce the desired portfolio distribution.

Rules of thumb:

- `overall_impact_score: 4` and `likelihood_score: 3` creates `Critical-12` inherent risk.
- Strong controls can bring even severe inherent risk down to Low/Medium residual.
- Improvement Needed controls should leave meaningful High residual exposure.
- Inadequate control environment should be rare and reserved for the 1 to 2 Critical residual cases.
- Avoid impossible narratives, such as a Low residual risk with multiple unresolved critical control failures unless a strong compensating control is clearly described.

## Realism Requirements

Each process fixture must include:

- Process-specific volumes and exposure metrics, not generic placeholder metrics.
- Named source systems that match the process metadata.
- Evidence quality with sample sizes, exceptions noted, and last-tested dates.
- Open issues with plausible ages, owners, status, and severity.
- Specific control design and operating rationales.
- Root causes that map to People, Process, Technology, and External patterns.
- Regulatory or policy hooks when relevant, without overclaiming legal advice.
- Executive summary that explains why the process matters and what action executives should take.

Use realistic 2026-ish values. Examples:

- Payment exception volumes, aged exception counts, SLA breach rates, high-value dollar exposure.
- Wire reconciliation break counts, unmatched item aging, GL variance dollars.
- CIP exception aging, OFAC potential match disposition timing, CDD completeness rates.
- Dispute aging, provisional credit deadline adherence, customer notice completion.
- Credit rating override counts, model drift indicators, covenant package aging.
- Liquidity trigger breaches, contingency funding action completion, data-feed timeliness.
- Settlement fails, collateral margin call timing, custodian SLA misses.
- Privileged-access exception aging, break-glass recertification delays, stale entitlement counts.
- Critical vulnerability SLA breaches, exploitability scores, exception approval aging.

## KRI Library Requirements

Create `packs/kri_library.yaml` with 45 to 60 KRIs. Each KRI must map to one `risk_taxonomy_id`.

KRI schema:

```yaml
kri_library:
  - kri_id: "KRI-..."
    kri_name: "..."
    risk_taxonomy_id: "RIB-..."
    metric_definition: "..."
    formula: "..."
    unit: "..."
    measurement_frequency: "Daily | Weekly | Monthly | Quarterly"
    data_source: "..."
    owner: "..."
    thresholds:
      green: "..."
      amber: "..."
      red: "..."
    rationale: "..."
    escalation_path: "..."
    use_cases:
      - "..."
    placement_guidance: "..."
```

Coverage requirements:

- At least 3 KRIs for each business unit.
- At least 2 KRIs for each of these taxonomy IDs: `RIB-BPR`, `RIB-DM`, `RIB-CYB`, `RIB-COM`, `RIB-ORS`, `RIB-TPR`, `RIB-IT`, `RIB-RR`, `RIB-MDL`, `RIB-EFR`, `RIB-PRI`.
- Thresholds must include actual numeric bands or explicit conditions.
- Placement guidance must explain where executives should see the KRI, such as ORC dashboard, CISO scorecard, Board Risk Committee pack, or BU risk appetite statement.

## Evidence, Issues, And Obligations

`packs/evidence_artifacts.yaml` must have 80 to 110 artifacts. Include coverage across all processes and control families. Evidence should include:

- workflow extracts
- reconciliation packages
- approval logs
- QA samples
- committee minutes
- access review extracts
- issue management records
- vendor SLA reports
- SOC or assurance summaries
- model monitoring reports
- business continuity exercise reports
- dashboard snapshots

`packs/issues.yaml` must have 32 to 45 issues. Include:

- mix of Open, In Remediation, Closed
- mix of Low, Medium, High, and no more than 2 Critical
- process-linked issues and control-linked issues
- realistic ages from 7 to 120 days
- a few aged executive-visible items

`packs/regulatory_obligations.yaml` must have 28 to 40 obligations. Include:

- BSA/AML, OFAC, CIP/CDD
- Regulation E dispute timing
- UCC Article 4A / wire transfer expectations
- GLBA privacy/data protection
- FFIEC IT and cyber governance expectations
- Third-party risk management expectations
- liquidity risk management governance
- model risk management guidance
- internal policy obligations where external regulation is not the right framing

Use citations at a high level. Do not invent exact paragraph numbers unless they are already provided in attached repo files.

## Control Design Requirements

Use executive-friendly control types already present in the repo examples. Suitable examples include:

- Authorization
- Exception Reporting
- Reconciliation
- Automated Rules
- Surveillance
- Directive
- Risk and Compliance Assessments
- System and Application Restrictions
- Data Security and Protection
- Segregation of Duties
- Verification and Validation
- System Change Management
- Business Continuity Planning and Awareness
- Technology Disaster Recovery
- Third Party Due Diligence
- Documentation, Data, and Activity Completeness and Appropriateness Checks
- Risk Escalation Processes

For every risk:

- Map 1 to 4 controls.
- At least one mapped control should directly address a listed root cause.
- If residual risk is High or Critical, include either a coverage gap, an open issue, an action plan, or an Improvement Needed control rating.
- If residual risk is Low, show why controls are strong enough.

## Narrative Quality Bar

Write like a senior bank risk officer preparing data for an executive committee:

- Specific, concrete, concise.
- No marketing language.
- No generic AI filler.
- No identical phrasing repeated across fixtures.
- Every metric should have a source and a business implication.
- Every High/Critical item needs a management action.
- Every action needs an owner and due date.
- Executive summaries should call out concentration, trend, and decision needed.

Bad:

```text
The process may fail due to weak controls causing risk.
```

Good:

```text
Unmatched wire activity may remain open past the daily close because reconciliation ownership is split between Wire Operations and Treasury Operations, creating misstated cash-position data and late escalation of customer-impacting breaks.
```

## Front-End Visibility Recommendations

Also provide `docs/risk-inventory-demo-executive-scenarios.md` with:

- A one-page executive walkthrough.
- Five business-unit-specific demo narratives.
- Expected portfolio heatmap takeaways.
- The top 10 residual risks executives should notice.
- A note explaining how the richer data makes Business Unit risk breakdown more obvious.

Include a compact table like:

| Business Unit | What executives should notice | Suggested presenter line |
| --- | --- | --- |
| Payment Operations | Operational concentration and queue/access pressure | "Payments is not broadly risky; it has a concentrated execution-and-access exposure profile." |

## Consistency Checks Before Final Answer

Before you finish, run or reason through these checks:

- All files are valid YAML or Markdown.
- Every process in `packs/processes.yaml` has exactly one run fixture in `packs/run_fixtures.yaml`.
- Every run fixture `scenario.process_id` matches a process ID.
- Every `taxonomy_node_id` is in the valid taxonomy list.
- Every `mapped_controls` ID exists in that fixture's `controls`.
- Every KRI `risk_taxonomy_id` is valid.
- Every evidence artifact `process_id`, issue `process_id`, and obligation `process_ids` value is valid.
- No real PII, real customer names, real bank names, or real confidential exam findings.
- Business-unit risk distributions meet the heatmap targets above.
- Residual-risk concentration is varied enough to be visually obvious in the front end.
- Existing deterministic loader can ingest the files without code changes.

## Final Response Format

Return:

1. A concise summary of files created or changed.
2. A portfolio-level count table:

| Item | Count |
| --- | ---: |
| Business Units | 5 |
| Processes | 10 |
| Run Fixtures | 10 |
| Risk Records | ... |
| Controls | ... |
| KRIs | ... |
| Evidence Artifacts | ... |
| Issues | ... |
| Regulatory Obligations | ... |

3. A business-unit risk distribution table:

| Business Unit | Risk Records | Operational | Cyber | Regulatory Compliance | Talent | High+ Residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

4. Any assumptions or intentional design choices.
5. Validation notes, including any checks you could not run.
