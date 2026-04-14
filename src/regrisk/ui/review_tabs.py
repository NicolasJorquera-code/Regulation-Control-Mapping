"""Tabs 2 & 3: Classification Review and Mapping Review.

Tab 2 uses a master-detail split (60 / 40) with ObligationCard list on the
left and full detail on the right.  Tab 3 uses grouped expander panels per
obligation with nested MappingChip components.
"""

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
    set_auto_save as set_assess_auto_save,
    set_emitter as set_assess_emitter,
)
from regrisk.tracing.db import TraceDB
from regrisk.tracing.listener import SQLiteTraceListener
from regrisk.ui.progress import StreamlitProgressListener
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
    format_citation,
    criticality_dot,
    render_checkpoint_load,
    render_checkpoint_save,
    render_filter_bar,
    render_mapping_chip,
    render_obligation_card,
    render_obligation_detail,
    render_obligation_text_only,
    save_uploaded_file,
)
from regrisk.ui.session_keys import SK


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
# Tab 2: Classification Review  (master-detail split)
# ---------------------------------------------------------------------------

def render_classification_review_tab() -> None:
    """Render the classification review tab with master-detail layout."""
    classified = st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, [])

    if not classified:
        st.info("Run classification first (Tab 1).")
        return

    st.header(f"Classification Review ({len(classified)} obligations)")

    df = pd.DataFrame(classified)
    total_count = len(df)

    # ── Summary statistics — Row 1: Obligation breakdown by type ──
    from collections import Counter
    cat_counts = Counter(ob.get("obligation_category", "Not Assigned") for ob in classified)
    crit_counts = Counter(ob.get("criticality_tier", "Unrated") for ob in classified)
    total = len(classified) or 1

    cat_order = ["Controls", "Documentation", "Attestation", "General Awareness", "Not Assigned"]
    active_cats = [(c, cat_counts.get(c, 0)) for c in cat_order if cat_counts.get(c, 0) > 0]

    if active_cats:
        # Stacked bar as colored HTML segments
        bar_segments = []
        for cat, cnt in active_cats:
            pct = cnt / total * 100
            bg = CATEGORY_BG.get(cat, "#E2E3E5")
            label = f"{cat} ({cnt})" if pct >= 12 else str(cnt)
            bar_segments.append(
                f'<div style="background:{bg};width:{pct:.1f}%;padding:6px 8px;text-align:center;'
                f'font-size:0.78rem;white-space:nowrap;overflow:hidden">{label}</div>'
            )
        bar_html = (
            '<div style="display:flex;border-radius:6px;overflow:hidden;border:1px solid #ddd">'
            + "".join(bar_segments)
            + "</div>"
        )
        st.markdown("**Obligation breakdown by type**")
        st.markdown(bar_html, unsafe_allow_html=True)

        # Dominant category insight
        top_cat, top_cnt = active_cats[0]
        top_pct = top_cnt / total * 100
        if top_pct >= 40:
            st.caption(f"Most obligations ({top_pct:.0f}%) are **{top_cat}**.")

    # ── Row 2: Risk profile ──
    st.markdown("**Risk profile**")
    rc1, rc2, rc3 = st.columns(3)
    for col, tier, dot in ((rc1, "High", "🔴"), (rc2, "Medium", "🟡"), (rc3, "Low", "⚪")):
        cnt = crit_counts.get(tier, 0)
        pct = cnt / total * 100
        col.metric(f"{dot} {tier}", f"{cnt} ({pct:.0f}%)")

    high_pct = crit_counts.get("High", 0) / total * 100
    if high_pct >= 40:
        st.caption(f"{high_pct:.0f}% of obligations are high-criticality — enforcement risk if not addressed.")

    st.divider()

    # ── Filter bar ──
    df_filtered = render_filter_bar(
        df, total_count, key_prefix="tab2",
        show_category=True, show_criticality=True, show_subpart=True,
    )

    # Keep a list version for card rendering
    filtered_records = df_filtered.to_dict("records")

    # Ensure selected index is valid
    sel_key = SK.SELECTED_OBLIGATION_IDX
    if sel_key not in st.session_state:
        st.session_state[sel_key] = 0
    if st.session_state[sel_key] >= len(filtered_records):
        st.session_state[sel_key] = 0

    # ── Master-detail columns ──
    col_list, col_detail = st.columns([0.6, 0.4])

    with col_list:
        with st.container(height=900):
            # Group by subpart
            groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
            for idx, ob in enumerate(filtered_records):
                subpart = ob.get("subpart", "General")
                groups[subpart].append((idx, ob))

            for subpart in sorted(groups.keys()):
                st.subheader(subpart, divider="gray")
                for idx, ob in groups[subpart]:
                    clicked = render_obligation_card(
                        ob, idx, st.session_state[sel_key], key_prefix="tab2_ob",
                    )
                    if clicked:
                        st.session_state[sel_key] = idx
                        st.rerun()

    with col_detail:
        if filtered_records:
            sel_idx = st.session_state[sel_key]
            if 0 <= sel_idx < len(filtered_records):
                render_obligation_detail(filtered_records[sel_idx])

    # ── Actions ──
    st.divider()

    col_dl, col_ul = st.columns(2)
    with col_dl:
        buf = io.BytesIO()
        export_for_review(classified, "classification", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="classification_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_ul:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_classify_review",
        )
        if uploaded_review:
            review_path = save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "classification")
            st.session_state[SK.CLASSIFIED_OBLIGATIONS] = reviewed
            st.success(f"Imported {len(reviewed)} approved classifications.")
            st.rerun()

    st.divider()
    render_checkpoint_save(STAGE_CLASSIFIED, "tab2")
    render_checkpoint_load([STAGE_CLASSIFIED], "tab2")

    st.divider()

    if st.button("✅ Approve and Continue to Mapping", type="primary"):
        st.session_state[SK.APPROVED_FOR_MAPPING] = True
        _run_mapping()


