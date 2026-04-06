"""
Shared test fixtures.

All fixtures provide deterministic data — no LLM or network calls required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from regrisk.agents.base import AgentContext
from regrisk.core.config import PipelineConfig, load_config, default_config_path, default_taxonomy_path, load_risk_taxonomy
from regrisk.core.models import (
    APQCNode,
    ControlRecord,
    Obligation,
    ObligationGroup,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = _PROJECT_ROOT / "data"
_CONFIG_DIR = _PROJECT_ROOT / "config"


@pytest.fixture
def project_root() -> Path:
    return _PROJECT_ROOT


@pytest.fixture
def data_dir() -> Path:
    return _DATA_DIR


# ---------------------------------------------------------------------------
# Configuration fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config() -> PipelineConfig:
    """PipelineConfig loaded from config/default.yaml."""
    return load_config(str(default_config_path()))


@pytest.fixture
def sample_risk_taxonomy() -> dict:
    """Risk taxonomy loaded from config/risk_taxonomy.json."""
    return load_risk_taxonomy(str(default_taxonomy_path()))


# ---------------------------------------------------------------------------
# Agent context (no LLM)
# ---------------------------------------------------------------------------

@pytest.fixture
def no_llm_context() -> AgentContext:
    """AgentContext with no client — deterministic mode."""
    return AgentContext(client=None)


# ---------------------------------------------------------------------------
# Sample domain objects
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_obligations() -> list[Obligation]:
    """13 Obligation objects simulating 12 CFR 252.22 (risk committee requirements)."""
    base = {
        "mandate_title": "Enhanced Prudential Standards (Regulation YY)",
        "text": "",
        "link": "https://www.ecfr.gov/current/title-12/part-252/section-252.22",
        "status": "In Force",
        "title_level_2": "Enhanced Prudential Standards for BHCs With $50B+",
        "citation_level_2": "Subpart C",
        "citation_level_3": "12 CFR 252.22",
        "effective_date": "1-Apr-2021",
        "applicability": "",
    }
    obligations = []
    for i in range(1, 14):
        obligations.append(Obligation(
            citation=f"12 CFR 252.22(a)({i})",
            abstract=f"Risk committee requirement {i}: The board of directors must establish a risk committee.",
            title_level_3="Risk committee requirements",
            title_level_4=f"Risk committee sub-requirement {i}",
            title_level_5="",
            **base,
        ))
    return obligations


@pytest.fixture
def sample_apqc_nodes() -> list[APQCNode]:
    """50 APQCNode objects covering sections 1.0, 9.0, 11.0 at depths 1-4."""
    nodes = []

    # Section 1 — Develop Vision and Strategy
    section1 = [
        (10001, "1.0", "Develop Vision and Strategy", 1, ""),
        (10002, "1.1", "Define the business concept and long-term vision", 2, "1.0"),
        (10003, "1.1.1", "Assess the external environment", 3, "1.1"),
        (10004, "1.1.1.1", "Analyze industry drivers", 4, "1.1.1"),
        (10005, "1.1.1.2", "Identify economic trends", 4, "1.1.1"),
        (10006, "1.1.2", "Survey market and customer needs", 3, "1.1"),
        (10007, "1.2", "Develop business strategy", 2, "1.0"),
        (10008, "1.2.1", "Develop overall mission statement", 3, "1.2"),
        (10009, "1.2.2", "Evaluate strategic options", 3, "1.2"),
        (10010, "1.3", "Manage strategic initiatives", 2, "1.0"),
        (10011, "1.3.1", "Develop strategic initiatives", 3, "1.3"),
    ]
    # Section 9 — Manage Financial Resources
    section9 = [
        (10100, "9.0", "Manage Financial Resources", 1, ""),
        (10101, "9.5", "Manage capital", 2, "9.0"),
        (10102, "9.5.1", "Manage capital structure", 3, "9.5"),
        (10103, "9.5.1.1", "Determine capital requirements", 4, "9.5.1"),
        (10104, "9.6", "Manage credit", 2, "9.0"),
        (10105, "9.6.1", "Manage credit portfolio", 3, "9.6"),
        (10106, "9.7", "Manage treasury operations", 2, "9.0"),
        (10107, "9.7.1", "Manage treasury policies and procedures", 3, "9.7"),
        (10108, "9.7.1.1", "Establish banking relationships", 4, "9.7.1"),
        (10109, "9.7.2", "Manage cash", 3, "9.7"),
    ]
    # Section 11 — Manage Enterprise Risk
    section11 = [
        (10200, "11.0", "Manage Enterprise Risk, Compliance, Remediation, and Resiliency", 1, ""),
        (10201, "11.1", "Manage enterprise risk", 2, "11.0"),
        (10202, "11.1.1", "Establish enterprise risk framework and policies", 3, "11.1"),
        (10203, "11.1.1.1", "Determine risk tolerance for organization", 4, "11.1.1"),
        (10204, "11.1.1.2", "Develop and maintain risk policies", 4, "11.1.1"),
        (10205, "11.1.2", "Manage enterprise-level risks", 3, "11.1"),
        (10206, "11.1.2.1", "Identify enterprise-level risks", 4, "11.1.2"),
        (10207, "11.1.3", "Manage business unit-level risks", 3, "11.1"),
        (10208, "11.2", "Manage compliance", 2, "11.0"),
        (10209, "11.2.1", "Manage regulatory compliance", 3, "11.2"),
        (10210, "11.2.1.1", "Monitor regulatory environment", 4, "11.2.1"),
        (10211, "11.2.2", "Manage internal compliance policies", 3, "11.2"),
        (10212, "11.3", "Manage remediation", 2, "11.0"),
        (10213, "11.3.1", "Manage internal audit", 3, "11.3"),
        (10214, "11.3.1.1", "Conduct internal audits", 4, "11.3.1"),
        (10215, "11.4", "Manage business resiliency", 2, "11.0"),
        (10216, "11.4.1", "Develop business continuity strategy", 3, "11.4"),
        (10217, "11.4.1.1", "Identify critical business functions", 4, "11.4.1"),
        (10218, "11.1.1.3", "Design risk management framework", 4, "11.1.1"),
        (10219, "11.1.1.4", "Establish risk governance structure", 4, "11.1.1"),
    ]

    for pcf_id, hid, name, depth, parent in section1 + section9 + section11:
        nodes.append(APQCNode(pcf_id=pcf_id, hierarchy_id=hid, name=name, depth=depth, parent_id=parent))

    # Pad to 50
    for i in range(len(nodes), 50):
        nodes.append(APQCNode(pcf_id=10300 + i, hierarchy_id=f"13.{i}.1", name=f"Placeholder process {i}", depth=3, parent_id=f"13.{i}"))

    return nodes[:50]


@pytest.fixture
def sample_controls() -> list[ControlRecord]:
    """20 ControlRecord objects at various hierarchy_ids."""
    controls = []
    base = {
        "selected_level_1": "Preventive",
        "where": "Governance Platform",
        "quality_rating": "Strong",
        "business_unit_name": "Risk Management",
    }
    templates = [
        ("CTRL-0100-RSK-001", "1.0", "Risk Limit Setting", "Chief Risk Officer",
         "Establishes risk appetite thresholds", "Annual", "Risk appetite control"),
        ("CTRL-0100-RSK-002", "1.1.1", "Risk and Compliance Assessments", "Risk Director",
         "Conducts external environment assessment", "Quarterly", "Environment assessment"),
        ("CTRL-0900-FIN-001", "9.5.1", "Authorization", "CFO",
         "Authorizes capital structure changes", "Quarterly", "Capital control"),
        ("CTRL-0900-FIN-002", "9.7.1", "Verification and Validation", "Treasury Manager",
         "Verifies treasury policy compliance", "Monthly", "Treasury control"),
        ("CTRL-0900-FIN-003", "9.7.1.1", "Documentation/Data/Activity Completeness and Appropriateness Checks", "Banking Analyst",
         "Checks banking relationship documentation", "Monthly", "Banking docs"),
        ("CTRL-1100-RSK-001", "11.1.1", "Risk Limit Setting", "CRO",
         "Sets enterprise risk framework limits", "Annual", "Enterprise risk"),
        ("CTRL-1100-RSK-002", "11.1.1.1", "Risk and Compliance Assessments", "Risk VP",
         "Determines organizational risk tolerance", "Annual", "Risk tolerance"),
        ("CTRL-1100-RSK-003", "11.1.2", "Risk Escalation Processes", "Risk Director",
         "Manages enterprise-level risk escalation", "Quarterly", "Risk escalation"),
        ("CTRL-1100-CMP-001", "11.2.1", "Verification and Validation", "Compliance Director",
         "Validates regulatory compliance status", "Monthly", "Compliance check"),
        ("CTRL-1100-AUD-001", "11.3.1", "Internal and External Audits", "Chief Auditor",
         "Conducts internal audit reviews", "Annual", "Internal audit"),
    ]

    for ctrl_id, hid, ctrl_type, who, what, freq, evidence in templates:
        controls.append(ControlRecord(
            control_id=ctrl_id,
            hierarchy_id=hid,
            leaf_name=f"Control at {hid}",
            full_description=f"{who} {what.lower()} using the {base['where']}.",
            selected_level_2=ctrl_type,
            who=who,
            what=what,
            when=f"At each {freq.lower()} cycle",
            frequency=freq,
            why=f"To ensure regulatory and internal policy compliance at {hid}.",
            evidence=evidence,
            **base,
        ))

    # Pad to 20
    for i in range(len(controls), 20):
        controls.append(ControlRecord(
            control_id=f"CTRL-PAD-{i:03d}",
            hierarchy_id=f"1.{i % 5}.{i % 3}",
            leaf_name=f"Padding control {i}",
            full_description=f"Padding control description {i}.",
            selected_level_2="Authorization",
            who="Analyst",
            what=f"Performs check {i}",
            when="Monthly",
            frequency="Monthly",
            why=f"To mitigate risk {i}.",
            evidence=f"Evidence {i}",
            **base,
        ))

    return controls[:20]
