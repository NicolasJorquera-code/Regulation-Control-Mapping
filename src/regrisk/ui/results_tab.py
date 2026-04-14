"""Tab: Coverage — obligation cards with coverage assessment detail and dashboard.

Layout:
  - Filter bar (category, criticality, subpart, coverage, APQC section)
  - Scrollable obligation cards grouped by subpart
    - Collapsed card: citation (row 1), category + relationship (row 2),
      regulation title (row 3)
    - Expanded view: obligation text + full-width coverage assessment chips
  - Executive dashboard: KPI cards + coverage progress bar
  - Export + checkpoint controls
"""

from __future__ import annotations

import io
from collections import defaultdict

import pandas as pd
import streamlit as st

from regrisk.export.excel_export import export_gap_report
from regrisk.ui.checkpoint import STAGE_ASSESSED, STAGE_ASSESS_PARTIAL, STAGE_CLASSIFIED, STAGE_MAPPED
from regrisk.ui.components import (
    build_partial_results,
    format_citation,
    render_checkpoint_load,
    render_checkpoint_save,
    render_coverage_chip,
    render_filter_bar,
    render_obligation_text_only,
)
from regrisk.ui.session_keys import SK


def render_coverage_tab() -> None:
    """Render the Coverage tab with obligation viewer and coverage dashboard."""
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

    st.header("Coverage")

    # ── Partial results warning ──
    if gap_report.get("_partial"):
        assessed = gap_report.get("_assessed_count", 0)
        total = gap_report.get("total_obligations", "?")
        st.warning(
            f"⚠️ **Partial results** — {assessed} of {total} obligations were assessed "
            f"before the pipeline was interrupted. Risk scoring was not completed. "
            f"Resume from the saved checkpoint to finish the remaining assessments."
        )

    # ── Gather data ──
    coverage = gap_report.get("coverage_summary", {})
    total_assessed = sum(coverage.values())
    covered = coverage.get("Covered", 0)
    partial_cov = coverage.get("Partially Covered", 0)
    not_covered = coverage.get("Not Covered", 0)
    gaps = partial_cov + not_covered

    # ── Build per-obligation records ──
    assessments = st.session_state.get(SK.COVERAGE_ASSESSMENTS, [])
    classified = st.session_state.get(SK.CLASSIFIED_OBLIGATIONS, [])

    ob_meta: dict[str, dict] = {}
    for ob in classified:
        cit = ob.get("citation", "")
        if cit:
            ob_meta[cit] = ob

    assessments_by_cit: dict[str, list[dict]] = defaultdict(list)
    for a in assessments:
        assessments_by_cit[a.get("citation", "")].append(a)

    assessed_citations = set(assessments_by_cit.keys())
    results_records: list[dict] = []
    for cit in sorted(assessed_citations):
        meta = ob_meta.get(cit, {})
        rec = dict(meta) if meta else {"citation": cit}
        rec.setdefault("citation", cit)
        rec.setdefault("subpart", "General")
        rec.setdefault("obligation_category", "Not Assigned")
        rec.setdefault("criticality_tier", "Low")
        ob_covs = [a.get("overall_coverage", "Not Covered") for a in assessments_by_cit[cit]]
        if "Not Covered" in ob_covs:
            rec["overall_coverage"] = "Not Covered"
        elif "Partially Covered" in ob_covs:
            rec["overall_coverage"] = "Partially Covered"
        else:
            rec["overall_coverage"] = "Covered"
        # Collect unique top-level APQC sections for this obligation
        sections = sorted({a.get("apqc_hierarchy_id", "").split(".")[0]
                           for a in assessments_by_cit[cit]
                           if a.get("apqc_hierarchy_id", "")},
                          key=lambda s: (int(s) if s.isdigit() else 999, s))
        rec["apqc_sections"] = ",".join(sections)
        results_records.append(rec)

    if not results_records:
        st.info("No assessed obligations to display.")
        _render_actions(gap_report)
        return

    # ── Filter bar ──
    df = pd.DataFrame(results_records)
    total_count = len(df)
    df_filtered = render_filter_bar(
        df, total_count, key_prefix="tab4_cov",
        show_category=True, show_criticality=True, show_subpart=True,
        show_coverage=True, show_apqc_section=True,
    )
    filtered_records = df_filtered.to_dict("records")

    if not filtered_records:
        st.info("No obligations match the current filters.")
        _render_coverage_dashboard(coverage, total_assessed, covered, partial_cov, not_covered, gaps)
        _render_actions(gap_report)
        return

    # ── Scrollable obligation cards ──
    with st.container(height=900):
        groups: dict[str, list[dict]] = defaultdict(list)
        for ob in filtered_records:
            subpart = ob.get("subpart", "General")
            groups[subpart].append(ob)

        for subpart in sorted(groups.keys()):
            st.subheader(subpart, divider="gray")
            for ob in groups[subpart]:
                cit = ob.get("citation", "")
                ob_assessments = assessments_by_cit.get(cit, [])

                with st.container(border=True):
                    # ── Three-row collapsed card header (no risk badge) ──
                    st.markdown(
                        _card_header_html(ob, 0, []),
                        unsafe_allow_html=True,
                    )

                    with st.expander("View Details", expanded=False):
                        # Obligation text
                        render_obligation_text_only(ob)

                        st.markdown("")  # breathing room

                        # ── Coverage summary bar ──
                        _render_coverage_summary(ob_assessments)

                        st.markdown("")  # breathing room

                        # Coverage assessment chips (control LEFT, breakdown RIGHT)
                        if ob_assessments:
                            for a in ob_assessments:
                                render_coverage_chip(a, show_inline=True)
                        else:
                            st.caption("No coverage assessment available.")

    # ── Executive Dashboard (below the detail view) ──
    st.divider()
    _render_coverage_dashboard(coverage, total_assessed, covered, partial_cov, not_covered, gaps)

    # ── Actions ──
    _render_actions(gap_report)


