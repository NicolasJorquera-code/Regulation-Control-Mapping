"""Shared UI components — HTML table renderer, color coding, checkpoint helpers."""

from __future__ import annotations

import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.export.formatting import display_col_name as _display_col_name
from regrisk.ui.checkpoint import (
    STAGE_CLASSIFIED,
    STAGE_MAPPED,
    STAGE_ASSESSED,
    STAGE_ASSESS_PARTIAL,
    save_checkpoint,
    load_checkpoint,
    list_checkpoints,
    stage_label,
    stage_keys,
)


# ---------------------------------------------------------------------------
# Color coding for obligation categories
# ---------------------------------------------------------------------------

CATEGORY_COLORS: dict[str, str] = {
    "Controls": "background-color: #CCE5FF",
    "Documentation": "background-color: #D4EDDA",
    "Attestation": "background-color: #E2D5F1",
    "General Awareness": "background-color: #E2E3E5",
    "Not Assigned": "background-color: #F8D7DA",
}

CATEGORY_BG: dict[str, str] = {
    "Controls": "#CCE5FF",
    "Documentation": "#D4EDDA",
    "Attestation": "#E2D5F1",
    "General Awareness": "#E2E3E5",
    "Not Assigned": "#F8D7DA",
}


def color_category(val: str) -> str:
    """Return CSS style string for a category value."""
    return CATEGORY_COLORS.get(val, "")


# ---------------------------------------------------------------------------
# HTML table renderer
# ---------------------------------------------------------------------------

