"""
Canonical string constants used across the pipeline.

Single source of truth for category names, coverage statuses,
relationship types, criticality tiers, and other repeated literals.
Validators, agents, graphs, and UI all import from here.
"""

from __future__ import annotations

# ── Obligation categories ────────────────────────────────────────────────

CATEGORY_ATTESTATION = "Attestation"
CATEGORY_DOCUMENTATION = "Documentation"
CATEGORY_CONTROLS = "Controls"
CATEGORY_GENERAL_AWARENESS = "General Awareness"
CATEGORY_NOT_ASSIGNED = "Not Assigned"

OBLIGATION_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_ATTESTATION,
    CATEGORY_DOCUMENTATION,
    CATEGORY_CONTROLS,
    CATEGORY_GENERAL_AWARENESS,
    CATEGORY_NOT_ASSIGNED,
})

ACTIONABLE_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_CONTROLS,
    CATEGORY_DOCUMENTATION,
    CATEGORY_ATTESTATION,
})

# ── Relationship types ───────────────────────────────────────────────────

REL_REQUIRES_EXISTENCE = "Requires Existence"
REL_CONSTRAINS_EXECUTION = "Constrains Execution"
REL_REQUIRES_EVIDENCE = "Requires Evidence"
REL_SETS_FREQUENCY = "Sets Frequency"
REL_NA = "N/A"

RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    REL_REQUIRES_EXISTENCE,
    REL_CONSTRAINS_EXECUTION,
    REL_REQUIRES_EVIDENCE,
    REL_SETS_FREQUENCY,
    REL_NA,
})

# ── Criticality tiers ────────────────────────────────────────────────────

CRITICALITY_HIGH = "High"
CRITICALITY_MEDIUM = "Medium"
CRITICALITY_LOW = "Low"

CRITICALITY_TIERS: frozenset[str] = frozenset({
    CRITICALITY_HIGH,
    CRITICALITY_MEDIUM,
    CRITICALITY_LOW,
})

# ── Coverage statuses ────────────────────────────────────────────────────

COVERAGE_COVERED = "Covered"
COVERAGE_PARTIALLY_COVERED = "Partially Covered"
COVERAGE_NOT_COVERED = "Not Covered"

COVERAGE_STATUSES: frozenset[str] = frozenset({
    COVERAGE_COVERED,
    COVERAGE_PARTIALLY_COVERED,
    COVERAGE_NOT_COVERED,
})

# ── Semantic match values ────────────────────────────────────────────────

SEMANTIC_FULL = "Full"
SEMANTIC_PARTIAL = "Partial"
SEMANTIC_NONE = "None"

SEMANTIC_MATCHES: frozenset[str] = frozenset({
    SEMANTIC_FULL,
    SEMANTIC_PARTIAL,
    SEMANTIC_NONE,
})

# ── Relationship match values ────────────────────────────────────────────

REL_MATCH_SATISFIED = "Satisfied"
REL_MATCH_PARTIAL = "Partial"
REL_MATCH_NOT_SATISFIED = "Not Satisfied"

RELATIONSHIP_MATCHES: frozenset[str] = frozenset({
    REL_MATCH_SATISFIED,
    REL_MATCH_PARTIAL,
    REL_MATCH_NOT_SATISFIED,
})

# ── Risk ratings ─────────────────────────────────────────────────────────

RISK_CRITICAL = "Critical"
RISK_HIGH = "High"
RISK_MEDIUM = "Medium"
RISK_LOW = "Low"

# ── Control improvement change types ──────────────────────────────────────

CHANGE_TYPE_NEW = "new"
CHANGE_TYPE_ENHANCEMENT = "enhancement"

CHANGE_TYPES: frozenset[str] = frozenset({
    CHANGE_TYPE_NEW,
    CHANGE_TYPE_ENHANCEMENT,
})

# ── Source types (hybrid obligation/policy/procedure model) ──────────────

SOURCE_TYPE_REGULATORY_OBLIGATION = "Regulatory_Obligation"
SOURCE_TYPE_POLICY_REQUIREMENT = "Policy_Requirement"
SOURCE_TYPE_STANDARD = "Standard"
SOURCE_TYPE_PROCEDURE_STEP = "Procedure_Step"

