"""Tab 5: Traceability — SQLite-backed execution trace viewer and data lineage."""

from __future__ import annotations

import time as _time
from collections import defaultdict
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.tracing.db import TraceDB


# ---------------------------------------------------------------------------
# Event colors for timeline
# ---------------------------------------------------------------------------

_EVENT_COLOR: dict[str, str] = {
    "pipeline_started": "#1E88E5",
    "pipeline_completed": "#43A047",
    "pipeline_failed": "#E53935",
    "stage_started": "#1E88E5",
    "stage_completed": "#43A047",
    "item_started": "#FDD835",
    "item_completed": "#43A047",
    "group_classified": "#7E57C2",
    "mapping_completed": "#26A69A",
    "coverage_assessed": "#42A5F5",
    "risk_scored": "#FF7043",
    "warning": "#FFA726",
}


def _get_trace_db() -> TraceDB:
    if "trace_db" not in st.session_state:
        from regrisk.core.constants import DEFAULT_TRACE_DB_PATH
        st.session_state["trace_db"] = TraceDB(DEFAULT_TRACE_DB_PATH)
    return st.session_state["trace_db"]


# ---------------------------------------------------------------------------
# Tab renderer
# ---------------------------------------------------------------------------

def render_traceability_tab() -> None:
    """Render the traceability tab."""
    trace_db = _get_trace_db()
    runs = trace_db.list_runs(limit=50)

    # ── Section A: Run Selector ──
    st.header("🔍 Execution Trace Viewer")
    st.caption(
        "Every pipeline run is recorded to a local SQLite database at "
        "**data/traces.db**. You can also query it directly in a terminal: "
        "`sqlite3 data/traces.db \"SELECT * FROM runs;\"`"
    )

    if not runs:
        st.info("No traced runs yet. Run the pipeline to start recording traces.")
        _render_data_lineage()
        return

    run_labels: dict[str, str] = {}
    for r in runs:
        ts = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(r["started_at"]))
        status_icon = {"running": "🟡", "completed": "🟢", "failed": "🔴"}.get(r["status"], "⚪")
        label = f"{status_icon} {r['graph_name']} — {r.get('regulation_name') or '(unnamed)'} — {ts}"
        run_labels[r["run_id"]] = label

    current_run_id = st.session_state.get("current_trace_run_id", "")
    default_idx = 0
    run_ids = [r["run_id"] for r in runs]
    if current_run_id in run_ids:
        default_idx = run_ids.index(current_run_id)

    selected_id = st.selectbox(
        "Select a run",
        options=run_ids,
        index=default_idx,
        format_func=lambda rid: run_labels.get(rid, rid),
    )

    if not selected_id:
        return

    summary = trace_db.get_run_summary(selected_id)
    if not summary:
        st.warning("Run not found.")
        return

    # ── Section B: Run Overview ──
    st.subheader("📊 Run Overview")
    status_badge = {"running": "🟡 Running", "completed": "🟢 Completed", "failed": "🔴 Failed"}.get(
        summary.get("status", ""), summary.get("status", "")
    )
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Status", status_badge)
    col2.metric("Nodes Executed", summary.get("node_count", 0))
    col3.metric("LLM Calls", summary.get("llm_call_count", 0))
    col4.metric("Total Tokens", f"{summary.get('total_tokens', 0):,}")
    duration_s = (summary.get("total_node_ms", 0) or 0) / 1000
    col5.metric("Node Time", f"{duration_s:.1f}s")

    # ── Section C: Event Timeline ──
    st.subheader("📋 Event Timeline")
    events = trace_db.get_run_events(selected_id)
    if events:
        event_rows = []
        for e in events:
            ts = _time.strftime("%H:%M:%S", _time.localtime(e["timestamp"]))
            event_rows.append({
                "Time": ts,
                "Event": e["event_type"],
                "Stage": e.get("stage") or "",
                "Message": e.get("message") or "",
            })
        df_events = pd.DataFrame(event_rows)
        st.dataframe(df_events, width='stretch', hide_index=True)
    else:
        st.caption("No events recorded.")

    # ── Section D: Node Executions ──
    st.subheader("⚙️ Node Executions")
    nodes = trace_db.get_run_nodes(selected_id)
    if nodes:
        node_rows = []
        for n in nodes:
            node_rows.append({
                "Node": n["node_name"],
                "Duration (ms)": round(n.get("duration_ms") or 0, 1),
                "Input": n.get("input_summary") or "",
                "Output": n.get("output_summary") or "",
                "Error": n.get("error") or "",
            })
        df_nodes = pd.DataFrame(node_rows)
        st.dataframe(df_nodes, width='stretch', hide_index=True)

        if len(node_rows) > 1:
            chart_df = df_nodes[["Node", "Duration (ms)"]].set_index("Node")
            st.bar_chart(chart_df)
    else:
        st.caption("No node executions recorded.")

    # ── Section E: LLM Call Inspector ──
    st.subheader("🤖 LLM Call Inspector")
    llm_calls = trace_db.get_run_llm_calls(selected_id)
    if llm_calls:
        total_prompt_tok = sum(c.get("prompt_tokens") or 0 for c in llm_calls)
        total_comp_tok = sum(c.get("completion_tokens") or 0 for c in llm_calls)
        total_latency = sum(c.get("latency_ms") or 0 for c in llm_calls)
        avg_latency = total_latency / len(llm_calls) if llm_calls else 0

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total LLM Calls", len(llm_calls))
        mc2.metric("Prompt Tokens", f"{total_prompt_tok:,}")
        mc3.metric("Completion Tokens", f"{total_comp_tok:,}")
        mc4.metric("Avg Latency", f"{avg_latency:.0f}ms")

        call_rows = []
        for i, c in enumerate(llm_calls):
            ts = _time.strftime("%H:%M:%S", _time.localtime(c["timestamp"]))
            call_rows.append({
                "#": i + 1,
                "Time": ts,
                "Node": c.get("node_name") or "",
                "Agent": c.get("agent_name") or "",
                "Model": c.get("model") or "",
                "Prompt Tok": c.get("prompt_tokens") or 0,
                "Comp Tok": c.get("completion_tokens") or 0,
                "Latency (ms)": round(c.get("latency_ms") or 0, 0),
                "Error": c.get("error") or "",
            })
        st.dataframe(pd.DataFrame(call_rows), width='stretch', hide_index=True)

        if len(llm_calls) > 1:
            tok_by_node: dict[str, int] = defaultdict(int)
            for c in llm_calls:
                tok_by_node[c.get("node_name") or "unknown"] += (c.get("total_tokens") or 0)
            if tok_by_node:
                st.caption("Token usage by node")
                tok_df = pd.DataFrame(
                    [{"Node": k, "Tokens": v} for k, v in tok_by_node.items()]
                ).set_index("Node")
                st.bar_chart(tok_df)

        st.caption("Click to expand individual LLM call details:")
        for i, c in enumerate(llm_calls):
            label = f"Call #{i+1} — {c.get('node_name', '')} / {c.get('agent_name', '')} ({c.get('latency_ms', 0):.0f}ms)"
            with st.expander(label):
                st.markdown("**System Prompt:**")
                st.code(c.get("system_prompt") or "(none)", language="text")
                st.markdown("**User Prompt:**")
                st.code(c.get("user_prompt") or "(none)", language="text")
                st.markdown("**Response:**")
                st.code(c.get("response_text") or "(none)", language="text")
                if c.get("error"):
                    st.error(f"Error: {c['error']}")
    else:
        st.caption("No LLM calls recorded (pipeline may have run in deterministic/CPU-only mode).")

    # ── Section F: Maintenance ──
    st.divider()
    col_purge, col_delete = st.columns(2)
    with col_purge:
        if st.button("🗑️ Purge old runs (keep latest 20)"):
            deleted = trace_db.purge_old_runs(keep_latest=20)
            st.success(f"Purged {deleted} old run(s).")
            st.rerun()
    with col_delete:
        if st.button("❌ Delete this run"):
            trace_db.delete_run(selected_id)
            st.success("Run deleted.")
            st.rerun()

    # ── Data lineage view ──
    st.divider()
    _render_data_lineage()


