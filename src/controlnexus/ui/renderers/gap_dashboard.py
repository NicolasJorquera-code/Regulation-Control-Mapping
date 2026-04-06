"""GapReport visualization: metric cards, expandable gap lists."""

from __future__ import annotations

import streamlit as st

from controlnexus.core.state import GapReport
from controlnexus.ui.styles import score_color


def render_gap_dashboard(gap_report: GapReport) -> None:
    """Render the gap analysis dashboard with metric cards and gap details."""

    # -- Overall Score Banner --------------------------------------------------
    color = score_color(gap_report.overall_score)
    st.markdown(
        f"""
        <div class="carbon-tile" style="text-align:center;">
            <div class="metric-label">OVERALL CONTROL ECOSYSTEM SCORE</div>
            <div class="metric-value" style="color:{color};">{gap_report.overall_score}</div>
            <div style="color:#525252;font-size:0.875rem;">{gap_report.summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -- Dimension Cards -------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)

    _render_dimension_card(
        col1,
        "Regulatory Coverage",
        len(gap_report.regulatory_gaps),
        "tag-blue",
        "40%",
    )
    _render_dimension_card(
        col2,
        "Ecosystem Balance",
        len(gap_report.balance_gaps),
        "tag-teal",
        "25%",
    )
    _render_dimension_card(
        col3,
        "Frequency Coherence",
        len(gap_report.frequency_issues),
        "tag-purple",
        "15%",
    )
    _render_dimension_card(
        col4,
        "Evidence Sufficiency",
        len(gap_report.evidence_issues),
        "25%",
        "20%",
    )

    st.markdown("---")

    # -- Detailed Gap Lists ----------------------------------------------------
    _render_regulatory_gaps(gap_report.regulatory_gaps)
    _render_balance_gaps(gap_report.balance_gaps)
    _render_frequency_issues(gap_report.frequency_issues)
    _render_evidence_issues(gap_report.evidence_issues)

    # -- Accept Gaps for Remediation -------------------------------------------
    st.markdown("---")
    st.markdown("### Remediation")

    total_gaps = (
        len(gap_report.regulatory_gaps)
        + len(gap_report.balance_gaps)
        + len(gap_report.frequency_issues)
        + len(gap_report.evidence_issues)
    )

    if total_gaps == 0:
        st.success("No gaps identified. Your control ecosystem is healthy!")
        return

    st.markdown(f"**{total_gaps}** gaps identified across all dimensions.")

    if st.button("Accept All Gaps for Remediation", type="primary", width="stretch"):
        st.session_state["accepted_gaps"] = gap_report
        st.success("Gaps accepted. Scroll down to the Remediation section below to select gaps and generate controls.")


# -- Helpers -------------------------------------------------------------------


def _render_dimension_card(
    col: st.delta_generator.DeltaGenerator,
    title: str,
    gap_count: int,
    tag_class: str,
    weight: str,
) -> None:
    """Render a single dimension metric card."""
    status_cls = "status-success" if gap_count == 0 else "status-warning"

    col.markdown(
        f"""
        <div class="carbon-tile">
            <div class="metric-label">{title}</div>
            <div class="score-card">
                <div class="{status_cls}" style="font-size:1.5rem;font-weight:300;">{gap_count}</div>
                <div class="score-label">gap(s) found</div>
            </div>
            <div style="margin-top:0.5rem;">
                <span class="carbon-tag tag-gray">Weight: {weight}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_regulatory_gaps(gaps: list) -> None:
    """Render regulatory coverage gaps."""
    with st.expander(f"Regulatory Coverage Gaps ({len(gaps)})", expanded=len(gaps) > 0):
        if not gaps:
            st.success("All regulatory frameworks have adequate coverage.")
            return
        for gap in gaps:
            framework = gap.framework
            coverage = gap.current_coverage
            theme = gap.required_theme
            st.markdown(f"- **{framework}** ({theme}): Coverage {coverage:.0f}% — below 60% threshold")


def _render_balance_gaps(gaps: list) -> None:
    """Render ecosystem balance gaps."""
    with st.expander(f"Ecosystem Balance Issues ({len(gaps)})", expanded=len(gaps) > 0):
        if not gaps:
            st.success("Control type distribution is within expected ranges.")
            return
        for gap in gaps:
            ctrl_type = gap.control_type
            direction = gap.direction
            actual = gap.actual_pct
            expected = gap.expected_pct
            st.markdown(f"- **{ctrl_type}**: {direction}-represented (actual {actual:.1f}%, expected {expected:.1f}%)")


def _render_frequency_issues(issues: list) -> None:
    """Render frequency coherence issues."""
    with st.expander(f"Frequency Coherence Issues ({len(issues)})", expanded=len(issues) > 0):
        if not issues:
            st.success("All control frequencies are consistent with their types.")
            return
        for issue in issues:
            ctrl_id = issue.control_id
            actual = issue.actual_frequency
            expected = issue.expected_frequency
            st.markdown(f"- **{ctrl_id}**: Frequency is *{actual}*, expected *{expected}*")


def _render_evidence_issues(issues: list) -> None:
    """Render evidence sufficiency issues."""
    with st.expander(f"Evidence Sufficiency Issues ({len(issues)})", expanded=len(issues) > 0):
        if not issues:
            st.success("All controls have adequate evidence documentation.")
            return
        for issue in issues:
            ctrl_id = issue.control_id
            detail = issue.issue
            st.markdown(f"- **{ctrl_id}**: {detail if detail else 'Evidence documentation insufficient'}")
