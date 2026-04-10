"""Tabs 2 & 3: Classification Review and Mapping Review."""

from __future__ import annotations

import io
import uuid
from collections import defaultdict
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.core.events import EventEmitter
from regrisk.export.excel_export import export_for_review, import_reviewed
from regrisk.graphs.assess_graph import (
    build_assess_graph,
    get_partial_assessments,
    reset_caches as reset_assess_caches,
    set_emitter as set_assess_emitter,
)
from regrisk.tracing.db import TraceDB
from regrisk.tracing.listener import SQLiteTraceListener
from regrisk.ui.checkpoint import (
    STAGE_ASSESSED,
    STAGE_ASSESS_PARTIAL,
    STAGE_CLASSIFIED,
    STAGE_MAPPED,
    save_checkpoint,
)
from regrisk.ui.components import (
    CATEGORY_BG,
    build_partial_results,
    render_checkpoint_load,
    render_checkpoint_save,
    render_html_table,
    save_uploaded_file,
)


# ---------------------------------------------------------------------------
# Tracing helpers (shared with upload_tab)
# ---------------------------------------------------------------------------

def _get_trace_db() -> TraceDB:
    if "trace_db" not in st.session_state:
        from regrisk.core.constants import DEFAULT_TRACE_DB_PATH
        st.session_state["trace_db"] = TraceDB(DEFAULT_TRACE_DB_PATH)
    return st.session_state["trace_db"]


def _new_run_id() -> str:
    rid = uuid.uuid4().hex[:12]
    st.session_state["current_trace_run_id"] = rid
    return rid


# ---------------------------------------------------------------------------
# Tab 2: Classification Review
# ---------------------------------------------------------------------------

def render_classification_review_tab() -> None:
    """Render the classification review tab."""
    classified = st.session_state.get("classified_obligations", [])

    if not classified:
        st.info("Run classification first (Tab 1).")
        return

    st.header(f"Classification Review ({len(classified)} obligations)")

    df = pd.DataFrame(classified)

    col1, col2 = st.columns(2)
    with col1:
        cat_filter = st.multiselect(
            "Filter by Category",
            options=sorted(df["obligation_category"].unique()) if "obligation_category" in df.columns else [],
            key="cat_filter",
        )
    with col2:
        crit_filter = st.multiselect(
            "Filter by Criticality",
            options=["High", "Medium", "Low"],
            key="crit_filter",
        )

    if cat_filter:
        df = df[df["obligation_category"].isin(cat_filter)]
    if crit_filter:
        df = df[df["criticality_tier"].isin(crit_filter)]

    display_cols = [
        "subpart", "citation", "abstract", "relationship_type",
        "criticality_tier", "obligation_category",
        "classification_rationale",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    render_html_table(
        df, display_cols, height=400,
        color_col="obligation_category", color_map=CATEGORY_BG,
    )

    # Download / Upload review
    col1, col2 = st.columns(2)
    with col1:
        buf = io.BytesIO()
        export_for_review(classified, "classification", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="classification_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_classify_review",
        )
        if uploaded_review:
            review_path = save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "classification")
            st.session_state["classified_obligations"] = reviewed
            st.success(f"Imported {len(reviewed)} approved classifications.")
            st.rerun()

    st.divider()
    render_checkpoint_save(STAGE_CLASSIFIED, "tab2")
    render_checkpoint_load([STAGE_CLASSIFIED], "tab2")

    st.divider()

    if st.button("✅ Approve and Continue to Mapping", type="primary"):
        st.session_state["approved_for_mapping"] = True
        _run_mapping()


# ---------------------------------------------------------------------------
# Tab 3: Mapping Review
# ---------------------------------------------------------------------------

def render_mapping_review_tab() -> None:
    """Render the mapping review tab."""
    mappings = st.session_state.get("obligation_mappings", [])

    if not mappings:
        st.info("Run APQC mapping first (approve classifications in Tab 2).")
        return

    st.header(f"APQC Mapping Review ({len(mappings)} mappings)")

    df = pd.DataFrame(mappings)
    display_cols = [
        "citation", "apqc_hierarchy_id", "apqc_process_name",
        "relationship_type", "relationship_detail", "confidence",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    render_html_table(df, display_cols, height=400)

    col1, col2 = st.columns(2)
    with col1:
        buf = io.BytesIO()
        export_for_review(mappings, "mapping", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="mapping_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_mapping_review",
        )
        if uploaded_review:
            review_path = save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "mapping")
            st.session_state["obligation_mappings"] = reviewed
            st.success(f"Imported {len(reviewed)} approved mappings.")
            st.rerun()

    st.divider()
    render_checkpoint_save(STAGE_MAPPED, "tab3")
    render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESS_PARTIAL], "tab3")

    st.divider()

    if st.button("✅ Approve and Run Coverage Assessment", type="primary"):
        _run_assessment()


