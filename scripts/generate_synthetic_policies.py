"""
Generate a synthetic Policy / Procedure workbook for demo & testing.

Produces ``data/policy_source_inventory.xlsx`` with a ``Source_Inventory``
sheet containing realistic policy and procedure rows for a fictional
financial institution. Run once::

    python scripts/generate_synthetic_policies.py

The output can be loaded directly by the Streamlit UI when the hybrid
source-type feature is active.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _PROJECT_ROOT / "data" / "policy_source_inventory.xlsx"

# Seed for reproducibility
random.seed(42)

# ── Controlled vocabularies ───────────────────────────────────────────────

_POLICY_OWNERS = [
    "Chief Credit Officer",
    "Chief Operational Risk Officer",
    "Chief Compliance Officer",
    "MLRO",
    "Head of Cybersecurity",
    "Treasurer",
    "Chief Data Officer",
]

_BUSINESS_UNITS = [
    "Wholesale Banking",
    "Consumer Banking",
    "Wealth Management",
    "Markets",
    "Treasury",
    "Operations",
    "Technology",
    "Compliance",
    "Risk",
]

_LEGAL_ENTITIES = [
    "BAC NA",
    "BAC Europe SA",
    "BAC Securities LLC",
    "BAC Asia Pte Ltd",
]

_JURISDICTIONS = [
    "US-Federal",
    "US-State-NY",
    "EU",
    "UK",
    "APAC-SG",
]

_APPROVAL_BODIES = [
    "Board Risk Committee",
    "Operating Risk Committee",
    "Compliance Committee",
    "Technology Risk Committee",
]

_EXCEPTION_PROCESSES = [
    "Standard EAA",
    "Risk-Accepted by ORC",
    "Time-Limited Waiver",
    "No Exception Allowed",
]

_CONTROL_FREQUENCIES = [
    "Continuous",
    "Daily",
    "Weekly",
    "Monthly",
    "Quarterly",
    "Annual",
    "Event-Driven",
]

# ── Realistic policy / procedure templates ────────────────────────────────

_POLICIES: list[dict] = [
    {
        "id": "POL-CRED-014",
        "title": "Credit Risk Concentration Limits",
        "document": "Enterprise Credit Risk Policy v3.2",
        "section": "§4.2 Concentration Caps",
        "text": "All single-name exposures shall not exceed 10% of Tier 1 capital. Aggregate sector concentrations must remain within board-approved limits.",
        "owner": "Chief Credit Officer",
        "bu": "Wholesale Banking",
        "jurisdiction": "US-Federal",
        "requirement_type": "Threshold",
        "regulation_links": "12 CFR 252.34",
        "risk_theme": "Credit Concentration",
        "procedures": [
            {
                "pid": "PROC-CRED-014.P1",
                "title": "Weekly Exception Review",
                "step": "Compliance pulls concentration exception report from CCRM system weekly. Desk head reviews and signs off on all limit breaches within 2 business days.",
                "evidence": "CCRM Exception Report (CCRM-44)",
            },
            {
                "pid": "PROC-CRED-014.P2",
                "title": "Monthly Board Reporting",
                "step": "Risk Analytics team produces monthly concentration dashboard. Chief Credit Officer presents to Board Risk Committee.",
                "evidence": "Monthly Concentration Dashboard (RiskVu-12)",
            },
        ],
    },
    {
        "id": "POL-AML-022",
        "title": "Enhanced Due Diligence for PEPs",
        "document": "AML/CFT Policy v5.1",
        "section": "§7.3 Politically Exposed Persons",
        "text": "All accounts associated with Politically Exposed Persons (PEPs) must undergo Enhanced Due Diligence (EDD) prior to onboarding and at every periodic review cycle.",
        "owner": "MLRO",
        "bu": "Compliance",
        "jurisdiction": "US-Federal",
        "requirement_type": "Mandate",
        "regulation_links": "31 CFR 1010.620; FATF Recommendation 12",
        "risk_theme": "Money Laundering",
        "procedures": [
            {
                "pid": "PROC-AML-022.P1",
                "title": "PEP Screening at Onboarding",
                "step": "KYC team triggers EDD form in CAMS system upon PEP match. Analyst completes source-of-wealth and source-of-funds sections within 10 business days.",
                "evidence": "EDD Form (CAMS-EDD-01)",
            },
            {
                "pid": "PROC-AML-022.P2",
                "title": "Compliance EDD Review",
                "step": "Compliance reviews EDD packet within 5 business days. Findings documented in case file. Escalation to MLRO if adverse media identified.",
                "evidence": "EDD Case File (CAMS-CASE)",
            },
            {
                "pid": "PROC-AML-022.P3",
                "title": "MLRO Approval",
                "step": "MLRO approves or rejects PEP onboarding before account opening. Decision recorded in CAMS with rationale.",
                "evidence": "MLRO Decision Record (CAMS-DEC)",
            },
        ],
    },
    {
        "id": "POL-OPRES-008",
        "title": "Operational Resilience Recovery Threshold",
        "document": "Operational Resilience Policy v2.0",
        "section": "§3.1 Recovery Objectives",
        "text": "Critical business services must recover within 2 hours of disruption. Non-critical services must recover within 24 hours.",
        "owner": "Chief Operational Risk Officer",
        "bu": "Operations",
        "jurisdiction": "UK",
        "requirement_type": "Threshold",
        "regulation_links": "",
        "risk_theme": "Business Disruption",
        "procedures": [
            {
                "pid": "PROC-OPRES-008.P1",
                "title": "BCP Testing",
                "step": "Business Continuity team conducts quarterly scenario-based recovery tests for all Tier-1 services. Results reported to Operating Risk Committee.",
                "evidence": "BCP Test Report (ServiceNow-BCP)",
            },
        ],
    },
    {
        "id": "POL-CYBER-031",
        "title": "Encryption at Rest and in Transit",
        "document": "Information Security Policy v4.3",
        "section": "§5.2 Data Protection",
        "text": "All customer data must be encrypted at rest using AES-256 and in transit using TLS 1.2 or higher. Key management must follow the Enterprise Key Management Standard.",
        "owner": "Head of Cybersecurity",
        "bu": "Technology",
        "jurisdiction": "US-Federal",
        "requirement_type": "Mandate",
        "regulation_links": "",
        "risk_theme": "Information Security",
        "procedures": [],
    },
    {
        "id": "POL-DATA-005",
        "title": "Data Quality and Lineage",
        "document": "Enterprise Data Governance Policy v2.1",
        "section": "§4.1 Data Quality",
        "text": "All critical data elements must have defined data quality rules, automated monitoring, and documented lineage from source to consumption.",
        "owner": "Chief Data Officer",
        "bu": "Technology",
        "jurisdiction": "US-Federal",
        "requirement_type": "Principle",
        "regulation_links": "BCBS 239",
        "risk_theme": "Data Risk",
        "procedures": [
            {
                "pid": "PROC-DATA-005.P1",
                "title": "Monthly DQ Scorecard",
                "step": "Data Governance team runs automated DQ checks against defined rules. Monthly scorecard published to data owners and Chief Data Officer.",
                "evidence": "DQ Scorecard (Collibra-DQ)",
            },
            {
                "pid": "PROC-DATA-005.P2",
                "title": "Lineage Documentation",
                "step": "Data engineering team maintains lineage maps in Collibra for all Tier-1 datasets. Reviewed semi-annually.",
                "evidence": "Lineage Map (Collibra-LIN)",
            },
        ],
    },
    {
        "id": "POL-MARKETS-019",
        "title": "Pre-Trade and Post-Trade Controls",
        "document": "Markets Conduct Policy v3.0",
        "section": "§6.4 Trade Surveillance",
        "text": "All trades over $50M notional require pre-trade limit check and post-trade review within T+1. Exceptions must be escalated to Head of Markets.",
        "owner": "Chief Compliance Officer",
        "bu": "Markets",
        "jurisdiction": "US-Federal",
        "requirement_type": "Mandate",
        "regulation_links": "",
        "risk_theme": "Market Conduct",
        "procedures": [
            {
                "pid": "PROC-MARKETS-019.P1",
                "title": "Pre-Trade Limit Check",
                "step": "Trading system enforces automated pre-trade limit check. Block triggered when notional exceeds $50M and limit headroom is insufficient.",
                "evidence": "Trade Blotter (Murex-PTL)",
            },
            {
                "pid": "PROC-MARKETS-019.P2",
                "title": "Post-Trade Review",
                "step": "Surveillance team reviews all trades >$50M by T+1 close. Findings logged in Archer with exception flag if review incomplete.",
                "evidence": "Surveillance Log (Archer-SUR)",
            },
        ],
    },
    {
        "id": "POL-FIN-042",
        "title": "Daily Cash Reconciliation",
        "document": "Finance Operations Policy v6.0",
        "section": "§2.1 Cash Management",
        "text": "All nostro and vostro accounts must be reconciled daily by 10:00 AM local time. Cash breaks exceeding $100K must be escalated to Treasury within 1 hour.",
        "owner": "Treasurer",
        "bu": "Treasury",
        "jurisdiction": "US-Federal",
        "requirement_type": "Operational_Step",
        "regulation_links": "",
        "risk_theme": "Liquidity",
        "procedures": [
            {
                "pid": "PROC-FIN-042.P1",
                "title": "Automated Reconciliation Run",
                "step": "Reconciliation engine (Wallstreet Suite) runs overnight batch matching. Unmatched items flagged by 6:00 AM. Operations team investigates breaks before 10:00 AM deadline.",
                "evidence": "Recon Exception Report (WSS-RECON)",
            },
        ],
    },
]


def _build_rows() -> list[dict]:
    rows: list[dict] = []
    for pol in _POLICIES:
        legal_entity = random.choice(_LEGAL_ENTITIES)
        version = f"{random.randint(1, 5)}.{random.randint(0, 9)}"
        rows.append({
            "Source_ID": pol["id"],
            "Source_Type": "Policy_Requirement",
            "Source_Title": pol["title"],
            "Source_Document_Name": pol["document"],
            "Source_Section": pol["section"],
            "Source_Text": pol["text"],
            "Source_Owner": pol["owner"],
            "Business_Unit": pol["bu"],
            "Legal_Entity": legal_entity,
            "Jurisdiction": pol["jurisdiction"],
            "Effective_Date": "2025-01-15",
            "Review_Date": "2026-01-15",
            "Version": version,
            "Parent_Source_ID": "",
            "Procedure_ID": "",
            "Procedure_Title": "",
            "Procedure_Step": "",
            "Requirement_Type": pol["requirement_type"],
            "Requirement_Intent": "",
            "Control_Objective": "",
            "Risk_Theme": pol["risk_theme"],
            "Evidence_Reference": "",
            "Source_Confidence": 0.95,
            "Extraction_Rationale": "Verbatim from policy document.",
            "Regulation_Links": pol.get("regulation_links", ""),
        })
        for proc in pol.get("procedures", []):
            rows.append({
                "Source_ID": proc["pid"],
                "Source_Type": "Procedure_Step",
                "Source_Title": proc["title"],
                "Source_Document_Name": pol["document"],
                "Source_Section": pol["section"],
                "Source_Text": proc["step"],
                "Source_Owner": pol["owner"],
                "Business_Unit": pol["bu"],
                "Legal_Entity": legal_entity,
                "Jurisdiction": pol["jurisdiction"],
                "Effective_Date": "2025-01-15",
                "Review_Date": "2026-01-15",
                "Version": version,
                "Parent_Source_ID": pol["id"],
                "Procedure_ID": proc["pid"],
                "Procedure_Title": proc["title"],
                "Procedure_Step": proc["step"],
                "Requirement_Type": "Operational_Step",
                "Requirement_Intent": "",
                "Control_Objective": "",
                "Risk_Theme": pol["risk_theme"],
                "Evidence_Reference": proc.get("evidence", ""),
                "Source_Confidence": 0.90,
                "Extraction_Rationale": "Extracted from procedure manual.",
                "Regulation_Links": "",
            })
    return rows


def main() -> None:
    rows = _build_rows()
    df = pd.DataFrame(rows)
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(_OUTPUT), engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Source_Inventory", index=False)
    print(f"Generated {len(rows)} rows → {_OUTPUT}")
    print(f"  Policies:   {sum(1 for r in rows if r['Source_Type'] == 'Policy_Requirement')}")
    print(f"  Procedures: {sum(1 for r in rows if r['Source_Type'] == 'Procedure_Step')}")


if __name__ == "__main__":
    main()