# ---------------------------------------------------------------------------
# Card header HTML builder
# ---------------------------------------------------------------------------

_RISK_BADGE_BG: dict[str, tuple[str, str]] = {
    "Critical": ("#c62828", "white"),
    "High": ("#ef6c00", "white"),
    "Medium": ("#f9a825", "#333"),
    "Low": ("#2e7d32", "white"),
}


def _card_header_html(ob: dict, n_risks: int, ob_risks: list[dict]) -> str:
    """Build HTML for the three-row collapsed card header.

    Row 1: Citation (dominant anchor)
    Row 2: Category badge · Relationship type · Risk count badge (colored)
    Row 3: Regulation title (plain text, wraps naturally)
    """
    from html import escape as _esc

    cit = ob.get("citation", "")
    cit_fmt = format_citation(cit)
    cat = ob.get("obligation_category", "")
    rel = ob.get("relationship_type", "")
    cat_bg = _CATEGORY_BG.get(cat, "#E2E3E5")

    # Row 1: Citation
    row1 = (
        f'<div style="font-size:1.15rem;font-weight:700;color:#1a1a1a;'
        f'margin-bottom:4px">{_esc(cit_fmt)}</div>'
    )

    # Row 2: Category + Relationship + Risk count
    meta_parts: list[str] = []
    if cat:
        meta_parts.append(
            f'<span class="category-pill" style="background:{cat_bg};font-size:0.78rem">'
            f'{_esc(cat)}</span>'
        )
    if rel and rel != "N/A":
        meta_parts.append(
            f'<span style="color:#6c757d;font-size:0.82rem">{_esc(rel)}</span>'
        )
    if n_risks > 0:
        highest_bg, highest_fg = _highest_severity_color(ob_risks)
        risk_label = f"{n_risks} risk{'s' if n_risks != 1 else ''}"
        meta_parts.append(
            f'<span style="display:inline-block;background:{highest_bg};color:{highest_fg};'
            f'border-radius:4px;padding:1px 8px;font-size:0.78rem;font-weight:600">'
            f'{risk_label}</span>'
        )
    row2 = (
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;'
        f'margin-bottom:4px">{"  ".join(meta_parts)}</div>'
        if meta_parts else ""
    )

    # Row 3: Regulation title (plain text, no breadcrumb arrows)
    title = ob.get("mandate_title", "") or ""
    row3 = ""
    if title and str(title).strip() and str(title).lower() not in ("nan", "none"):
        row3 = (
            f'<div style="color:#555;font-size:0.85rem;line-height:1.4">'
            f'{_esc(str(title).strip())}</div>'
        )

    return f'{row1}{row2}{row3}'


def _highest_severity_color(ob_risks: list[dict]) -> tuple[str, str]:
    """Return (bg, fg) for the highest-severity risk present."""
    severity_order = ["Critical", "High", "Medium", "Low"]
    present = {r.get("inherent_risk_rating", "Low") for r in ob_risks}
    for sev in severity_order:
        if sev in present:
            return _RISK_BADGE_BG.get(sev, ("#e0e0e0", "#333"))
    return ("#e0e0e0", "#333")


_CATEGORY_BG: dict[str, str] = {
    "Controls": "#CCE5FF",
    "Documentation": "#D4EDDA",
    "Attestation": "#E2D5F1",
    "General Awareness": "#E2E3E5",
    "Not Assigned": "#F8D7DA",
}


# ---------------------------------------------------------------------------
# Coverage summary for a single obligation
# ---------------------------------------------------------------------------