SOURCE_TYPES: frozenset[str] = frozenset({
    SOURCE_TYPE_REGULATORY_OBLIGATION,
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_STANDARD,
    SOURCE_TYPE_PROCEDURE_STEP,
})

INTERNAL_SOURCE_TYPES: frozenset[str] = frozenset({
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_STANDARD,
    SOURCE_TYPE_PROCEDURE_STEP,
})

# ── Requirement types (granular hint to classifier/mapper) ───────────────

REQUIREMENT_TYPES: frozenset[str] = frozenset({
    "Mandate",
    "Principle",
    "Standard",
    "Operational_Step",
    "Threshold",
    "Reporting_Obligation",
})

# ── Review reason codes (AI governance, machine-readable) ──────────────────

REVIEW_MISSING_SOURCE_OWNER = "missing_source_owner"
REVIEW_LOW_MAPPING_CONFIDENCE = "low_mapping_confidence"
REVIEW_EXCESSIVE_MAPPING_FANOUT = "excessive_mapping_fanout"
REVIEW_COVERAGE_PARTIAL = "coverage_partially_covered"
REVIEW_PENDING_CONTROL_GENERATION = "pending_control_generation"
REVIEW_POLICY_LIFECYCLE_BREACH = "policy_lifecycle_breach"
REVIEW_ORPHAN_PROCEDURE = "orphan_procedure"
REVIEW_PROCEDURE_CONTRADICTS_POLICY = "procedure_contradicts_policy"
REVIEW_MISSING_EVIDENCE_ARTIFACT = "missing_evidence_artifact"
REVIEW_CRITICAL_RESIDUAL_RISK = "critical_residual_risk"
REVIEW_WEAK_REGULATORY_TRACEABILITY = "weak_regulatory_traceability"
REVIEW_AMBIGUOUS_CONTROL_OWNER = "ambiguous_control_owner"
REVIEW_LOW_EXTRACTION_CONFIDENCE = "low_extraction_confidence"
REVIEW_UNCLASSIFIED_REQUIREMENT = "unclassified_requirement"

REVIEW_REASONS: frozenset[str] = frozenset({
    REVIEW_MISSING_SOURCE_OWNER,
    REVIEW_LOW_MAPPING_CONFIDENCE,
    REVIEW_EXCESSIVE_MAPPING_FANOUT,
    REVIEW_COVERAGE_PARTIAL,
    REVIEW_PENDING_CONTROL_GENERATION,
    REVIEW_POLICY_LIFECYCLE_BREACH,
    REVIEW_ORPHAN_PROCEDURE,
    REVIEW_PROCEDURE_CONTRADICTS_POLICY,
    REVIEW_MISSING_EVIDENCE_ARTIFACT,
    REVIEW_CRITICAL_RESIDUAL_RISK,
    REVIEW_WEAK_REGULATORY_TRACEABILITY,
    REVIEW_AMBIGUOUS_CONTROL_OWNER,
    REVIEW_LOW_EXTRACTION_CONFIDENCE,
    REVIEW_UNCLASSIFIED_REQUIREMENT,
})

# ── Defaults ─────────────────────────────────────────────────────────────

DEFAULT_MODEL = "gpt-4o"
DEFAULT_TRACE_DB_PATH = "data/traces.db"

# ── Column display overrides (shared by UI and Excel export) ─────────────

COL_DISPLAY_OVERRIDES: dict[str, str] = {
    "apqc_hierarchy_id": "APQC Hierarchy ID",
    "apqc_process_name": "APQC Process Name",
    "risk_id": "Risk ID",
    "control_id": "Control ID",
    "source_apqc_id": "Source APQC ID",
    # Data Source Explorer labels
    "mandate_title": "Regulation",
    "abstract": "Obligation Summary",
    "citation_level_2": "Subpart",
    "citation_level_3": "Section",
    "effective_date": "Effective Date",
    "pcf_id": "PCF ID",
    "hierarchy_id": "Hierarchy ID",
    "selected_level_1": "Control Type",
    "selected_level_2": "Control Category",
    "leaf_name": "Process Name",
    "who": "Performed By",
    "what": "Control Activity",
    "business_unit_name": "Business Unit",
    "quality_rating": "Rating",
    "full_description": "Full Description",
}
