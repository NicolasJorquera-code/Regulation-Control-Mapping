"""Tab 4: Results — executive dashboard with coverage metrics, risk heatmap,
gap analysis, and risk register.

Layout:
  - Four metric cards + stacked coverage bar
  - Two-column: risk heatmap (55%) | top gaps at-a-glance (45%)
  - Expandable gap analysis & risk register sections
  - Export + checkpoint controls
"""

from __future__ import annotations

import io
from collections import defaultdict

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
    coverage_indicator_html,
    format_citation,
    criticality_dot,
    render_checkpoint_load,
    render_checkpoint_save,
    risk_score_badge_html,
)
from regrisk.ui.session_keys import SK


def render_results_tab() -> None:
    """Render the Results tab as an executive dashboard."""
    gap_report = st.session_state.get(SK.GAP_REPORT, {})

    if not gap_report:
        assessments = st.session_state.get(SK.COVERAGE_ASSESSMENTS, [])
        if assessments:
            classified = st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, [])
            build_partial_results(assessments, classified)
            gap_report = st.session_state.get(SK.GAP_REPORT, {})

    if not gap_report:
        st.info("Run the full assessment pipeline first (Tabs 1–3).")
        return

    st.header("Results")

    # ── Partial results warning ──
    if gap_report.get("_partial"):
        assessed = gap_report.get("_assessed_count", 0)
        total = gap_report.get("total_obligations", "?")
        st.warning(
            f"⚠️ **Partial results** — {assessed} of {total} obligations were assessed "
            f"before the pipeline was interrupted. Risk scoring was not completed. "
            f"Resume from the saved checkpoint to finish the remaining assessments."
        )

    # ── Key metric cards ──
    coverage = gap_report.get("coverage_summary", {})
    total_assessed = sum(coverage.values())
    covered = coverage.get("Covered", 0)
    partial_cov = coverage.get("Partially Covered", 0)
    not_covered = coverage.get("Not Covered", 0)
    risks = st.session_state.get(SK.SCORED_RISKS, [])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Assessed", total_assessed)
    m2.metric("✅ Covered", f"{covered} ({_pct(covered, total_assessed)})")
    m3.metric("❌ Gaps", f"{partial_cov + not_covered} ({_pct(partial_cov + not_covered, total_assessed)})")
    m4.metric("Risks Identified", len(risks))

    # ── Stacked coverage bar ──
    if total_assessed > 0:
        pct_covered = covered / total_assessed * 100
        pct_partial = partial_cov / total_assessed * 100
        pct_gap = not_covered / total_assessed * 100
        bar_html = (
            '<div style="display:flex;height:24px;border-radius:6px;overflow:hidden;margin:0.5rem 0 1rem 0">'
            f'<div style="width:{pct_covered:.1f}%;background:#2e7d32" title="Covered {pct_covered:.0f}%"></div>'
            f'<div style="width:{pct_partial:.1f}%;background:#f57f17" title="Partial {pct_partial:.0f}%"></div>'
            f'<div style="width:{pct_gap:.1f}%;background:#c62828" title="Gap {pct_gap:.0f}%"></div>'
            '</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:0.8rem;color:#6c757d">'
            f'<span>✅ Covered {pct_covered:.0f}%</span>'
            f'<span>⚠️ Partial {pct_partial:.0f}%</span>'
            f'<span>❌ Gap {pct_gap:.0f}%</span>'
            f'</div>'
        )
        st.markdown(bar_html, unsafe_allow_html=True)

    st.divider()

    # ── Two-column: Heatmap + Top Gaps ──
    col_heatmap, col_gaps = st.columns([0.55, 0.45])

    with col_heatmap:
        if risks:
            st.subheader("Risk Heatmap")
            _render_risk_heatmap(risks)

            # Compact risk distribution
            risk_cats: dict[str, int] = defaultdict(int)
            for r in risks:
                risk_cats[r.get("risk_category", "Other")] += 1
            if risk_cats:
                st.caption("**Risk distribution**")
                for cat, cnt in sorted(risk_cats.items(), key=lambda x: -x[1]):
                    st.caption(f"  {cat}: {cnt}")
        else:
            st.info("No risks extracted — risk heatmap not available.")

    with col_gaps:
        gaps = gap_report.get("gaps", [])
        st.subheader("Top Gaps")
        if gaps:
            top_gaps = sorted(
                gaps,
                key=lambda g: (
                    0 if g.get("overall_coverage") == "Not Covered" else 1,
                    g.get("citation", ""),
                ),
            )[:8]
            for g in top_gaps:
                with st.container(border=True):
                    cit = format_citation(g.get("citation", ""))
                    cov = g.get("overall_coverage", "")
                    ctrl = g.get("control_id", "—")
                    apqc = g.get("apqc_process_name", g.get("apqc_hierarchy_id", ""))
                    st.markdown(
                        f"**`{cit}`** &nbsp; {coverage_indicator_html(cov)}",
                        unsafe_allow_html=True,
                    )
                    if apqc:
                        st.caption(f"APQC: {apqc}")
                    st.caption(f"Control: {ctrl}")
            if len(gaps) > 8:
                st.caption(f"*…and {len(gaps) - 8} more gaps below*")
        else:
            st.success("No gaps found — all obligations have coverage!")

    st.divider()

    # ── Expandable Gap Analysis ──
    with st.expander(f"Gap Analysis — {len(gaps)} gaps", expanded=False):
        if gaps:
            # Group: Not Covered first, then Partially Covered
            not_covered_gaps = [g for g in gaps if g.get("overall_coverage") == "Not Covered"]
            partial_gaps = [g for g in gaps if g.get("overall_coverage") == "Partially Covered"]

            for label, group in [("Not Covered", not_covered_gaps), ("Partially Covered", partial_gaps)]:
                if not group:
                    continue
                st.markdown(f"**{label}** ({len(group)})")
                for g in group:
                    cit = format_citation(g.get("citation", ""))
                    cov = g.get("overall_coverage", "")
                    ctrl = g.get("control_id", "—")
                    sem = g.get("semantic_match", "")
                    rel = g.get("relationship_match", "")
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            st.markdown(
                                f"**`{cit}`** &nbsp; {coverage_indicator_html(cov)}",
                                unsafe_allow_html=True,
                            )
                            apqc = g.get("apqc_process_name", g.get("apqc_hierarchy_id", ""))
                            if apqc:
                                st.caption(f"APQC: {apqc}")
                        with c2:
                            if sem:
                                st.caption(f"Semantic: {sem}")
                        with c3:
                            if rel:
                                st.caption(f"Relationship: {rel}")
                            st.caption(f"Control: {ctrl}")
                        # Expandable rationale
                        rationale = g.get("semantic_rationale", "") or g.get("relationship_rationale", "")
                        if rationale:
                            with st.expander("Rationale", expanded=False):
                                st.markdown(rationale)
        else:
            st.success("No gaps found!")

    # ── Expandable Risk Register ──
    with st.expander(f"Risk Register — {len(risks)} risks", expanded=False):
        if risks:
            # Group by risk_category
            by_cat: dict[str, list[dict]] = defaultdict(list)
            for r in risks:
                by_cat[r.get("risk_category", "Other")].append(r)

            for cat in sorted(by_cat.keys()):
                st.markdown(f"**{cat}** ({len(by_cat[cat])})")
                for r in by_cat[cat]:
                    rid = r.get("risk_id", "")
                    cit = format_citation(r.get("source_citation", ""))
                    desc = r.get("risk_description", "")
                    rating = r.get("inherent_risk_rating", "Low")
                    impact = r.get("impact_rating", 0)
                    freq = r.get("frequency_rating", 0)
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**{rid}** — `{cit}`")
                            st.caption(desc)
                        with c2:
                            score = impact * freq if impact and freq else None
                            st.markdown(
                                risk_score_badge_html(rating, score),
                                unsafe_allow_html=True,
                            )
                            if impact and freq:
                                st.caption(f"Impact: {impact} × Freq: {freq}")
                        # Expandable detail
                        sub_cat = r.get("sub_risk_category", "")
                        impact_rat = r.get("impact_rationale", "")
                        freq_rat = r.get("frequency_rationale", "")
                        extras = []
                        if sub_cat:
                            extras.append(f"**Sub-category:** {sub_cat}")
                        if impact_rat:
                            extras.append(f"**Impact rationale:** {impact_rat}")
                        if freq_rat:
                            extras.append(f"**Frequency rationale:** {freq_rat}")
                        if extras:
                            with st.expander("Detail", expanded=False):
                                st.markdown("\n\n".join(extras))
        else:
            st.info("No risks extracted.")

    st.divider()

    # ── Export ──
    buf = io.BytesIO()
    export_gap_report(
        gap_report,
        st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, []),
        st.session_state.get(SK.OBLIGATION_MAPPINGS, []),
        st.session_state.get(SK.COVERAGE_ASSESSMENTS, []),
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
    """Format a percentage string, returning 'N/A' when total is zero."""
    return f"{n / total * 100:.0f}%" if total > 0 else "N/A"


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
