"""Tab 4: Results — coverage summary, risk heatmap, gap analysis, risk register."""

from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from regrisk.export.excel_export import export_gap_report
from regrisk.ui.checkpoint import STAGE_ASSESSED, STAGE_ASSESS_PARTIAL, STAGE_CLASSIFIED, STAGE_MAPPED
from regrisk.ui.components import (
    build_partial_results,
    render_checkpoint_load,
    render_checkpoint_save,
    render_html_table,
)


def render_results_tab() -> None:
    """Render the Results tab."""
    gap_report = st.session_state.get("gap_report", {})

    if not gap_report:
        assessments = st.session_state.get("coverage_assessments", [])
        if assessments:
            classified = st.session_state.get("classified_obligations", [])
            build_partial_results(assessments, classified)
            gap_report = st.session_state.get("gap_report", {})

    if not gap_report:
        st.info("Run the full assessment pipeline first (Tabs 1–3).")
        return

    st.header("Results")

    if gap_report.get("_partial"):
        assessed = gap_report.get("_assessed_count", 0)
        total = gap_report.get("total_obligations", "?")
        st.warning(
            f"⚠️ **Partial results** — {assessed} of {total} obligations were assessed "
            f"before the pipeline was interrupted. Risk scoring was not completed. "
            f"Resume from the saved checkpoint to finish the remaining assessments."
        )

    # Coverage summary cards
    coverage = gap_report.get("coverage_summary", {})
    total_assessed = sum(coverage.values())
    col1, col2, col3 = st.columns(3)
    with col1:
        covered = coverage.get("Covered", 0)
        pct = f"{covered / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("✅ Covered", f"{covered} ({pct})")
    with col2:
        partial = coverage.get("Partially Covered", 0)
        pct = f"{partial / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("⚠️ Partially Covered", f"{partial} ({pct})")
    with col3:
        not_covered = coverage.get("Not Covered", 0)
        pct = f"{not_covered / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("❌ Not Covered", f"{not_covered} ({pct})")

    st.divider()

    # Risk heatmap
    risks = st.session_state.get("scored_risks", [])
    if risks:
        st.subheader("Risk Heatmap (Impact × Frequency)")
        _render_risk_heatmap(risks)

    st.divider()

    # Gap analysis table
    st.subheader("Gap Analysis")
    gaps = gap_report.get("gaps", [])
    if gaps:
        df_gaps = pd.DataFrame(gaps)
        display_cols = ["citation", "apqc_hierarchy_id", "control_id", "overall_coverage",
                        "semantic_match", "relationship_match"]
        display_cols = [c for c in display_cols if c in df_gaps.columns]
        render_html_table(df_gaps, display_cols, height=300)
    else:
        st.success("No gaps found — all obligations have coverage!")

    st.divider()

    # Risk register
    st.subheader("Risk Register")
    if risks:
        df_risks = pd.DataFrame(risks)
        display_cols = [
            "risk_id", "source_citation", "risk_description",
            "risk_category", "impact_rating", "frequency_rating",
            "inherent_risk_rating", "coverage_status",
        ]
        display_cols = [c for c in display_cols if c in df_risks.columns]
        render_html_table(df_risks, display_cols, height=300)
    else:
        st.info("No risks extracted.")

    st.divider()

    # Download full report
    buf = io.BytesIO()
    export_gap_report(
        gap_report,
        st.session_state.get("classified_obligations", []),
        st.session_state.get("obligation_mappings", []),
        st.session_state.get("coverage_assessments", []),
        risks,
        buf,
    )
    st.download_button(
        "📥 Download Full Report",
        data=buf.getvalue(),
        file_name="compliance_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    render_checkpoint_save(STAGE_ASSESSED, "tab4")
    render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED, STAGE_ASSESS_PARTIAL], "tab4")


def _render_risk_heatmap(risks: list[dict]) -> None:
    """4x4 risk heatmap using matplotlib."""
    grid = np.zeros((4, 4), dtype=int)
    for r in risks:
        impact = r.get("impact_rating", 1)
        freq = r.get("frequency_rating", 1)
        if 1 <= impact <= 4 and 1 <= freq <= 4:
            grid[4 - impact][freq - 1] += 1

    fig, ax = plt.subplots(figsize=(6, 5))

    color_grid = np.zeros((4, 4, 4))
    for i in range(4):
        for j in range(4):
            impact = 4 - i
            freq = j + 1
            score = impact * freq
            if score >= 12:
                color_grid[i, j, :3] = [0.8, 0.0, 0.0]
            elif score >= 8:
                color_grid[i, j, :3] = [1.0, 0.5, 0.0]
            elif score >= 4:
                color_grid[i, j, :3] = [1.0, 1.0, 0.0]
            else:
                color_grid[i, j, :3] = [0.2, 0.8, 0.2]
            color_grid[i, j, 3] = 0.6

    ax.imshow(color_grid, aspect="auto")

    for i in range(4):
        for j in range(4):
            count = grid[i][j]
            if count > 0:
                ax.text(j, i, str(count), ha="center", va="center",
                        fontsize=14, fontweight="bold", color="black")

    ax.set_xticks(range(4))
    ax.set_xticklabels(["Remote\n(1)", "Unlikely\n(2)", "Possible\n(3)", "Likely\n(4)"])
    ax.set_yticks(range(4))
    ax.set_yticklabels(["Severe\n(4)", "Major\n(3)", "Moderate\n(2)", "Minor\n(1)"])
    ax.set_xlabel("Frequency / Likelihood")
    ax.set_ylabel("Impact")
    ax.set_title("Risk Heatmap")

    st.pyplot(fig)
    plt.close(fig)
