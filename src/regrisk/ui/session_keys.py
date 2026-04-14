"""
Catalog of ``st.session_state`` keys used across the Streamlit UI.

Every key that the application reads or writes is listed here with its type
and a short description.  Modules should reference these constants instead of
repeating bare strings so that typos are caught by the linter.

Usage::

    from regrisk.ui.session_keys import SK
    obligations = st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, [])
"""

from __future__ import annotations


class SK:
    """String constants for every ``st.session_state`` key."""

    # ── Pipeline data (written by graph invocations) ──
    CLASSIFY_RESULT = "classify_result"
    CLASSIFIED_OBLIGATIONS = "classified_obligations"
    OBLIGATION_GROUPS = "obligation_groups"
    APQC_NODES = "apqc_nodes"
    CONTROLS = "controls"
    REGULATION_NAME = "regulation_name"
    PIPELINE_CONFIG = "pipeline_config"
    RISK_TAXONOMY = "risk_taxonomy"
    LLM_ENABLED = "llm_enabled"

    ASSESS_RESULT = "assess_result"
    OBLIGATION_MAPPINGS = "obligation_mappings"
    COVERAGE_ASSESSMENTS = "coverage_assessments"
    SCORED_RISKS = "scored_risks"
    GAP_REPORT = "gap_report"
    COMPLIANCE_MATRIX = "compliance_matrix"
    RISK_REGISTER = "risk_register"

    # ── UI control flags ──
    APPROVED_FOR_MAPPING = "approved_for_mapping"
    CACHES_INITIALISED = "caches_initialised"
    CLASSIFICATION_JUST_COMPLETED = "classification_just_completed"

    # ── UI navigation ──
    SELECTED_OBLIGATION_IDX = "selected_obligation_idx"
    SELECTED_MAPPING_OBLIGATION_IDX = "selected_mapping_obligation_idx"
    SELECTED_RESULTS_IDX = "selected_results_idx"
    RESULTS_GAP_EXPANDED = "results_gap_expanded"
    RESULTS_RISK_EXPANDED = "results_risk_expanded"

    # ── Data Source Explorer ──
    EXPLORER_DATA_PATHS = "explorer_data_paths"

    # ── Tracing ──
    TRACE_DB = "trace_db"
    CURRENT_TRACE_RUN_ID = "current_trace_run_id"
