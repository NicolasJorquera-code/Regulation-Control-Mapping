"""EvalReport visualization: 4-dimension scores, per-control breakdown."""

from __future__ import annotations

import streamlit as st

from controlnexus.evaluation.models import EvalReport
from controlnexus.ui.styles import score_color


def render_eval_dashboard(eval_report: EvalReport) -> None:
    """Render the evaluation dashboard with dimension scores and control details."""

    # -- Header ----------------------------------------------------------------
    st.markdown(
        f"""
        <div class="carbon-tile" style="text-align:center;">
            <div class="metric-label">EVALUATION REPORT</div>
            <div style="color:#525252;font-size:0.875rem;">
                Run: <strong>{eval_report.run_id or 'N/A'}</strong> |
                Controls evaluated: <strong>{eval_report.total_controls}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -- Four Dimension Cards --------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)

    _score_tile(col1, "Faithfulness", eval_report.faithfulness_avg, 4.0, "How well controls match their specs")
    _score_tile(col2, "Completeness", eval_report.completeness_avg, 6.0, "5W coverage and word count")
    _score_tile(col3, "Diversity", eval_report.diversity_score, 1.0, "Uniqueness across controls")
    _delta_tile(col4, "Gap Closure", eval_report.gap_closure_delta, "Score improvement vs original")

    # -- Near Duplicates -------------------------------------------------------
    st.markdown("---")
    if eval_report.near_duplicate_count > 0:
        st.warning(
            f"**{eval_report.near_duplicate_count}** near-duplicate pair(s) detected "
            f"(cosine > 0.92). Consider differentiation."
        )
    else:
        st.success("No near-duplicate controls detected.")

    # -- Per-Control Breakdown -------------------------------------------------
    st.markdown("### Per-Control Scores")
    if not eval_report.per_control_scores:
        st.info("No per-control scores available.")
        return

    for cs in eval_report.per_control_scores:
        faith_pct = cs.faithfulness / 4 * 100
        comp_pct = cs.completeness / 6 * 100
        faith_color = score_color(faith_pct)
        comp_color = score_color(comp_pct)

        with st.expander(f"{cs.control_id} — F:{cs.faithfulness}/4  C:{cs.completeness}/6"):
            c1, c2 = st.columns(2)
            c1.markdown(
                f'<span style="color:{faith_color};font-weight:600;">'
                f"Faithfulness: {cs.faithfulness}/4</span>",
                unsafe_allow_html=True,
            )
            c2.markdown(
                f'<span style="color:{comp_color};font-weight:600;">'
                f"Completeness: {cs.completeness}/6</span>",
                unsafe_allow_html=True,
            )
            if cs.failures:
                st.markdown("**Failures:** " + ", ".join(cs.failures))
            else:
                st.markdown("No failures.")


# -- Helpers -------------------------------------------------------------------


def _score_tile(
    col: st.delta_generator.DeltaGenerator,
    label: str,
    value: float,
    max_val: float,
    description: str,
) -> None:
    """Render a score tile for a dimension."""
    pct = (value / max_val * 100) if max_val else 0
    color = score_color(pct)
    col.markdown(
        f"""
        <div class="carbon-tile score-card">
            <div class="metric-label">{label}</div>
            <div class="score-value" style="color:{color};">{value:.2f}</div>
            <div class="score-label">/ {max_val:.0f}</div>
            <div style="color:#525252;font-size:0.75rem;margin-top:0.5rem;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _delta_tile(
    col: st.delta_generator.DeltaGenerator,
    label: str,
    delta: float,
    description: str,
) -> None:
    """Render a delta tile for gap closure."""
    if delta > 0:
        color = "#24a148"
        sign = "+"
    elif delta < 0:
        color = "#da1e28"
        sign = ""
    else:
        color = "#525252"
        sign = ""

    col.markdown(
        f"""
        <div class="carbon-tile score-card">
            <div class="metric-label">{label}</div>
            <div class="score-value" style="color:{color};">{sign}{delta:.1f}</div>
            <div class="score-label">points</div>
            <div style="color:#525252;font-size:0.75rem;margin-top:0.5rem;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