# ---------------------------------------------------------------------------
# Data lineage
# ---------------------------------------------------------------------------

def _render_data_lineage() -> None:
    """Show obligation -> mapping -> assessment -> risk chains."""
    classified = st.session_state.get("classified_obligations", [])
    if not classified:
        return

    st.subheader("🔗 Data Lineage Chains")
    st.caption("End-to-end traceability from obligation through mapping, coverage, and risk.")

    mappings = st.session_state.get("obligation_mappings", [])
    assessments = st.session_state.get("coverage_assessments", [])
    risks = st.session_state.get("scored_risks", [])

    mapping_lookup: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mapping_lookup[m.get("citation", "")].append(m)
    assessment_lookup: dict[str, list[dict]] = defaultdict(list)
    for a in assessments:
        assessment_lookup[a.get("citation", "")].append(a)
    risk_lookup: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risk_lookup[r.get("source_citation", "")].append(r)

    by_subpart: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        by_subpart[ob.get("subpart", "Unknown")].append(ob)

    for subpart in sorted(by_subpart.keys()):
        obs = by_subpart[subpart]
        with st.expander(f"📂 {subpart} ({len(obs)} obligations)"):
            for ob in obs:
                cit = ob.get("citation", "")
                cat = ob.get("obligation_category", "")
                crit = ob.get("criticality_tier", "")

                st.markdown(f"**{cit}** — {cat} ({crit})")

                ob_mappings = mapping_lookup.get(cit, [])
                if ob_mappings:
                    for m in ob_mappings:
                        st.markdown(f"  → APQC: {m.get('apqc_hierarchy_id', '')} — {m.get('apqc_process_name', '')}")

                ob_assessments = assessment_lookup.get(cit, [])
                if ob_assessments:
                    for a in ob_assessments:
                        coverage_status = a.get("overall_coverage", "")
                        ctrl = a.get("control_id", "None")
                        st.markdown(f"  → Coverage: {coverage_status} (Control: {ctrl})")

                ob_risks = risk_lookup.get(cit, [])
                if ob_risks:
                    for r in ob_risks:
                        rating = r.get("inherent_risk_rating", "")
                        st.markdown(f"  → Risk: {r.get('risk_id', '')} — {rating} — {r.get('risk_description', '')[:80]}")

                st.markdown("---")
