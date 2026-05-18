"""
Source-type-aware prompt fragments.

Centralized so all four LLM agents (classifier, mapper, coverage assessor,
risk extractor) inject a consistent guidance block when the input row's
``source_type`` is anything other than the default ``Regulatory_Obligation``.

Phase 3 of the hybrid source-led workflow. Keeping these as small string
fragments (not template engines) preserves the existing
``call_llm`` / ``parse_json`` plumbing in :mod:`regrisk.agents.base`.
"""

from __future__ import annotations

from regrisk.core.constants import (
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_PROCEDURE_STEP,
    SOURCE_TYPE_REGULATORY_OBLIGATION,
    SOURCE_TYPE_STANDARD,
)


# ── Per-agent guidance blocks ─────────────────────────────────────────────

_CLASSIFIER_GUIDANCE: dict[str, str] = {
    SOURCE_TYPE_REGULATORY_OBLIGATION: (
        "SOURCE TYPE: Regulatory_Obligation. Apply the standard Promontory/IBM RCM "
        "categories. Criticality reflects regulator enforcement risk."
    ),
    SOURCE_TYPE_POLICY_REQUIREMENT: (
        "SOURCE TYPE: Policy_Requirement. The source is an INTERNAL policy mandate. "
        "Choose 'Controls' when the policy prescribes a specific control outcome; "
        "'General Awareness' when it states a principle without a control bite. "
        "Criticality reflects internal-audit / board-level risk, not regulator risk."
    ),
    SOURCE_TYPE_STANDARD: (
        "SOURCE TYPE: Standard. The source is an INTERNAL standard. Prefer "
        "'Documentation' or 'Controls' depending on whether the standard prescribes "
        "evidence (Documentation) vs operational behaviour (Controls)."
    ),
    SOURCE_TYPE_PROCEDURE_STEP: (
        "SOURCE TYPE: Procedure_Step. The source is an operational step under a "
        "parent policy. Default category is 'Controls'. Relationship_type is usually "
        "'Constrains Execution' or 'Sets Frequency'. Criticality should mirror the "
        "parent policy unless the step is informational."
    ),
}

_MAPPER_GUIDANCE: dict[str, str] = {
    SOURCE_TYPE_REGULATORY_OBLIGATION: (
        "SOURCE TYPE: Regulatory_Obligation. Prefer L3-L4 APQC specificity. "
        "One regulation may map to many APQC processes."
    ),
    SOURCE_TYPE_POLICY_REQUIREMENT: (
        "SOURCE TYPE: Policy_Requirement. Prefer L2-L3 APQC process families "
        "(broader mappings expected). If no clear APQC match exists, emit ONE "
        "mapping with confidence <= 0.4."
    ),
    SOURCE_TYPE_STANDARD: (
        "SOURCE TYPE: Standard. Prefer L3 APQC processes. Confidence should be "
        "high (>=0.8) only when standard text and APQC name share substantive overlap."
    ),
    SOURCE_TYPE_PROCEDURE_STEP: (
        "SOURCE TYPE: Procedure_Step. Prefer L4-L5 APQC specificity. Usually a "
        "single mapping. Use the parent policy's business unit to disambiguate."
    ),
}

_COVERAGE_GUIDANCE: dict[str, str] = {
    SOURCE_TYPE_REGULATORY_OBLIGATION: (
        "SOURCE TYPE: Regulatory_Obligation. Evaluate coverage from a "
        "regulator-defensibility perspective."
    ),
    SOURCE_TYPE_POLICY_REQUIREMENT: (
        "SOURCE TYPE: Policy_Requirement. Evaluate whether the control enforces the "
        "policy's INTENT, not just its letter. If no control exists at the APQC "
        "node, mark Not Covered and flag for control GENERATION (a new control "
        "should be authored from the policy text)."
    ),
    SOURCE_TYPE_STANDARD: (
        "SOURCE TYPE: Standard. Evaluate strict adherence \u2014 standards are typically "
        "binary (compliant or not)."
    ),
    SOURCE_TYPE_PROCEDURE_STEP: (
        "SOURCE TYPE: Procedure_Step. Evaluate whether the control implements the "
        "specific operational step. Frequency mismatches are material."
    ),
}

_RISK_GUIDANCE: dict[str, str] = {
    SOURCE_TYPE_REGULATORY_OBLIGATION: (
        "SOURCE TYPE: Regulatory_Obligation. Frame risks as NONCOMPLIANCE: regulator "
        "action, fines, consent orders, MRAs, reputational damage with regulators."
    ),
    SOURCE_TYPE_POLICY_REQUIREMENT: (
        "SOURCE TYPE: Policy_Requirement. Frame risks as POLICY BREACH: operational "
        "failure, internal-audit findings, board-level escalation, control-environment "
        "weakness. Penalties are internal, not regulatory."
    ),
    SOURCE_TYPE_STANDARD: (
        "SOURCE TYPE: Standard. Frame risks as STANDARD VIOLATION: inconsistent "
        "execution across business units, audit findings, remediation cost."
    ),
    SOURCE_TYPE_PROCEDURE_STEP: (
        "SOURCE TYPE: Procedure_Step. Frame risks as PROCESS EXECUTION FAILURE: "
        "control bypass, data quality issues, exception backlog, manual error rate."
    ),
}


def _resolve(table: dict[str, str], source_type: str | None) -> str:
    """Return the guidance fragment for ``source_type`` or empty string."""
    if not source_type:
        return ""
    return table.get(source_type, table[SOURCE_TYPE_REGULATORY_OBLIGATION])


def classifier_guidance(source_type: str | None) -> str:
    return _resolve(_CLASSIFIER_GUIDANCE, source_type)


def mapper_guidance(source_type: str | None) -> str:
    return _resolve(_MAPPER_GUIDANCE, source_type)


def coverage_guidance(source_type: str | None) -> str:
    return _resolve(_COVERAGE_GUIDANCE, source_type)


def risk_guidance(source_type: str | None) -> str:
    return _resolve(_RISK_GUIDANCE, source_type)
