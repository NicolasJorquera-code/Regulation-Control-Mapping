"""Tab: Risk Register — obligation cards with risk detail and risk dashboard.

Layout:
  - Filter bar (category, criticality, subpart, APQC section)
  - Scrollable obligation cards grouped by subpart (only obligations with risks)
    - Collapsed card: citation (row 1), category + relationship + risk badge (row 2),
      regulation title (row 3)
    - Expanded view: obligation text + full-width risks by severity tier
  - Risk dashboard: KPI cards + distribution charts + 4×4 heatmap
  - Export + checkpoint controls
"""

from __future__ import annotations

import io
from collections import Counter, defaultdict

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
    format_citation,
    render_checkpoint_load,
    render_checkpoint_save,
    render_filter_bar,
    render_obligation_text_only,
    render_risk_chip,
)
from regrisk.ui.session_keys import SK


# ---------------------------------------------------------------------------
# Shared styling constants (same as Coverage tab for consistency)
# ---------------------------------------------------------------------------

_RISK_BADGE_BG: dict[str, tuple[str, str]] = {
    "Critical": ("#c62828", "white"),
    "High": ("#ef6c00", "white"),
    "Medium": ("#f9a825", "#333"),
    "Low": ("#2e7d32", "white"),
}

_CATEGORY_BG: dict[str, str] = {
    "Controls": "#CCE5FF",
    "Documentation": "#D4EDDA",
    "Attestation": "#E2D5F1",
    "General Awareness": "#E2E3E5",
    "Not Assigned": "#F8D7DA",
}

_SEVERITY_CONFIG = [
    ("Critical", "🔴", True),
    ("High", "🟠", True),
    ("Medium", "🟡", False),
    ("Low", "🟢", False),
]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_risk_register_tab() -> None:
    """Render the Risk Register tab with obligation cards and risk dashboard."""
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

    st.header("Risk Register")

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
    risks = st.session_state.get(SK.SCORED_RISKS, [])
    if not risks:
        st.info("No risks have been scored yet.")
        return

    # ── Build per-obligation records (only those with risks) ──
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

    risks_by_cit: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risks_by_cit[r.get("source_citation", "")].append(r)

    # Only include obligations that have at least one risk
    results_records: list[dict] = []
    for cit in sorted(risks_by_cit.keys()):
        meta = ob_meta.get(cit, {})
        rec = dict(meta) if meta else {"citation": cit}
        rec.setdefault("citation", cit)
        rec.setdefault("subpart", "General")
        rec.setdefault("obligation_category", "Not Assigned")
        rec.setdefault("criticality_tier", "Low")
        # Collect unique top-level APQC sections
        sections = sorted({a.get("apqc_hierarchy_id", "").split(".")[0]
                           for a in assessments_by_cit.get(cit, [])
                           if a.get("apqc_hierarchy_id", "")},
                          key=lambda s: (int(s) if s.isdigit() else 999, s))
        rec["apqc_sections"] = ",".join(sections)
        # Add highest severity for filtering
        ob_risks = risks_by_cit[cit]
        sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        rec["highest_severity"] = min(
            (r.get("inherent_risk_rating", "Low") for r in ob_risks),
            key=lambda s: sev_order.get(s, 4),
        )
        results_records.append(rec)

    if not results_records:
        st.info("No obligations with risks to display.")
        _render_actions(gap_report)
        return

    # ── Filter bar ──
    df = pd.DataFrame(results_records)
    total_count = len(df)
    df_filtered = render_filter_bar(
        df, total_count, key_prefix="tab4_risk",
        show_category=True, show_criticality=True, show_subpart=True,
        show_coverage=False, show_apqc_section=True,
    )
    filtered_records = df_filtered.to_dict("records")

    if not filtered_records:
        st.info("No obligations match the current filters.")
        _render_risk_dashboard(risks)
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
                ob_risks = risks_by_cit.get(cit, [])

                with st.container(border=True):
                    # ── Three-row collapsed card header (with risk badge) ──
                    st.markdown(
                        _card_header_html(ob, len(ob_risks), ob_risks),
                        unsafe_allow_html=True,
                    )

                    with st.expander("View Details", expanded=False):
                        # Obligation text
                        render_obligation_text_only(ob)

                        st.markdown("")  # breathing room

                        # Risks sorted by severity (flat list, no sub-expanders)
                        _render_risks_flat(ob_risks)

    # ── Risk Dashboard (below the detail view) ──
    st.divider()
    _render_risk_dashboard(risks)

    # ── Actions ──
    _render_actions(gap_report)


# ---------------------------------------------------------------------------
# Card header HTML builder (with risk badge)
# ---------------------------------------------------------------------------

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

    # Row 3: Regulation title
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


# ---------------------------------------------------------------------------
# Risk grouping by severity tier
# ---------------------------------------------------------------------------

def _render_risks_flat(ob_risks: list[dict]) -> None:
    """Render risks as a flat list sorted by severity (Critical first)."""
    sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    sorted_risks = sorted(
        ob_risks,
        key=lambda r: sev_order.get(r.get("inherent_risk_rating", "Low"), 4),
    )
    for r in sorted_risks:
        render_risk_chip(r, show_inline=True)