# ---------------------------------------------------------------------------
# Tab 3: Mapping Review  (grouped panels + nested chips)
# ---------------------------------------------------------------------------

def render_mapping_review_tab() -> None:
    """Render the mapping review tab with master-detail layout."""
    mappings = st.session_state.get(SK.OBLIGATION_MAPPINGS, [])

    if not mappings:
        st.info("Run APQC mapping first (approve classifications in Tab 2).")
        return

    # ── Build per-obligation mapping groups + metadata ──
    mappings_by_citation: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mappings_by_citation[m.get("citation", "unknown")].append(m)

    classified = st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, [])
    ob_meta: dict[str, dict] = {}
    for ob in classified:
        cit = ob.get("citation", "")
        if cit:
            ob_meta[cit] = ob

    # Build records list for mapped obligations only
    mapped_records: list[dict] = []
    for cit in mappings_by_citation:
        meta = ob_meta.get(cit, {})
        rec = dict(meta) if meta else {"citation": cit}
        rec.setdefault("citation", cit)
        rec.setdefault("subpart", "General")
        rec.setdefault("obligation_category", "Not Assigned")
        rec.setdefault("criticality_tier", "Low")
        mapped_records.append(rec)

    st.header("APQC Mapping Review")

    from collections import Counter

    total = len(mapped_records) or 1
    cat_counts = Counter(r.get("obligation_category", "Not Assigned") for r in mapped_records)
    crit_counts = Counter(r.get("criticality_tier", "Low") for r in mapped_records)

    # ── Obligation breakdown bar ──
    cat_order = ["Controls", "Documentation", "Attestation", "General Awareness", "Not Assigned"]
    active_cats = [(c, cat_counts.get(c, 0)) for c in cat_order if cat_counts.get(c, 0) > 0]

    if active_cats:
        bar_segments = []
        for cat, cnt in active_cats:
            pct = cnt / total * 100
            bg = CATEGORY_BG.get(cat, "#E2E3E5")
            label = f"{cat} ({cnt})" if pct >= 12 else str(cnt)
            bar_segments.append(
                f'<div style="background:{bg};width:{pct:.1f}%;padding:6px 8px;text-align:center;'
                f'font-size:0.78rem;white-space:nowrap;overflow:hidden">{label}</div>'
            )
        bar_html = (
            '<div style="display:flex;border-radius:6px;overflow:hidden;border:1px solid #ddd">'
            + "".join(bar_segments)
            + "</div>"
        )
        st.markdown("**Obligation breakdown by type**")
        st.markdown(bar_html, unsafe_allow_html=True)

    # ── Risk profile ──
    st.markdown("**Risk profile**")
    rc1, rc2, rc3 = st.columns(3)
    for col, tier, dot in ((rc1, "High", "🔴"), (rc2, "Medium", "🟡"), (rc3, "Low", "⚪")):
        cnt = crit_counts.get(tier, 0)
        pct = cnt / total * 100
        col.metric(f"{dot} {tier}", f"{cnt} ({pct:.0f}%)")

    st.divider()

    # ── Filter bar ──
    df = pd.DataFrame(mapped_records)
    total_count = len(df)
    df_filtered = render_filter_bar(
        df, total_count, key_prefix="tab3",
        show_category=True, show_criticality=True, show_subpart=True,
    )
    filtered_records = df_filtered.to_dict("records")

    # Ensure selected index is valid
    sel_key = SK.SELECTED_MAPPING_OBLIGATION_IDX
    if sel_key not in st.session_state or st.session_state[sel_key] is None:
        st.session_state[sel_key] = 0
    if st.session_state[sel_key] >= len(filtered_records):
        st.session_state[sel_key] = 0

    # ── Master-detail columns ──
    col_list, col_detail = st.columns([0.6, 0.4])

    with col_list:
        with st.container(height=900):
            groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
            for idx, ob in enumerate(filtered_records):
                subpart = ob.get("subpart", "General")
                groups[subpart].append((idx, ob))

            for subpart in sorted(groups.keys()):
                st.subheader(subpart, divider="gray")
                for idx, ob in groups[subpart]:
                    cit = ob.get("citation", "")
                    n_maps = len(mappings_by_citation.get(cit, []))
                    map_label = f"**{n_maps} mapping{'s' if n_maps != 1 else ''}**"
                    clicked = render_obligation_card(
                        ob, idx, st.session_state[sel_key],
                        key_prefix="tab3_ob",
                        extra_label=map_label,
                    )
                    if clicked:
                        st.session_state[sel_key] = idx
                        st.rerun()

    with col_detail:
        if filtered_records:
            sel_idx = st.session_state[sel_key]
            if 0 <= sel_idx < len(filtered_records):
                selected_ob = filtered_records[sel_idx]
                render_obligation_text_only(selected_ob)

                # ── APQC Mappings for this obligation ──
                sel_cit = selected_ob.get("citation", "")
                ob_maps = mappings_by_citation.get(sel_cit, [])
                if ob_maps:
                    st.markdown("#### APQC Mappings")
                    for mapping in ob_maps:
                        render_mapping_chip(mapping)

    # ── Actions ──
    st.divider()

    col_dl, col_ul = st.columns(2)
    with col_dl:
        buf = io.BytesIO()
        export_for_review(mappings, "mapping", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="mapping_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_ul:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_mapping_review",
        )
        if uploaded_review:
            review_path = save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "mapping")
            st.session_state[SK.OBLIGATION_MAPPINGS] = reviewed
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

    trace_db = _get_trace_db()
    run_id = _new_run_id()
    trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-mapping")
    trace_listener = SQLiteTraceListener(trace_db, run_id)
    emitter.on(trace_listener)

    progress_bar = st.progress(0, text="Initializing APQC mapping…")
    with st.status("APQC Mapping Pipeline", expanded=True) as status:
        progress_listener = StreamlitProgressListener(progress_bar, status, "assess")
        emitter.on(progress_listener)
        try:
            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
            status.update(label="Mapping complete!", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="Mapping failed", state="error")
            st.error(f"Mapping pipeline failed: {type(exc).__name__}: {exc}")
            return
        finally:
            progress_listener.detach()
    progress_bar.progress(100, text="Mapping complete!")

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

    trace_db = _get_trace_db()
    run_id = _new_run_id()
    trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-full")
    trace_listener = SQLiteTraceListener(trace_db, run_id)
    emitter.on(trace_listener)

    def _auto_save_partial(partial: list[dict]) -> None:
        """Periodic auto-save: persist partial assessment checkpoint."""
        st.session_state["coverage_assessments"] = list(partial)
        build_partial_results(partial, classified)
        save_checkpoint(STAGE_ASSESS_PARTIAL, dict(st.session_state))

    set_assess_auto_save(_auto_save_partial, interval=25)

    progress_bar = st.progress(0, text="Initializing assessment pipeline…")
    with st.status("Assessment Pipeline", expanded=True) as status:
        progress_listener = StreamlitProgressListener(progress_bar, status, "assess")
        emitter.on(progress_listener)
        try:
            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
            status.update(label="Assessment complete!", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="Assessment failed", state="error")
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
        finally:
            progress_listener.detach()
    progress_bar.progress(100, text="Assessment complete!")

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