def _render_coverage_summary(ob_assessments: list[dict]) -> None:
    """Render a mini coverage bar for a single obligation's APQC assessments."""
    total_nodes = len(ob_assessments)
    if not total_nodes:
        return

    covered_count = sum(
        1 for a in ob_assessments if a.get("overall_coverage") == "Covered"
    )
    partial_count = sum(
        1 for a in ob_assessments if a.get("overall_coverage") == "Partially Covered"
    )
    gap_count = total_nodes - covered_count - partial_count

    pct_c = covered_count / total_nodes * 100
    pct_p = partial_count / total_nodes * 100
    pct_g = gap_count / total_nodes * 100
    bar_html = (
        f'<div style="font-size:0.85rem;font-weight:600;margin-bottom:4px">'
        f'{covered_count} of {total_nodes} APQC nodes covered</div>'
        f'<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;'
        f'margin-bottom:6px">'
        f'<div style="width:{pct_c:.0f}%;background:#2e7d32"></div>'
        f'<div style="width:{pct_p:.0f}%;background:#f57f17"></div>'
        f'<div style="width:{pct_g:.0f}%;background:#c62828"></div>'
        f'</div>'
    )
    st.markdown(bar_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Coverage-only executive dashboard
# ---------------------------------------------------------------------------

def _render_coverage_dashboard(
    coverage: dict,
    total_assessed: int,
    covered: int,
    partial_cov: int,
    not_covered: int,
    gaps: int,
) -> None:
    """Render the coverage dashboard: KPIs + coverage progress bar."""
    # ── KPI Summary Strip ──
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(
            _kpi_card("Total Assessed", total_assessed),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _kpi_card("Covered", covered, _pct(covered, total_assessed), accent="positive"),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _kpi_card("Gaps", gaps, _pct(gaps, total_assessed), accent="negative", loud=True),
            unsafe_allow_html=True,
        )

    # ── Compact coverage progress bar ──
    if total_assessed > 0:
        pct_covered = covered / total_assessed * 100
        pct_partial = partial_cov / total_assessed * 100
        pct_gap = not_covered / total_assessed * 100
        bar_html = (
            '<div style="display:flex;height:10px;border-radius:5px;overflow:hidden;'
            'margin:0.25rem 0 0.5rem 0">'
            f'<div style="width:{pct_covered:.1f}%;background:#2e7d32"'
            f' title="Covered {pct_covered:.0f}%"></div>'
            f'<div style="width:{pct_partial:.1f}%;background:#f57f17"'
            f' title="Partial {pct_partial:.0f}%"></div>'
            f'<div style="width:{pct_gap:.1f}%;background:#c62828"'
            f' title="Gap {pct_gap:.0f}%"></div>'
            '</div>'
            '<div style="display:flex;justify-content:space-between;'
            'font-size:0.75rem;color:#6c757d">'
            f'<span>\u2705 Covered {pct_covered:.0f}%</span>'
            f'<span>\u26a0\ufe0f Partial {pct_partial:.0f}%</span>'
            f'<span>\u274c Gap {pct_gap:.0f}%</span>'
            '</div>'
        )
        st.markdown(bar_html, unsafe_allow_html=True)


def _render_actions(gap_report: dict) -> None:
    """Render export, checkpoint save/load controls."""
    st.divider()

    risks = st.session_state.get(SK.SCORED_RISKS, [])
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
    render_checkpoint_save(STAGE_ASSESSED, "tab4_cov")
    render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED, STAGE_ASSESS_PARTIAL], "tab4_cov")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
    """Format a percentage string, returning 'N/A' when total is zero."""
    return f"{n / total * 100:.0f}%" if total > 0 else "N/A"


def _kpi_card(
    label: str,
    value: int,
    pct_str: str | None = None,
    *,
    accent: str = "neutral",
    loud: bool = False,
) -> str:
    """Return HTML for a single KPI metric card."""
    styles = {
        "neutral":  ("#f0f2f6", "#333",    "#e0e0e0"),
        "positive": ("#e8f5e9", "#2e7d32", "#a5d6a7"),
        "negative": ("#fbe9e7", "#c62828", "#ef9a9a"),
        "warning":  ("#fff3e0", "#ef6c00", "#ffcc80"),
    }
    bg, fg, border = styles.get(accent, styles["neutral"])
    font_size = "1.8rem" if loud else "1.5rem"
    border_width = "3px" if loud else "1px"
    pct_html = (
        f'<div style="font-size:0.8rem;color:#6c757d">{pct_str}</div>'
        if pct_str
        else ""
    )
    return (
        f'<div style="background:{bg};border:{border_width} solid {border};'
        f'border-radius:8px;padding:0.75rem 0.5rem;text-align:center">'
        f'<div style="font-size:0.75rem;color:#6c757d;text-transform:uppercase;'
        f'letter-spacing:0.05em">{label}</div>'
        f'<div style="font-size:{font_size};font-weight:700;color:{fg};'
        f'line-height:1.3">{value}</div>'
        f'{pct_html}'
        f'</div>'
    )
