# Section Control Generation Prompt

> **Purpose**: Self-contained prompt for generating banking controls for a specific APQC process area using an external LLM (ChatGPT, Claude, etc.). Produces output matching the ControlNexus 19-field control record format.
>
> **Usage**: Copy the entire prompt below into an LLM conversation. Replace the `[SECTION DATA]` block with data from any `config/sections/section_*.yaml` file. Adjust `TARGET_COUNT` as needed.

---

## Prompt

```
You are a banking compliance control generation expert. Your task is to generate internal controls for a specific APQC process area within a financial institution's control framework.

You will produce controls that follow a standardized 19-field schema, using the section's risk profile, control type affinity matrix, and domain registry as inputs. Each control must have a realistic 5W narrative (who, what, when, where, why) grounded in the section's domain vocabulary.

────────────────────────────────────────────────────────
TARGET_COUNT: 10
────────────────────────────────────────────────────────

────────────────────────────────────────────────────────
OUTPUT SCHEMA (19 fields per control)
────────────────────────────────────────────────────────

For each control, produce a JSON object with EXACTLY these fields:

| # | Field | Type | Description |
|---|-------|------|-------------|
| 1 | control_id | string | Format: CTRL-{L1:02d}{L2:02d}-{TypeCode}-{Seq:03d}. L1 = section integer part, L2 = section decimal part. TypeCode = 3-letter code from the control type table. Seq = sequential per type starting at 001. Example: CTRL-1200-AUT-001 |
| 2 | hierarchy_id | string | APQC hierarchy path. For section-level generation use "{section_id}.1.1" (e.g., "12.0.1.1") |
| 3 | leaf_name | string | "{Section Name} – {Control Type Name}" |
| 4 | selected_level_1 | string | Same as placement (Preventive / Detective / Contingency Planning) |
| 5 | selected_level_2 | string | Same as control_type |
| 6 | business_unit_id | string | Business unit ID (e.g., "BU-001") |
| 7 | business_unit_name | string | Business unit name (e.g., "Compliance") |
| 8 | who | string | The specific role performing the control — MUST come from the section registry's roles list |
| 9 | what | string | The specific action performed — derived from the control type definition |
| 10 | when | string | The timing or trigger — MUST come from the section registry's event_triggers list |
| 11 | frequency | string | Derived from the "when" field. One of: Daily, Weekly, Monthly, Quarterly, Semi-Annual, Annual, Other |
| 12 | where | string | The system where the control is performed — MUST come from the section registry's systems list |
| 13 | why | string | The risk or objective — reference the section's risk profile rationale and regulatory frameworks |
| 14 | full_description | string | Complete prose narrative (30–80 words) incorporating all 5W fields plus evidence. Format: "{When}, the {who} {what} within the {where} {why}, with results documented via {evidence}." |
| 15 | quality_rating | string | One of: Strong, Effective, Satisfactory, Needs Improvement |
| 16 | validator_passed | boolean | true |
| 17 | validator_retries | integer | 0 |
| 18 | validator_failures | array | [] |
| 19 | evidence | string | Evidence artifact — MUST come from the section registry's evidence_artifacts list |

────────────────────────────────────────────────────────
CONTROL TYPES (25 types with 3-letter codes)
────────────────────────────────────────────────────────

| Code | Control Type | Definition | Default Placement |
|------|-------------|------------|-------------------|
| REC | Reconciliation | Comparison of features, transactions, activities, or data to validate accuracy, completeness, or appropriateness. Includes steps for investigating and resolving discrepancies. | Detective |
| AUT | Authorization | Review and validation of documentation or transaction information to determine appropriateness before allowing a process to continue. | Preventive |
| VNV | Verification and Validation | Examining information to validate accuracy, appropriateness, or completeness of information or required actions. | Detective |
| EXR | Exception Reporting | Creation of reports and alerts to identify risk limit breaches, system constraints, ageing items, or outstanding activities. | Detective |
| SOD | Segregation of Duties | Organizing activities so no individual can complete a process alone, limiting manipulation potential. | Preventive |
| DOC | Documentation Checks | Review, approval, and management of data and documentation to validate completeness and accuracy. | Preventive |
| AUD | Internal and External Audits | Testing and review of internal controls to assess effectiveness or regulatory alignment. | Detective |
| ARL | Automated Rules | Pre-defined rules in systems to control or restrict action execution. | Preventive |
| REP | Risk Escalation Processes | Mechanisms for reporting violations, breaches, or misconduct to relevant stakeholders. | Detective |
| TRN | Training and Awareness Programs | Formal knowledge transfer with standardized curriculum, tracked attendance, and escalation protocols. | Preventive |
| SAR | System and Application Restrictions | Access management for devices, portals, and networks based on credentials and user privileges. | Preventive |
| DSP | Data Security and Protection | Securely storing and safeguarding data to prevent unauthorized access using encryption and firewalls. | Preventive |
| CDM | Client Due Diligence and Transaction Monitoring | Validation of client identity during onboarding and monitoring transactions for suspicious activity. | Preventive |
| SRV | Surveillance | Real-time monitoring of behaviors, activities, or data signals subject to ongoing change. | Detective |
| PHY | Physical Safeguards | Physical tools and infrastructure to protect buildings, property, equipment, or documents. | Preventive |
| BCP | Business Continuity Planning | Business protocols for outage/crisis events including critical function identification. | Contingency Planning |
| CRS | Crisis Management | Activation of contingency plans and communication strategies during active crises. | Contingency Planning |
| TDR | Technology Disaster Recovery | Technology recovery plans to sustain business during crisis and restore key systems. | Contingency Planning |
| SRA | Staffing and Resourcing Adequacy | Staffing and skills assessments to determine required operational capacity. | Preventive |
| ICM | Internal Compliance Monitoring | Monitoring release of material non-public information and trading activity for prohibited transactions. | Preventive |
| TMP | Talent Management Practices | Managing staff alignment with business objectives including background checks and registrations. | Preventive |
| RCA | Risk and Compliance Assessments | Enterprise-wide assessments to identify inherent risks, measure control effectiveness, and determine residual risk. | Preventive |
| RLS | Risk Limit Setting | Setting risk limits and tolerance thresholds with alert systems for limit breaches. | Preventive |
| SCM | System Change Management | Software testing to validate newly implemented or updated systems and infrastructure effects. | Preventive |
| THR | Third Party Due Diligence | Due diligence on third-party vendors to understand risk exposures and control environment strength. | Preventive |

────────────────────────────────────────────────────────
FREQUENCY DERIVATION RULES
────────────────────────────────────────────────────────

Derive the "frequency" field from the "when" (event trigger) text:
- If trigger contains "daily", "every day", "eod" → "Daily"
- If trigger contains "weekly", "every week" → "Weekly"
- If trigger contains "monthly", "every month", "month-end" → "Monthly"
- If trigger contains "quarterly", "every quarter" → "Quarterly"
- If trigger contains "semi-annual", "twice a year" → "Semi-Annual"
- If trigger contains "annual", "annually", "yearly" → "Annual"
- If no keyword matches → "Other"

────────────────────────────────────────────────────────
GENERATION RULES
────────────────────────────────────────────────────────

1. **Affinity-driven type selection**: Prioritize control types from the section's HIGH affinity list. Include MEDIUM types for variety. Rarely include LOW types. NEVER include NONE types.

2. **Registry grounding**: Every "who" MUST be a role from the registry. Every "where" MUST be a system from the registry. Every "when" MUST be an event trigger from the registry. Every "evidence" MUST be an evidence artifact from the registry.

3. **Placement from type**: Use the control type's default placement category (see table above). If a type has multiple placements, choose the one most appropriate for the section's risk profile.

4. **Method selection**: Preventive controls default to "Automated" unless the registry suggests manual processes. Detective controls default to "Manual". Contingency Planning controls default to "Manual".

5. **Narrative quality**: The full_description must be 30–80 words, flow naturally as prose, and incorporate all 5W fields. Stronger controls have more specific language and explicit regulatory references.

6. **Quality rating distribution**: Aim for ~20% Strong, ~50% Effective, ~25% Satisfactory, ~5% Needs Improvement. Strong ratings require specific regulatory framework references and detailed evidence.

7. **Business unit assignment**: Cycle through relevant business units. For compliance-heavy sections, prefer Compliance (BU-009), Legal (BU-010), and Risk Management (BU-011). Adjust based on section domain.

8. **Control ID sequencing**: Within a type, sequence starts at 001 and increments. L1 and L2 derive from the section_id (e.g., section "12.0" → L1=12, L2=00, so prefix is CTRL-1200).

9. **Regulatory framework references**: Use the section's regulatory_frameworks list in "why" fields to ground controls in actual regulations.

10. **Exemplar alignment**: If the section includes exemplar controls, use them as style and quality references — match their narrative tone, specificity level, and structure.

────────────────────────────────────────────────────────
VALIDATION CRITERIA
────────────────────────────────────────────────────────

Each generated control must pass these checks:
- full_description word count is between 30 and 80 words
- who, what, when, where, why fields are all non-empty
- who matches a role from the section registry
- where matches a system from the section registry
- frequency is one of the valid tier labels
- quality_rating is one of: Strong, Effective, Satisfactory, Needs Improvement

────────────────────────────────────────────────────────
[SECTION DATA] — Replace this block with your target section
────────────────────────────────────────────────────────

Section ID: 12.0
Section Name: External Relationship Management
Domain: external_relationship_management

Risk Profile:
  Inherent Risk: 3/5
  Regulatory Intensity: 4/5
  Control Density: 3/5
  Multiplier: 2.2
  Rationale: Management of external relationships with regulators, government entities, industry bodies, and counterparties carries risk related to regulatory standing, information disclosure, and reputational exposure. Ineffective external relationship management can result in supervisory criticism and loss of regulatory confidence.

Affinity Matrix:
  HIGH:
    - Documentation, Data, and Activity Completeness and Appropriateness Checks
    - Authorization
    - Verification and Validation
    - Risk Escalation Processes
  MEDIUM:
    - Third Party Due Diligence
    - Internal Compliance Monitoring
    - Risk and Compliance Assessments
    - Training and Awareness Programs
  LOW:
    - Segregation of Duties
    - Exception Reporting
    - Internal and External Audits
    - Automated Rules
  NONE:
    - Reconciliation
    - Client Due Diligence and Transaction Monitoring
    - Surveillance
    - Physical Safeguards
    - Business Continuity Planning and Awareness
    - Crisis Management
    - Technology Disaster Recovery
    - Staffing and Resourcing Adequacy
    - Talent Management Practices
    - Risk Limit Setting
    - System and Application Restrictions
    - Data Security and Protection
    - System Change Management

Registry:
  Roles:
    - Regulatory Relations Manager
    - Government Affairs Manager
    - External Affairs Director
    - Regulatory Examination Coordinator
    - Industry Association Liaison
    - Community Relations Manager
    - Head of Regulatory Affairs
    - Corporate Communications Manager
  Systems:
    - Regulatory Examination Management System
    - Regulatory Filing and Submission Platform
    - Government Affairs Tracking System
    - External Communications Approval Workflow Tool
    - Stakeholder Relationship Management Platform
  Data Objects:
    - regulatory examination schedules and correspondence
    - regulatory filing submissions and confirmations
    - government affairs activity logs
    - external communication drafts and approvals
    - industry association membership and participation records
    - community reinvestment activity documentation
  Evidence Artifacts:
    - regulatory examination response package with executive sign-off
    - regulatory filing submission confirmation with completeness checklist
    - external communication approval log with legal and compliance review
    - government affairs activity report with disclosure compliance
    - community reinvestment reporting documentation
  Event Triggers:
    - on receipt of regulatory examination notification or information request
    - at each regulatory filing submission deadline
    - on scheduling of regulator meeting or examination entrance conference
    - at each annual Community Reinvestment Act reporting cycle
    - on material external communication requiring legal and compliance review
    - on engagement with new external counterparty or industry body
  Regulatory Frameworks:
    - OCC Examination Process Requirements
    - Federal Reserve Supervisory Process
    - SEC Disclosure Requirements
    - Community Reinvestment Act
    - Lobbying Disclosure Act
    - FOIA and Public Records Requirements

Exemplar (reference for narrative style and quality):
  Control Type: Authorization
  Placement: Preventive
  Method: Manual
  Full Description: "Prior to submission, the Regulatory Relations Manager reviews all regulatory examination response packages for completeness and accuracy, and obtains formal sign-off from the relevant business line executive, Chief Risk Officer, and General Counsel before transmitting the response to the examining regulatory agency, ensuring all commitments and representations are authorized at the appropriate governance level."
  Word Count: 51
  Quality Rating: Strong

────────────────────────────────────────────────────────
OUTPUT FORMAT
────────────────────────────────────────────────────────

Return a JSON array of exactly TARGET_COUNT control objects, each with all 19 fields.

Example output for 1 control:

[
  {
    "control_id": "CTRL-1200-AUT-001",
    "hierarchy_id": "12.0.1.1",
    "leaf_name": "External Relationship Management – Authorization",
    "selected_level_1": "Preventive",
    "selected_level_2": "Authorization",
    "business_unit_id": "BU-009",
    "business_unit_name": "Compliance",
    "who": "Regulatory Relations Manager",
    "what": "reviews and authorizes all regulatory examination response packages for completeness and accuracy",
    "when": "on receipt of regulatory examination notification or information request",
    "frequency": "Other",
    "where": "Regulatory Examination Management System",
    "why": "to ensure all commitments and representations are authorized at appropriate governance levels per OCC Examination Process Requirements",
    "full_description": "On receipt of regulatory examination notification or information request, the Regulatory Relations Manager reviews and authorizes all regulatory examination response packages for completeness and accuracy within the Regulatory Examination Management System to ensure all commitments and representations are authorized at appropriate governance levels per OCC Examination Process Requirements, with results documented via regulatory examination response package with executive sign-off.",
    "quality_rating": "Strong",
    "validator_passed": true,
    "validator_retries": 0,
    "validator_failures": [],
    "evidence": "regulatory examination response package with executive sign-off"
  }
]

Now generate TARGET_COUNT controls for the section described above. Ensure diversity across control types (prioritizing HIGH affinity types), roles, systems, and event triggers. Each control should be unique and realistic.
```