def render_html_table(
    df: pd.DataFrame,
    columns: list[str],
    height: int = 400,
    color_col: str | None = None,
    color_map: dict[str, str] | None = None,
) -> None:
    """Render a DataFrame as a scrollable HTML table with text wrapping."""
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return

    rows_html: list[str] = []
    for _, row in df[cols].iterrows():
        cells: list[str] = []
        for c in cols:
            val = row[c]
            cell_val = "" if pd.isna(val) else str(val)
            style = ""
            if color_col and c == color_col and color_map:
                bg = color_map.get(cell_val, "")
                if bg:
                    style = f' style="background-color: {bg}"'
            cells.append(f"<td{style}>{cell_val}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header = "".join(f"<th>{_display_col_name(c)}</th>" for c in cols)
    html = (
        f'<div class="wrapped-table-container" style="max-height:{height}px">'
        f'<table class="wrapped-table">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        f"</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def save_uploaded_file(uploaded_file: Any) -> str:
    """Save a Streamlit UploadedFile to a temporary path and return the path."""
    import tempfile

    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


# ---------------------------------------------------------------------------
# Checkpoint UI helpers
# ---------------------------------------------------------------------------

def render_checkpoint_save(stage: str, key_prefix: str) -> None:
    """Render a 'Save checkpoint' + download button for the current stage."""
    data = {k: st.session_state.get(k) for k in stage_keys(stage) if k in st.session_state}
    if not data:
        return
    with st.expander(f"💾 Save / Download {stage_label(stage)} Checkpoint"):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save to disk", key=f"{key_prefix}_save"):
                path = save_checkpoint(stage, data)
                st.success(f"Saved: `{path.name}`")
        with col2:
            payload = {"_meta": {"stage": stage, "stage_label": stage_label(stage),
                                  "regulation_name": data.get("regulation_name", ""),
                                  "keys_saved": list(data.keys())}, **data}
            blob = json.dumps(payload, default=str, indent=2).encode("utf-8")
            st.download_button(
                "📥 Download checkpoint",
                data=blob,
                file_name=f"{stage}_checkpoint.json",
                mime="application/json",
                key=f"{key_prefix}_dl",
            )


def render_checkpoint_load(allowed_stages: list[str], key_prefix: str) -> None:
    """Render a checkpoint loader (file upload + saved-on-disk picker)."""
    with st.expander("💾 Resume from Checkpoint"):
        tab_upload, tab_disk = st.tabs(["Upload File", "Saved on Disk"])

        with tab_upload:
            uploaded = st.file_uploader(
                "Upload a checkpoint JSON",
                type=["json"],
                key=f"{key_prefix}_upload",
            )
            if uploaded:
                data = json.loads(uploaded.getvalue())
                meta = data.get("_meta", {})
                ckpt_stage = meta.get("stage", "")
                if ckpt_stage not in allowed_stages:
                    st.error(f"This checkpoint is for stage '{meta.get('stage_label', ckpt_stage)}' — "
                             f"expected one of: {', '.join(stage_label(s) for s in allowed_stages)}")
                else:
                    apply_checkpoint(data)

        with tab_disk:
            checkpoints = list_checkpoints()
            relevant = [c for c in checkpoints if c["stage"] in allowed_stages]
            if not relevant:
                st.info("No saved checkpoints found.")
            else:
                options = {
                    f"{c['stage_label']} — {c['regulation_name']} ({c['timestamp']})": c
                    for c in relevant
                }
                choice = st.selectbox("Select checkpoint", options=list(options.keys()),
                                      key=f"{key_prefix}_pick")
                if choice and st.button("Load", key=f"{key_prefix}_load"):
                    data = load_checkpoint(options[choice]["path"])
                    apply_checkpoint(data)


def apply_checkpoint(data: dict[str, Any]) -> None:
    """Write checkpoint data into session_state and rerun."""
    meta = data.pop("_meta", {})
    for k, v in data.items():
        st.session_state[k] = v
    st.success(f"Restored **{meta.get('stage_label', '?')}** checkpoint "
               f"for *{meta.get('regulation_name', '?')}*")
    st.rerun()


# ---------------------------------------------------------------------------
# Pipeline status helpers
# ---------------------------------------------------------------------------

def pipeline_phase() -> str:
    """Return the furthest pipeline phase completed in session_state."""
    if st.session_state.get("gap_report"):
        return STAGE_ASSESSED
    if st.session_state.get("obligation_mappings"):
        return STAGE_MAPPED
    if st.session_state.get("classified_obligations"):
        return STAGE_CLASSIFIED
    return ""


def phase_badge(label: str, complete: bool) -> str:
    """Return a status badge string for a pipeline phase."""
    return f"✅ {label}" if complete else f"⬜ {label}"


def build_partial_results(assessments: list[dict], classified: list[dict]) -> None:
    """Populate session state with a partial gap_report from completed assessments."""
    coverage_summary: dict[str, int] = defaultdict(int)
    for a in assessments:
        status = a.get("overall_coverage", "Not Covered")
        coverage_summary[status] += 1

    gaps = [a for a in assessments if a.get("overall_coverage") in ("Not Covered", "Partially Covered")]

    classified_counts: dict[str, int] = defaultdict(int)
    for ob in classified:
        cat = ob.get("obligation_category", "Not Assigned")
        classified_counts[cat] += 1

    mappings = st.session_state.get("obligation_mappings", [])

    st.session_state["gap_report"] = {
        "regulation_name": st.session_state.get("regulation_name", ""),
        "total_obligations": len(classified),
        "classified_counts": dict(classified_counts),
        "mapped_obligation_count": len(set(m.get("citation") for m in mappings)),
        "coverage_summary": dict(coverage_summary),
        "gaps": gaps,
        "_partial": True,
        "_assessed_count": len(assessments),
    }
    st.session_state["scored_risks"] = []
    st.session_state["compliance_matrix"] = {"rows": []}
    st.session_state["risk_register"] = {}


# ---------------------------------------------------------------------------
# New components — progressive-disclosure UI
# ---------------------------------------------------------------------------

_CRITICALITY_DOT: dict[str, str] = {
    "High": "🔴",
    "Medium": "🟡",
    "Low": "⚪",
}

_RISK_BADGE_CSS: dict[str, str] = {
    "Critical": "risk-critical",
    "High": "risk-high",
    "Medium": "risk-medium",
    "Low": "risk-low",
}

_COVERAGE_HTML: dict[str, str] = {
    "Covered": '<span class="coverage-covered">✅ Covered</span>',
    "Partially Covered": '<span class="coverage-partial">⚠️ Partial</span>',
    "Not Covered": '<span class="coverage-gap">❌ Gap</span>',
}


def format_citation(citation: str) -> str:
    """Abbreviate a CFR citation for badge display. E.g. '12 CFR 252.34(a)(1)(i)' → '§252.34(a)(1)(i)'."""
    if not citation:
        return ""
    # Strip the '12 CFR ' prefix if present
    c = citation.strip()
    for prefix in ("12 CFR ", "17 CFR "):
        if c.startswith(prefix):
            c = "§" + c[len(prefix):]
            break
    return c


def criticality_dot(tier: str) -> str:
    """Return emoji dot for a criticality tier."""
    return _CRITICALITY_DOT.get(tier, "⚪")


def category_pill_html(category: str) -> str:
    """Return an HTML pill badge for an obligation category."""
    bg = CATEGORY_BG.get(category, "#E2E3E5")
    from html import escape
    return f'<span class="category-pill" style="background:{bg}">{escape(category)}</span>'


def citation_badge_html(citation: str) -> str:
    """Return an HTML monospace badge for a citation."""
    from html import escape
    short = format_citation(citation)
    return f'<span class="citation-badge">{escape(short)}</span>'


def coverage_indicator_html(status: str) -> str:
    """Return HTML for a coverage status indicator."""
    return _COVERAGE_HTML.get(status, f'<span>{status}</span>')


def risk_score_badge_html(rating: str, score: int | None = None) -> str:
    """Return HTML for a risk rating badge with optional numeric score."""
    from html import escape
    css_class = _RISK_BADGE_CSS.get(rating, "risk-low")
    score_text = f" ({score})" if score is not None else ""
    return f'<span class="{css_class}">{escape(rating)}{score_text}</span>'


def format_confidence(conf: float) -> str:
    """Return colored HTML for a confidence value."""
    if conf >= 0.8:
        css = "conf-high"
    elif conf >= 0.5:
        css = "conf-medium"
    else:
        css = "conf-low"
    return f'<span class="{css}">{conf:.2f}</span>'


def render_obligation_card(ob: dict, idx: int, selected_idx: int, key_prefix: str = "ob") -> bool:
    """Render a collapsed obligation card. Returns True if this card was clicked."""
    citation = format_citation(ob.get("citation", ""))
    category = ob.get("obligation_category", "")
    crit = ob.get("criticality_tier", "")
    abstract = ob.get("abstract", "") or ""
    truncated = (abstract[:80] + "…") if len(abstract) > 80 else abstract

    is_selected = idx == selected_idx

    border_style = "border-left: 3px solid #1E88E5;" if is_selected else ""
    bg_style = "background-color: #f8f9ff;" if is_selected else ""

    cat_bg = CATEGORY_BG.get(category, "#E2E3E5")
    crit_dot = criticality_dot(crit)

    with st.container(border=True):
        clicked = st.button(
            f"**`{citation}`**  {crit_dot}  {category}",
            key=f"{key_prefix}_card_{idx}",
            use_container_width=True,
        )
        st.caption(truncated)
    return clicked


def render_obligation_detail(ob: dict) -> None:
    """Render the full detail view for a selected obligation."""
    citation = ob.get("citation", "")
    category = ob.get("obligation_category", "")
    crit = ob.get("criticality_tier", "")
    crit_dot = criticality_dot(crit)

    st.markdown(f"### `{format_citation(citation)}`")
    cat_bg = CATEGORY_BG.get(category, "#E2E3E5")
    st.markdown(
        f'{crit_dot} **{crit}** &nbsp; '
        f'<span class="category-pill" style="background:{cat_bg}">{category}</span>',
        unsafe_allow_html=True,
    )

    # Subpart / section breadcrumb
    parts = []
    if ob.get("subpart"):
        parts.append(ob["subpart"])
    if ob.get("section_citation"):
        parts.append(ob["section_citation"])
    if ob.get("section_title"):
        parts.append(ob["section_title"])
    if parts:
        st.caption(" → ".join(parts))

    # Regulatory text
    text = ob.get("text", "") or ob.get("abstract", "")
    if text:
        st.markdown("**Regulatory Text**")
        st.markdown(
            f'<div class="obligation-detail">{text}</div>',
            unsafe_allow_html=True,
        )

    # Abstract (if different from text)
    abstract = ob.get("abstract", "")
    full_text = ob.get("text", "")
    if abstract and full_text and abstract != full_text:
        st.markdown("**Abstract**")
        st.info(abstract)

    # Classification details
    st.markdown("**Classification**")
    rel_type = ob.get("relationship_type", "N/A")
    rationale = ob.get("classification_rationale", "")
    st.markdown(f"**Category:** {category} &nbsp;|&nbsp; **Relationship:** {rel_type}")
    if rationale:
        st.markdown(f"*{rationale}*")


def render_mapping_chip(mapping: dict) -> None:
    """Render a single APQC mapping as a compact chip inside a container."""
    process_name = mapping.get("apqc_process_name", "")
    hierarchy_id = mapping.get("apqc_hierarchy_id", "")
    rel_type = mapping.get("relationship_type", "")
    confidence = mapping.get("confidence", 0)
    detail = mapping.get("relationship_detail", "")

    with st.container(border=True):
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(f"**{process_name}**")
            st.caption(f"`{hierarchy_id}` · {rel_type}")
        with cols[1]:
            conf_color = "#2e7d32" if confidence >= 0.8 else "#f57f17" if confidence >= 0.5 else "#c62828"
            st.markdown(f"**<span style='color:{conf_color}'>{confidence:.2f}</span>**",
                        unsafe_allow_html=True)
        with cols[2]:
            pass
        if detail:
            st.caption(detail)


def render_coverage_indicator(status: str) -> None:
    """Render a coverage status indicator using st.markdown."""
    st.markdown(coverage_indicator_html(status), unsafe_allow_html=True)


def render_risk_score_cell(rating: str, impact: int = 0, frequency: int = 0) -> None:
    """Render a risk score badge with impact × frequency detail."""
    score = impact * frequency
    st.markdown(risk_score_badge_html(rating, score if score else None), unsafe_allow_html=True)
    if impact and frequency:
        st.caption(f"Impact: {impact} × Freq: {frequency}")


def render_filter_bar(
    df: pd.DataFrame,
    total_count: int,
    key_prefix: str,
    show_category: bool = True,
    show_criticality: bool = True,
    show_subpart: bool = True,
    show_coverage: bool = False,
) -> pd.DataFrame:
    """Render a horizontal filter bar and return the filtered DataFrame."""
    num_cols = sum([show_category, show_criticality, show_subpart, show_coverage])
    if num_cols == 0:
        return df

    cols = st.columns(num_cols + 1)  # Extra column for count display
    col_idx = 0

    filtered = df.copy()

    if show_category and "obligation_category" in df.columns:
        with cols[col_idx]:
            options = sorted(df["obligation_category"].unique())
            selected = st.multiselect("Category", options=options, key=f"{key_prefix}_cat_f")
            if selected:
                filtered = filtered[filtered["obligation_category"].isin(selected)]
        col_idx += 1

    if show_criticality and "criticality_tier" in df.columns:
        with cols[col_idx]:
            selected = st.multiselect("Criticality", options=["High", "Medium", "Low"],
                                      key=f"{key_prefix}_crit_f")
            if selected:
                filtered = filtered[filtered["criticality_tier"].isin(selected)]
        col_idx += 1

    if show_subpart and "subpart" in df.columns:
        with cols[col_idx]:
            options = sorted(df["subpart"].dropna().unique())
            selected = st.multiselect("Subpart", options=options, key=f"{key_prefix}_sub_f")
            if selected:
                filtered = filtered[filtered["subpart"].isin(selected)]
        col_idx += 1

    if show_coverage and "overall_coverage" in df.columns:
        with cols[col_idx]:
            options = sorted(df["overall_coverage"].unique())
            selected = st.multiselect("Coverage", options=options, key=f"{key_prefix}_cov_f")
            if selected:
                filtered = filtered[filtered["overall_coverage"].isin(selected)]
        col_idx += 1

    with cols[col_idx]:
        st.metric("Showing", f"{len(filtered)} of {total_count}")

    return filtered