# ---------------------------------------------------------------------------
# Risk dashboard (KPIs + distribution charts + heatmap)
# ---------------------------------------------------------------------------

def _render_risk_dashboard(risks: list[dict]) -> None:
    """Render risk-focused dashboard: KPIs, distribution bars, heatmap."""
    col_left, col_right = st.columns([3, 2])

    with col_left:
        # ── KPI Summary Strip ──
        critical_count = sum(1 for r in risks if r.get("inherent_risk_rating") == "Critical")
        high_count = sum(1 for r in risks if r.get("inherent_risk_rating") == "High")

        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(
                _kpi_card("Total Risks", len(risks), accent="warning"),
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                _kpi_card("Critical", critical_count, accent="negative", loud=True),
                unsafe_allow_html=True,
            )
        with k3:
            st.markdown(
                _kpi_card("High", high_count, accent="warning"),
                unsafe_allow_html=True,
            )

        # ── Distribution breakdowns (tabbed) ──
        tab_sev, tab_cat = st.tabs(["By Severity", "By Category"])

        with tab_sev:
            sev_counts = Counter(
                r.get("inherent_risk_rating", "Low") for r in risks
            )
            sev_order = [
                ("Critical", "#c62828", "white"),
                ("High", "#ef6c00", "white"),
                ("Medium", "#f9a825", "#333"),
                ("Low", "#2e7d32", "white"),
            ]
            _render_distribution_bars(sev_counts, sev_order, len(risks))

        with tab_cat:
            cat_counts = Counter(
                r.get("risk_category", "Other") for r in risks
            )
            cat_palette = [
                "#1565C0", "#6A1B9A", "#00838F",
                "#4E342E", "#37474F", "#AD1457",
            ]
            cat_order = [
                (cat, cat_palette[i % len(cat_palette)], "white")
                for i, (cat, _) in enumerate(
                    sorted(cat_counts.items(), key=lambda x: -x[1])
                )
            ]
            _render_distribution_bars(cat_counts, cat_order, len(risks))

    with col_right:
        st.markdown("**Risk Heatmap**")
        _render_risk_heatmap(risks)


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
        key="risk_tab_download",
    )

    st.divider()
    render_checkpoint_save(STAGE_ASSESSED, "tab4_risk")
    render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED, STAGE_ASSESS_PARTIAL], "tab4_risk")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
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


def _render_distribution_bars(
    counts: Counter,
    order: list[tuple[str, str, str]],
    total: int,
) -> None:
    """Render horizontal bar chart rows for a distribution."""
    if not counts or total == 0:
        st.caption("No data available.")
        return
    max_count = max(counts.values()) if counts else 1
    rows: list[str] = []
    for label, bg, fg in order:
        cnt = counts.get(label, 0)
        if cnt == 0:
            continue
        bar_pct = cnt / max_count * 100
        rows.append(
            '<div style="display:flex;align-items:center;margin-bottom:6px">'
            '<div style="width:130px;font-size:0.82rem;color:#333;'
            'text-align:right;padding-right:10px;white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis" title="{label}">'
            f'{label}</div>'
            '<div style="flex:1;background:#f0f2f6;border-radius:4px;'
            'overflow:hidden;height:26px">'
            f'<div style="width:{bar_pct:.1f}%;background:{bg};height:100%;'
            'border-radius:4px;display:flex;align-items:center;'
            'justify-content:flex-end;padding-right:8px;min-width:32px">'
            f'<span style="color:{fg};font-size:0.78rem;font-weight:600">'
            f'{cnt}</span></div></div></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _render_risk_heatmap(risks: list[dict]) -> None:
    """4×4 risk heatmap using matplotlib."""
    grid = np.zeros((4, 4), dtype=int)
    for r in risks:
        impact = r.get("impact_rating", 1)
        freq = r.get("frequency_rating", 1)
        if 1 <= impact <= 4 and 1 <= freq <= 4:
            grid[4 - impact][freq - 1] += 1

    fig, ax = plt.subplots(figsize=(5, 4.5))

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

    ax.imshow(color_grid, aspect="equal")

    for i in range(4):
        for j in range(4):
            count = grid[i][j]
            if count > 0:
                ax.text(
                    j, i, str(count), ha="center", va="center",
                    fontsize=16, fontweight="bold", color="black",
                )

    ax.set_xticks(range(4))
    ax.set_xticklabels(
        ["Remote\n(1)", "Unlikely\n(2)", "Possible\n(3)", "Likely\n(4)"],
        fontsize=9,
    )
    ax.set_yticks(range(4))
    ax.set_yticklabels(
        ["Severe\n(4)", "Major\n(3)", "Moderate\n(2)", "Minor\n(1)"],
        fontsize=9,
    )
    ax.set_xlabel("Frequency / Likelihood", fontsize=10)
    ax.set_ylabel("Impact", fontsize=10)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()

    st.pyplot(fig)
    plt.close(fig)
