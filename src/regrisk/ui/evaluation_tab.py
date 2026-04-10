"""Tab 6: Evaluation — Run metrics, comparison, and cost/quality analysis.

Developer-facing tab for prompt engineers and pipeline developers. Answers:
"Is my pipeline getting better?  Which model gives the best cost/quality
tradeoff?  Where are the quality bottlenecks?"
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.tracing.db import TraceDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_trace_db() -> TraceDB:
    if "trace_db" not in st.session_state:
        from regrisk.core.constants import DEFAULT_TRACE_DB_PATH
        st.session_state["trace_db"] = TraceDB(DEFAULT_TRACE_DB_PATH)
    return st.session_state["trace_db"]


def _quality_color(score: float) -> str:
    if score >= 0.8:
        return "#2e7d32"
    if score >= 0.5:
        return "#f57f17"
    return "#c62828"


def _delta_arrow(val: float, higher_is_better: bool = True) -> str:
    if val > 0:
        color = "#2e7d32" if higher_is_better else "#c62828"
        return f'<span style="color:{color}">▲ {val:+.4f}</span>'
    if val < 0:
        color = "#c62828" if higher_is_better else "#2e7d32"
        return f'<span style="color:{color}">▼ {val:+.4f}</span>'
    return '<span style="color:#6c757d">— 0</span>'


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_run_history(trace_db: TraceDB) -> str | None:
    """Section 1 — Run History Table. Returns selected run_id or None."""
    st.subheader("Run History")

    metrics_list = trace_db.list_run_metrics(limit=50)
    if not metrics_list:
        st.info("No run metrics computed yet. Run the pipeline with tracing enabled, "
                "or click **Recompute All Metrics** below.")
        if st.button("Recompute All Metrics", key="eval_recompute"):
            with st.spinner("Recomputing…"):
                count = trace_db.recompute_all_metrics()
            st.success(f"Recomputed metrics for {count} runs.")
            st.rerun()
        return None

    rows = []
    for m in metrics_list:
        rows.append({
            "run_id": m["run_id"][:12],
            "regulation": (m.get("regulation_name") or "")[:30],
            "model": m.get("model", ""),
            "provider": m.get("provider", ""),
            "tokens": m.get("total_tokens", 0),
            "est_cost": f"${m.get('estimated_cost_usd', 0):.4f}",
            "pass_rate": f"{(m.get('overall_pass_rate', 0)) * 100:.1f}%",
            "quality": round(m.get("quality_score", 0), 3),
            "coverage": f"{(m.get('coverage_covered_pct', 0)) * 100:.1f}%",
            "llm_calls": m.get("total_llm_calls", 0),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Select a run for detail view
    run_ids = [m["run_id"] for m in metrics_list]
    labels = [f"{rid[:12]} — {m.get('regulation_name', '')[:25]} ({m.get('model', '')})"
              for rid, m in zip(run_ids, metrics_list)]
    selected_label = st.selectbox("Select run for detail view", labels,
                                  key="eval_run_select")
    if selected_label:
        idx = labels.index(selected_label)
        return run_ids[idx]
    return None


def _render_run_detail(trace_db: TraceDB, run_id: str) -> None:
    """Section 2 — Selected Run Detail."""
    st.subheader("Run Detail")

    m = trace_db.get_run_metrics(run_id)
    if not m:
        st.warning("No metrics found for this run.")
        return

    # Metric cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Tokens", f"{m.get('total_tokens', 0):,}")
    c2.metric("Est. Cost", f"${m.get('estimated_cost_usd', 0):.4f}")
    c3.metric("Quality Score", f"{m.get('quality_score', 0):.3f}")
    c4.metric("Pass Rate", f"{m.get('overall_pass_rate', 0) * 100:.1f}%")

    # Per-phase breakdown
    st.markdown("**Per-Phase Breakdown**")
    phases = [
        ("Classify", m.get("classify_total", 0), m.get("classify_passed", 0),
         m.get("classify_retries", 0), m.get("classify_pass_rate", 0)),
        ("Map", m.get("map_total", 0), m.get("map_passed", 0),
         m.get("map_retries", 0), m.get("map_pass_rate", 0)),
        ("Assess", m.get("assess_total", 0), m.get("assess_passed", 0),
         0, m.get("assess_pass_rate", 0)),
        ("Risk", m.get("risk_total", 0), m.get("risk_passed", 0),
         0, m.get("risk_pass_rate", 0)),
    ]
    phase_df = pd.DataFrame(phases, columns=["Phase", "Total", "Passed", "Retries", "Pass Rate"])
    phase_df["Pass Rate"] = phase_df["Pass Rate"].apply(lambda x: f"{x * 100:.1f}%")
    st.dataframe(phase_df, use_container_width=True, hide_index=True)

    # Extra metrics
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Mapping Confidence**")
        st.metric("Avg Confidence", f"{m.get('map_avg_confidence', 0):.3f}")

        st.markdown("**Coverage Distribution**")
        cov_data = {
            "Covered": m.get("coverage_covered_count", 0),
            "Partial": m.get("coverage_partial_count", 0),
            "Gap": m.get("coverage_gap_count", 0),
        }
        if any(cov_data.values()):
            cov_df = pd.DataFrame(list(cov_data.items()), columns=["Status", "Count"])
            st.bar_chart(cov_df, x="Status", y="Count")

    with col_b:
        st.markdown("**Classification Category Distribution**")
        cat_raw = m.get("classify_category_distribution", "{}")
        try:
            cat_dist = json.loads(cat_raw) if isinstance(cat_raw, str) else cat_raw
        except (json.JSONDecodeError, TypeError):
            cat_dist = {}
        if cat_dist:
            cat_df = pd.DataFrame(list(cat_dist.items()), columns=["Category", "Count"])
            st.bar_chart(cat_df, x="Category", y="Count")

        st.markdown("**Risk Distribution**")
        risk_raw = m.get("risk_distribution", "{}")
        try:
            risk_dist = json.loads(risk_raw) if isinstance(risk_raw, str) else risk_raw
        except (json.JSONDecodeError, TypeError):
            risk_dist = {}
        if risk_dist:
            risk_df = pd.DataFrame(list(risk_dist.items()), columns=["Rating", "Count"])
            st.bar_chart(risk_df, x="Rating", y="Count")


def _render_comparison(trace_db: TraceDB) -> None:
    """Section 3 — Run Comparison."""
    st.subheader("Run Comparison")

    metrics_list = trace_db.list_run_metrics(limit=50)
    if len(metrics_list) < 2:
        st.info("Need at least 2 runs with metrics to compare.")
        return

    run_ids = [m["run_id"] for m in metrics_list]
    labels = [f"{rid[:12]} — {m.get('regulation_name', '')[:25]} ({m.get('model', '')})"
              for rid, m in zip(run_ids, metrics_list)]

    col1, col2 = st.columns(2)
    with col1:
        label_a = st.selectbox("Run A", labels, index=0, key="eval_compare_a")
    with col2:
        default_b = min(1, len(labels) - 1)
        label_b = st.selectbox("Run B", labels, index=default_b, key="eval_compare_b")

    if st.button("Compare Runs", key="eval_compare_btn"):
        idx_a = labels.index(label_a)
        idx_b = labels.index(label_b)
        rid_a = run_ids[idx_a]
        rid_b = run_ids[idx_b]

        with st.spinner("Computing comparison…"):
            comp = trace_db.compare_runs(rid_a, rid_b)

        if not comp:
            st.error("Could not compute comparison.")
            return

        ma = trace_db.get_run_metrics(rid_a) or {}
        mb = trace_db.get_run_metrics(rid_b) or {}

        # Side-by-side metrics
        st.markdown("**Side-by-Side Metrics**")
        side_rows = []
        for label, key, fmt in [
            ("Total Tokens", "total_tokens", ","),
            ("Est. Cost (USD)", "estimated_cost_usd", ".4f"),
            ("Quality Score", "quality_score", ".3f"),
            ("Pass Rate", "overall_pass_rate", ".3f"),
            ("LLM Calls", "total_llm_calls", ","),
            ("Avg Latency (ms)", "avg_latency_per_call_ms", ".0f"),
        ]:
            va = ma.get(key, 0)
            vb = mb.get(key, 0)
            side_rows.append({
                "Metric": label,
                "Run A": f"{va:{fmt}}" if isinstance(va, (int, float)) else str(va),
                "Run B": f"{vb:{fmt}}" if isinstance(vb, (int, float)) else str(vb),
            })
        st.dataframe(pd.DataFrame(side_rows), use_container_width=True, hide_index=True)

        # Delta indicators
        st.markdown("**Deltas (B − A)**")
        delta_html = " &nbsp;|&nbsp; ".join([
            f"Quality: {_delta_arrow(comp.get('quality_delta', 0), True)}",
            f"Pass Rate: {_delta_arrow(comp.get('pass_rate_delta', 0), True)}",
            f"Tokens: {_delta_arrow(comp.get('token_delta', 0), False)}",
            f"Cost: {_delta_arrow(comp.get('cost_delta_usd', 0), False)}",
        ])
        st.markdown(delta_html, unsafe_allow_html=True)

        # Agreement metrics
        if comp.get("classify_agreement_rate") is not None:
            st.markdown("**Agreement Metrics** (same regulation)")
            ag_c1, ag_c2, ag_c3 = st.columns(3)
            ag_c1.metric("Classification Agreement",
                         f"{comp.get('classify_agreement_rate', 0) * 100:.1f}%")
            ag_c2.metric("Mapping Overlap",
                         f"{comp.get('map_overlap_rate', 0) * 100:.1f}%")
            ag_c3.metric("Coverage Agreement",
                         f"{comp.get('coverage_agreement_rate', 0) * 100:.1f}%")


def _render_cost_quality_scatter(trace_db: TraceDB) -> None:
    """Section 4 — Cost vs Quality Scatter."""
    st.subheader("Cost vs Quality")

    history = trace_db.get_cost_history(limit=50)
    if not history:
        st.info("No cost history data available.")
        return

    try:
        import matplotlib.pyplot as plt
        import matplotlib

        matplotlib.use("Agg")

        models = list({h.get("model", "unknown") for h in history})
        color_map = {}
        palette = ["#1E88E5", "#E53935", "#43A047", "#FDD835", "#7E57C2", "#FF7043"]
        for i, m in enumerate(models):
            color_map[m] = palette[i % len(palette)]

        fig, ax = plt.subplots(figsize=(8, 5))
        for h in history:
            model = h.get("model", "unknown")
            cost = h.get("estimated_cost_usd", 0)
            quality = h.get("quality_score", 0)
            ax.scatter(cost, quality, c=color_map.get(model, "#999"),
                       s=80, alpha=0.8, edgecolors="white", linewidths=0.5)

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=color_map[m], label=m, markersize=8)
            for m in models
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

        ax.set_xlabel("Estimated Cost (USD)")
        ax.set_ylabel("Quality Score")
        ax.set_title("Cost vs Quality — Upper-left is Best")
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    except ImportError:
        # Fallback: simple dataframe if matplotlib not available
        df = pd.DataFrame(history)
        st.scatter_chart(df, x="estimated_cost_usd", y="quality_score", color="model")


# ---------------------------------------------------------------------------
# Main tab renderer
# ---------------------------------------------------------------------------

def render_evaluation_tab() -> None:
    """Render the Evaluation tab (Tab 6)."""
    st.markdown(
        "*Developer tool — compare pipeline runs, track quality metrics, "
        "and analyze cost/quality tradeoffs.*"
    )

    trace_db = _get_trace_db()

    selected_run = _render_run_history(trace_db)
    st.divider()

    if selected_run:
        _render_run_detail(trace_db, selected_run)
        st.divider()

    _render_comparison(trace_db)
    st.divider()

    _render_cost_quality_scatter(trace_db)
