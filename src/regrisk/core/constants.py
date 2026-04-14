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