---

## How to Use for Other Sections

1. Open any `config/sections/section_*.yaml` file
2. Replace the `[SECTION DATA]` block in the prompt with the data from that file
3. Adjust `TARGET_COUNT` as needed
4. Paste the entire prompt into ChatGPT, Claude, or another LLM
5. The output JSON can be directly imported into ControlNexus or converted to CSV/Excel

### Section Files Available

| File | Section ID | Domain |
|------|-----------|--------|
| section_1.yaml | 1.0 | Vision and Strategy |
| section_2.yaml | 2.0 | Product Development |
| section_3.yaml | 3.0 | Marketing and Sales |
| section_4.yaml | 4.0 | Sourcing and Procurement |
| section_5.yaml | 5.0 | Banking Operations |
| section_6.yaml | 6.0 | Customer Service |
| section_7.yaml | 7.0 | Human Capital Management |
| section_8.yaml | 8.0 | Information Technology |
| section_9.yaml | 9.0 | Financial Accounting |
| section_10.yaml | 10.0 | Asset Management |
| section_11.yaml | 11.0 | Enterprise Risk and Remediation |
| section_12.yaml | 12.0 | External Relationship Management |
| section_13.yaml | 13.0 | Business Capability Development |

### Control ID Format Reference

For section `X.Y`:
- L1 = X (zero-padded to 2 digits)
- L2 = Y (zero-padded to 2 digits, typically "00" for `.0` sections)
- TypeCode = 3-letter code from the control types table
- Seq = sequential number per type, zero-padded to 3 digits

Examples:
- Section 1.0, Reconciliation, 1st → `CTRL-0100-REC-001`
- Section 5.0, Authorization, 3rd → `CTRL-0500-AUT-003`
- Section 12.0, Documentation, 2nd → `CTRL-1200-DOC-002`