# ---------------------------------------------------------------------------
# Pipeline runners (mapping + assessment)
# ---------------------------------------------------------------------------

def _run_mapping() -> None:
    """Run Graph 2 mapping phase."""
    emitter = EventEmitter()
    reset_assess_caches()
    set_assess_emitter(emitter)

    classified = st.session_state.get("classified_obligations", [])
    config = st.session_state.get("pipeline_config", {})
    actionable = set(config.get("actionable_categories", ["Controls", "Documentation", "Attestation"]))

    groups_by_section: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        if ob.get("obligation_category") in actionable:
            key = ob.get("section_citation", "unknown")
            groups_by_section[key].append(ob)

    mappable_groups = []
    for section_cit, obs in groups_by_section.items():
        first = obs[0]
        mappable_groups.append({
            "section_citation": section_cit,
            "section_title": first.get("section_title", ""),
            "subpart": first.get("subpart", ""),
            "obligations": obs,
        })

    input_state: dict[str, Any] = {
        "regulation_name": st.session_state.get("regulation_name", ""),
        "pipeline_config": config,
        "risk_taxonomy": st.session_state.get("risk_taxonomy", {}),
        "llm_enabled": st.session_state.get("llm_enabled", False),
        "apqc_nodes": st.session_state.get("apqc_nodes", []),
        "controls": st.session_state.get("controls", []),
        "approved_obligations": classified,
        "mappable_groups": mappable_groups,
        "map_idx": 0,
    }

    with st.spinner("Running APQC mapping…"):
        try:
            trace_db = _get_trace_db()
            run_id = _new_run_id()
            trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-mapping")
            trace_listener = SQLiteTraceListener(trace_db, run_id)
            emitter.on(trace_listener)

            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
        except Exception as exc:
            st.error(f"Mapping pipeline failed: {type(exc).__name__}: {exc}")
            return

    st.session_state["obligation_mappings"] = result.get("obligation_mappings", [])
    st.session_state["assess_result"] = result

    save_checkpoint(STAGE_MAPPED, dict(st.session_state))

    st.success(f"Mapping complete! {len(st.session_state['obligation_mappings'])} mappings produced.")
    st.rerun()


def _run_assessment() -> None:
    """Run Graph 2 with full assessment."""
    emitter = EventEmitter()
    reset_assess_caches()
    set_assess_emitter(emitter)

    classified = st.session_state.get("classified_obligations", [])
    config = st.session_state.get("pipeline_config", {})
    actionable = set(config.get("actionable_categories", ["Controls", "Documentation", "Attestation"]))

    groups_by_section: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        if ob.get("obligation_category") in actionable:
            key = ob.get("section_citation", "unknown")
            groups_by_section[key].append(ob)

    mappable_groups = []
    for section_cit, obs in groups_by_section.items():
        first = obs[0]
        mappable_groups.append({
            "section_citation": section_cit,
            "section_title": first.get("section_title", ""),
            "subpart": first.get("subpart", ""),
            "obligations": obs,
        })

    input_state: dict[str, Any] = {
        "regulation_name": st.session_state.get("regulation_name", ""),
        "pipeline_config": config,
        "risk_taxonomy": st.session_state.get("risk_taxonomy", {}),
        "llm_enabled": st.session_state.get("llm_enabled", False),
        "apqc_nodes": st.session_state.get("apqc_nodes", []),
        "controls": st.session_state.get("controls", []),
        "approved_obligations": classified,
        "mappable_groups": mappable_groups,
        "map_idx": 0,
    }

    with st.spinner("Running full assessment pipeline…"):
        try:
            trace_db = _get_trace_db()
            run_id = _new_run_id()
            trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-full")
            trace_listener = SQLiteTraceListener(trace_db, run_id)
            emitter.on(trace_listener)

            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
        except Exception as exc:
            partial = get_partial_assessments()
            if partial:
                st.session_state["coverage_assessments"] = partial
                build_partial_results(partial, classified)
                save_checkpoint(STAGE_ASSESS_PARTIAL, dict(st.session_state))
                st.warning(
                    f"Pipeline failed but **{len(partial)} assessments** were completed and saved. "
                    f"Check the **Results** tab for partial results, or resume from the checkpoint."
                )
            st.error(f"Assessment pipeline failed: {type(exc).__name__}: {exc}")
            return

    st.session_state["assess_result"] = result
    st.session_state["obligation_mappings"] = result.get("obligation_mappings", [])
    st.session_state["coverage_assessments"] = result.get("coverage_assessments", [])
    st.session_state["scored_risks"] = result.get("scored_risks", [])
    st.session_state["gap_report"] = result.get("gap_report", {})
    st.session_state["compliance_matrix"] = result.get("compliance_matrix", {})
    st.session_state["risk_register"] = result.get("risk_register", {})

    save_checkpoint(STAGE_ASSESSED, dict(st.session_state))

    st.success("Assessment complete!")
    st.rerun()
