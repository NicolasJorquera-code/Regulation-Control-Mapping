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

# ---------------------------------------------------------------------------
# Plain-English explanations for classification labels
# ---------------------------------------------------------------------------

CATEGORY_EXPLANATIONS: dict[str, str] = {
    "Attestation": "Requires senior management sign-off, certification, or board approval.",
    "Documentation": "Requires maintenance of written policies, procedures, plans, or records.",
    "Controls": "Requires evidence of operating processes, controls, systems, or monitoring.",
    "General Awareness": "Principle-based guidance — no direct implementation requirement.",
    "Not Assigned": "General requirement, not directly actionable.",
}

RELATIONSHIP_EXPLANATIONS: dict[str, str] = {
    "Requires Existence": "A specific function, committee, role, or process must exist.",
    "Constrains Execution": "Requirements on HOW a process must be performed.",
    "Requires Evidence": "Documentation, reports, or records must be produced and maintained.",
    "Sets Frequency": "An activity must be performed at a specified interval.",
    "N/A": "Not applicable — this obligation is informational.",
}

CRITICALITY_EXPLANATIONS: dict[str, str] = {
    "High": "Violation would likely trigger enforcement action, consent order, or MRA.",
    "Medium": "Violation would result in supervisory criticism or examination findings.",
    "Low": "Violation would be noted as an observation or best-practice gap.",
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
                    c.get("display", c["filename"]): c
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


def render_obligation_card(
    ob: dict,
    idx: int,
    selected_idx: int,
    key_prefix: str = "ob",
    extra_label: str = "",
) -> bool:
    """Render a collapsed obligation card. Returns True if this card was clicked."""
    citation = format_citation(ob.get("citation", ""))
    category = ob.get("obligation_category", "")
    crit = ob.get("criticality_tier", "")
    rel_type = ob.get("relationship_type", "")
    crit_dot = criticality_dot(crit)

    # Use abstract for preview (short summary); fall back to text
    preview_src = ob.get("abstract", "") or ob.get("text", "") or ""
    truncated = (preview_src[:120] + "…") if len(preview_src) > 120 else preview_src

    cat_bg = CATEGORY_BG.get(category, "#E2E3E5")

    with st.container(border=True):
        clicked = st.button(
            f"**`{citation}`** &nbsp; {crit_dot}",
            key=f"{key_prefix}_card_{idx}",
            use_container_width=True,
        )
        secondary = f'<span class="category-pill" style="background:{cat_bg};font-size:0.75rem">{category}</span>'
        if rel_type and rel_type != "N/A":
            secondary += f"  ·  {rel_type}"
        if extra_label:
            secondary += f"  ·  {extra_label}"
        st.markdown(secondary, unsafe_allow_html=True)
        if truncated:
            st.caption(truncated)
    return clicked


def render_obligation_detail(ob: dict) -> None:
    """Render the full detail view for a selected obligation."""
    from html import escape as _esc

    citation = ob.get("citation", "")
    category = ob.get("obligation_category", "")
    crit = ob.get("criticality_tier", "")
    crit_dot = criticality_dot(crit)
    rel_type = ob.get("relationship_type", "N/A")
    cat_bg = CATEGORY_BG.get(category, "#E2E3E5")

    # ── Header block ──
    st.markdown(
        f'<span style="font-family:monospace;font-size:1.5rem;font-weight:700">'
        f'§{_esc(citation.replace("12 CFR ", ""))}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'{crit_dot} **{crit}** &nbsp;&nbsp; '
        f'<span class="category-pill" style="background:{cat_bg}">{_esc(category)}</span>',
        unsafe_allow_html=True,
    )

    # Breadcrumb from title hierarchy
    breadcrumb_parts: list[str] = []
    for fld in ("title_level_2", "title_level_3", "title_level_4", "title_level_5"):
        val = ob.get(fld, "")
        if val and str(val).strip() and str(val).lower() not in ("nan", "none"):
            breadcrumb_parts.append(str(val).strip())
    if not breadcrumb_parts:
        # Fall back to subpart/section
        for fld_val in (ob.get("subpart", ""), ob.get("section_citation", ""), ob.get("section_title", "")):
            if fld_val and str(fld_val).strip():
                breadcrumb_parts.append(str(fld_val).strip())
    if breadcrumb_parts:
        st.caption(" → ".join(breadcrumb_parts))

    # ── Primary content — Obligation Text ──
    st.markdown("#### Obligation Text")
    reg_text = ob.get("text", "") or ""
    if reg_text and str(reg_text).strip() and str(reg_text).lower() not in ("nan", "none"):
        text_html = _esc(str(reg_text).strip())
        st.markdown(
            f'<div class="obligation-detail">{text_html}</div>',
            unsafe_allow_html=True,
        )
    else:
        abstract = ob.get("abstract", "") or ""
        if abstract and str(abstract).lower() not in ("nan", "none"):
            st.markdown(
                f'<div class="obligation-detail">{_esc(str(abstract))}</div>',
                unsafe_allow_html=True,
            )
            st.caption("_(Full regulatory text not available — showing abstract)_")
        else:
            st.info("No regulatory text available for this obligation.")

    # Show abstract as a callout if text was displayed (abstract is the short summary)
    abstract_val = ob.get("abstract", "") or ""
    if reg_text and abstract_val and str(abstract_val).lower() not in ("nan", "none"):
        with st.expander("📋 Abstract (short summary)"):
            st.markdown(str(abstract_val))

    # ── Applicability & Scope ──
    applicability = ob.get("applicability", "") or ""
    eff_date = ob.get("effective_date", "") or ""
    has_scope = any(
        v and str(v).strip() and str(v).lower() not in ("nan", "none", "nat", "")
        for v in (applicability, eff_date)
    )
    if has_scope:
        st.markdown("#### Applicability & Scope")
        if applicability and str(applicability).lower() not in ("nan", "none"):
            st.markdown(f"**Applies to:** {_esc(str(applicability))}")
        if eff_date and str(eff_date).lower() not in ("nan", "none", "nat"):
            st.markdown(f"**Effective Date:** {_esc(str(eff_date))}")

    # ── Classification block ──
    st.markdown("#### Classification")
    with st.container(border=True):
        st.markdown("This obligation is classified as:")
        st.markdown("")

        # Category with explanation
        cat_explanation = CATEGORY_EXPLANATIONS.get(category, "")
        st.markdown(
            f'<span class="category-pill" style="background:{cat_bg};font-size:0.85rem">'
            f'{_esc(category)}</span>'
            f'{" — " + _esc(cat_explanation) if cat_explanation else ""}',
            unsafe_allow_html=True,
        )
        st.markdown("")

        # Relationship with explanation
        rel_explanation = RELATIONSHIP_EXPLANATIONS.get(rel_type, "")
        st.markdown(f"**Relationship:** {_esc(rel_type)}")
        if rel_explanation:
            st.caption(rel_explanation)

        # Criticality with explanation
        crit_explanation = CRITICALITY_EXPLANATIONS.get(crit, "")
        st.markdown(f"**Criticality:** {crit_dot} {_esc(crit)}")
        if crit_explanation:
            st.caption(crit_explanation)

        # Rationale
        rationale = ob.get("classification_rationale", "")
        if rationale:
            with st.expander("Rationale"):
                st.markdown(rationale)

    # ── Source link ──
    link = ob.get("link", "") or ""
    if link and str(link).lower() not in ("nan", "none"):
        st.markdown(
            f"[🔗 View source regulation]({link})",
            unsafe_allow_html=True,
        )


def render_obligation_text_only(ob: dict) -> None:
    """Render the obligation text block only (no citation/category header)."""
    from html import escape as _esc

    # ── Obligation Text ──
    st.markdown("#### Obligation Text")
    reg_text = ob.get("text", "") or ""
    if reg_text and str(reg_text).strip() and str(reg_text).lower() not in ("nan", "none"):
        st.markdown(
            f'<div class="obligation-detail">{_esc(str(reg_text).strip())}</div>',
            unsafe_allow_html=True,
        )
    else:
        abstract = ob.get("abstract", "") or ""
        if abstract and str(abstract).lower() not in ("nan", "none"):
            st.markdown(
                f'<div class="obligation-detail">{_esc(str(abstract))}</div>',
                unsafe_allow_html=True,
            )
            st.caption("_(Full regulatory text not available — showing abstract)_")
        else:
            st.info("No regulatory text available for this obligation.")


def render_coverage_chip(assessment: dict, key_suffix: str = "", show_inline: bool = False) -> None:
    """Render a single coverage assessment as a two-column chip.

    Left column: control details (always visible).
    Right column: coverage indicator, APQC ID, match info, rationale.
    """
    from html import escape as _esc

    cov = assessment.get("overall_coverage", "")
    apqc_id = assessment.get("apqc_hierarchy_id", "")
    ctrl_id = assessment.get("control_id") or ""
    sem = assessment.get("semantic_match", "")
    rel = assessment.get("relationship_match", "")

    with st.container(border=True):
        col_left, col_right = st.columns([2, 3])

        # ── LEFT: Control details ──
        with col_left:
            if ctrl_id:
                ctrl_record = _lookup_control(ctrl_id)
                if ctrl_record:
                    _render_control_detail(ctrl_record)
                else:
                    st.markdown(f"**{_esc(ctrl_id)}**")
                    st.caption("Control record not found")
            else:
                st.markdown("**No control mapped**")
                st.caption("No matching control for this APQC node")

        # ── RIGHT: Coverage breakdown ──
        with col_right:
            st.markdown(coverage_indicator_html(cov), unsafe_allow_html=True)
            st.caption(f"APQC: `{apqc_id}`")
            if sem:
                st.caption(f"Semantic: **{sem}**")
            if rel:
                st.caption(f"Relationship: **{rel}**")

            # Rationale (least prominent)
            sem_rat = assessment.get("semantic_rationale", "")
            rel_rat = assessment.get("relationship_rationale", "")
            if sem_rat:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#555;margin-top:6px">{_esc(sem_rat)}</div>',
                    unsafe_allow_html=True,
                )
            if rel_rat and rel_rat != sem_rat:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#555">{_esc(rel_rat)}</div>',
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# Control lookup & detail renderer
# ---------------------------------------------------------------------------

_QUALITY_BADGE: dict[str, tuple[str, str]] = {
    "Effective": ("#2e7d32", "white"),
    "Strong": ("#1565c0", "white"),
    "Satisfactory": ("#f9a825", "#333"),
    "Needs Improvement": ("#c62828", "white"),
}


def _lookup_control(control_id: str) -> dict | None:
    """Find a control record by ID from session state."""
    controls = st.session_state.get("controls", [])
    for c in controls:
        if c.get("control_id") == control_id:
            return c
    return None


def _render_control_detail(ctrl: dict) -> None:
    """Render a compact control summary inside a coverage chip."""
    from html import escape as _esc

    quality = ctrl.get("quality_rating", "")
    q_bg, q_fg = _QUALITY_BADGE.get(quality, ("#e0e0e0", "#333"))

    # Header: Control ID + quality badge
    st.markdown(
        f'**{_esc(ctrl.get("control_id", ""))}** &nbsp;'
        f'<span class="quality-badge" style="background:{q_bg};color:{q_fg};'
        f'border-radius:4px;padding:2px 8px;font-size:0.78rem;font-weight:600">'
        f'{_esc(quality)}</span>',
        unsafe_allow_html=True,
    )

    # Label-value pairs
    _fields = [
        ("Business Unit", ctrl.get("business_unit_name", "")),
        ("Description", ctrl.get("full_description", "")),
        ("Type", " · ".join(filter(None, [
            ctrl.get("selected_level_1", ""),
            ctrl.get("selected_level_2", ""),
        ]))),
    ]
    for label, value in _fields:
        if value and str(value).strip() and str(value).lower() not in ("nan", "none", ""):
            st.markdown(f"**{label}:** {_esc(str(value).strip())}")


def render_risk_chip(risk: dict, key_suffix: str = "", show_inline: bool = False) -> None:
    """Render a single scored risk as a two-column chip.

    Left column: risk identity (ID, severity badge, score, category).
    Right column: risk description (prominent), rationales.
    """
    from html import escape as _esc

    rid = risk.get("risk_id", "")
    desc = risk.get("risk_description", "")
    rating = risk.get("inherent_risk_rating", "Low")
    impact = risk.get("impact_rating", 0)
    freq = risk.get("frequency_rating", 0)
    score = impact * freq if impact and freq else None
    category = risk.get("risk_category", "")
    sub_cat = risk.get("sub_risk_category", "")

    _score_colors = {
        "Critical": "#c62828", "High": "#ef6c00",
        "Medium": "#f9a825", "Low": "#2e7d32",
    }
    score_color = _score_colors.get(rating, "#333")

    with st.container(border=True):
        col_left, col_right = st.columns([2, 3])

        # ── LEFT: Risk identity ──
        with col_left:
            st.markdown(f"**{_esc(rid)}**")
            st.markdown(risk_score_badge_html(rating, None), unsafe_allow_html=True)
            if impact and freq:
                st.markdown(
                    f'<div style="margin-top:4px">'
                    f'<span class="risk-score-highlight" style="color:{score_color}">'
                    f'{score}</span> &nbsp;'
                    f'<span class="risk-score-label">'
                    f'Impact {impact} × Freq {freq}</span></div>',
                    unsafe_allow_html=True,
                )
            if category:
                cat_line = f"**Category:** {_esc(category)}"
                if sub_cat:
                    cat_line += f" › {_esc(sub_cat)}"
                st.markdown(cat_line)

        # ── RIGHT: Description + rationales ──
        with col_right:
            st.markdown(desc)
            impact_rat = risk.get("impact_rationale", "")
            freq_rat = risk.get("frequency_rationale", "")
            if impact_rat:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#555;margin-top:6px">'
                    f'<strong>Impact:</strong> {_esc(impact_rat)}</div>',
                    unsafe_allow_html=True,
                )
            if freq_rat:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#555">'
                    f'<strong>Frequency:</strong> {_esc(freq_rat)}</div>',
                    unsafe_allow_html=True,
                )


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
            st.markdown(f"**{hierarchy_id} · {process_name}**")
            st.caption(rel_type)
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
    show_apqc_section: bool = False,
) -> pd.DataFrame:
    """Render a horizontal filter bar and return the filtered DataFrame."""
    num_cols = sum([show_category, show_criticality, show_subpart, show_coverage, show_apqc_section])
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

    if show_apqc_section and "apqc_sections" in df.columns:
        with cols[col_idx]:
            # Explode comma-separated section values to get unique options
            all_sections = set()
            for val in df["apqc_sections"].dropna():
                for s in str(val).split(","):
                    s = s.strip()
                    if s:
                        all_sections.add(s)
            options = sorted(all_sections, key=lambda x: (int(x) if x.isdigit() else 999, x))
            selected = st.multiselect("APQC Section", options=options, key=f"{key_prefix}_apqc_f")
            if selected:
                sel_set = set(selected)
                mask = filtered["apqc_sections"].apply(
                    lambda v: bool(sel_set & set(str(v).split(","))) if pd.notna(v) else False
                )
                filtered = filtered[mask]
        col_idx += 1

    with cols[col_idx]:
        st.metric("Showing", f"{len(filtered)} of {total_count}")

    return filtered


# ---------------------------------------------------------------------------
# Data Source Explorer — reusable configuration-driven table
# ---------------------------------------------------------------------------

# Badge renderer functions: value → HTML string
def _badge_status(val: str) -> str:
    if not val:
        return "—"
    low = val.strip().lower()
    if low == "in force":
        return '<span class="status-badge-active">In Force</span>'
    if low == "pending":
        return '<span class="status-badge-pending">Pending</span>'
    return f'<span class="rating-badge-default">{_html_escape(val)}</span>'


def _badge_control_type(val: str) -> str:
    if not val:
        return "—"
    low = val.strip().lower()
    if low == "preventive":
        return '<span class="type-badge-preventive">Preventive</span>'
    if low == "detective":
        return '<span class="type-badge-detective">Detective</span>'
    return f'<span class="rating-badge-default">{_html_escape(val)}</span>'


def _badge_rating(val: str) -> str:
    if not val:
        return "—"
    low = val.strip().lower()
    if low == "effective":
        return '<span class="rating-badge-effective">Effective</span>'
    return f'<span class="rating-badge-default">{_html_escape(val)}</span>'


BADGE_RENDERERS: dict[str, Any] = {
    "selected_level_1": _badge_control_type,
    "quality_rating": _badge_rating,
}


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for table cell content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_data_table(
    df: pd.DataFrame,
    *,
    column_keys: list[str],
    key_prefix: str,
    label_overrides: dict[str, str] | None = None,
    search_columns: list[str] | None = None,
    filter_columns: list[tuple[str, str]] | None = None,
    badge_columns: dict[str, Any] | None = None,
    truncate_columns: dict[str, int] | None = None,
    indent_column: str | None = None,
    indent_depth_column: str | None = None,
    narrow_columns: set[str] | None = None,
    all_available_columns: list[str] | None = None,
    default_page_size: int = 25,
    total_label: str = "rows",
    detail_columns: list[str] | None = None,
) -> None:
    """Render a filterable, paginated, badge-aware HTML table.

    Parameters
    ----------
    df : DataFrame
        Full (unfiltered) data.
    column_keys : list[str]
        Default visible column keys (order matters).
    key_prefix : str
        Unique prefix for all widget keys.
    label_overrides : dict
        column_key → display label overrides.
    search_columns : list[str]
        Columns to search across with text input.
    filter_columns : list[tuple[str, str]]
        (column_key, display_label) pairs for multiselect filters.
    badge_columns : dict[str, callable]
        column_key → badge renderer function.
    truncate_columns : dict[str, int]
        column_key → max chars before truncation.
    indent_column : str
        Column to apply visual indentation to.
    indent_depth_column : str
        Column containing depth (int) for indentation.
    narrow_columns : set[str]
        Column keys that should use narrow fixed width.
    all_available_columns : list[str]
        All columns in the DataFrame available for the column toggle.
    default_page_size : int
        Default rows per page.
    total_label : str
        Label for total count (e.g., "obligations", "nodes").
    detail_columns : list[str]
        Extra columns to show in a detail panel on row click.
    """
    if df.empty:
        st.info("No data available.")
        return

    label_map = dict(label_overrides or {})
    badge_map = dict(badge_columns or BADGE_RENDERERS)
    trunc_map = dict(truncate_columns or {})
    narrow = set(narrow_columns or set())
    all_cols = list(all_available_columns or df.columns)

    def _col_label(col: str) -> str:
        if col in label_map:
            return label_map[col]
        return _display_col_name(col)

    # ── Column toggle ──
    extra_cols = [c for c in all_cols if c not in column_keys and c in df.columns]
    chosen_extras: list[str] = []
    if extra_cols:
        with st.popover("⚙️ Columns"):
            chosen_extras = st.multiselect(
                "Add columns",
                options=extra_cols,
                format_func=_col_label,
                key=f"{key_prefix}_col_toggle",
            )
    visible_cols = list(column_keys) + chosen_extras
    visible_cols = [c for c in visible_cols if c in df.columns]

    # ── Search + filters bar ──
    filter_defs = list(filter_columns or [])
    num_widgets = (1 if search_columns else 0) + len(filter_defs) + 1  # +1 for count
    cols_layout = st.columns(num_widgets)
    widget_idx = 0
    filtered = df.copy()

    # Search
    if search_columns:
        with cols_layout[widget_idx]:
            search_cols_present = [c for c in search_columns if c in df.columns]
            query = st.text_input(
                "🔍 Search",
                key=f"{key_prefix}_search",
                placeholder=f"Search {', '.join(_col_label(c) for c in search_cols_present[:2])}…",
            )
            if query and search_cols_present:
                q_lower = query.lower()
                mask = pd.Series(False, index=filtered.index)
                for sc in search_cols_present:
                    mask = mask | filtered[sc].astype(str).str.lower().str.contains(
                        q_lower, na=False, regex=False,
                    )
                filtered = filtered[mask]
        widget_idx += 1

    # Filters
    for f_col, f_label in filter_defs:
        if f_col not in df.columns:
            continue
        with cols_layout[widget_idx]:
            options = sorted(filtered[f_col].dropna().unique())
            selected = st.multiselect(f_label, options=options, key=f"{key_prefix}_f_{f_col}")
            if selected:
                filtered = filtered[filtered[f_col].isin(selected)]
        widget_idx += 1

    # Count badge
    with cols_layout[widget_idx]:
        st.metric("Showing", f"{len(filtered):,} of {len(df):,}")

    # ── Pagination ──
    page_sizes = [10, 25, 50, 100]
    p_cols = st.columns([1, 3, 1, 1])
    with p_cols[0]:
        page_size = st.selectbox(
            "Rows/page",
            page_sizes,
            index=page_sizes.index(default_page_size) if default_page_size in page_sizes else 1,
            key=f"{key_prefix}_psize",
            label_visibility="collapsed",
        )
    total_rows = len(filtered)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    page_key = f"{key_prefix}_page"
    current_page = st.session_state.get(page_key, 0)
    current_page = min(current_page, total_pages - 1)
    with p_cols[1]:
        st.caption(f"Page {current_page + 1} of {total_pages} · {page_size} per page")
    with p_cols[2]:
        if st.button("◀", key=f"{key_prefix}_prev", disabled=(current_page <= 0)):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with p_cols[3]:
        if st.button("▶", key=f"{key_prefix}_next", disabled=(current_page >= total_pages - 1)):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    start = current_page * page_size
    page_df = filtered.iloc[start : start + page_size]

    if page_df.empty:
        st.info("No matching rows.")
        return

    # ── Render HTML table ──
    header_cells = "".join(
        f'<th>{_html_escape(_col_label(c))}</th>' for c in visible_cols
    )
    rows_html: list[str] = []
    page_indices = list(page_df.index)
    for row_idx in page_indices:
        row = page_df.loc[row_idx]
        cells: list[str] = []
        for c in visible_cols:
            raw = row.get(c)
            val = "" if pd.isna(raw) else str(raw)
            if not val:
                cell_html = '<span class="text-muted">—</span>'
            elif c in badge_map:
                cell_html = badge_map[c](val)
            elif c in trunc_map and len(val) > trunc_map[c]:
                short = val[: trunc_map[c]].rsplit(" ", 1)[0] + "…"
                cell_html = (
                    f'<span title="{_html_escape(val)}">'
                    f'{_html_escape(short)}</span>'
                )
            else:
                cell_html = _html_escape(val)

            # Indentation
            if indent_column and c == indent_column and indent_depth_column:
                depth_val = row.get(indent_depth_column, 1)
                try:
                    depth_int = int(depth_val)
                except (ValueError, TypeError):
                    depth_int = 1
                pad = (depth_int - 1) * 24
                cell_html = f'<span style="padding-left:{pad}px">{cell_html}</span>'

            td_class = "col-narrow" if c in narrow else ""
            cells.append(f'<td class="{td_class}">{cell_html}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    html = (
        '<div class="explorer-table-container">'
        '<table class="explorer-table">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)

    # ── Detail panel (for controls row expansion) ──
    if detail_columns:
        detail_cols_present = [c for c in detail_columns if c in df.columns]
        if detail_cols_present and not page_df.empty:
            detail_key = f"{key_prefix}_detail_idx"
            sel_options = [
                f"{page_df.loc[idx].get(visible_cols[0], idx)}" for idx in page_indices
            ]
            with st.expander("🔎 Row Detail — click to inspect a row"):
                chosen = st.selectbox(
                    "Select row",
                    options=range(len(sel_options)),
                    format_func=lambda i: sel_options[i],
                    key=detail_key,
                )
                if chosen is not None:
                    sel_row = page_df.iloc[chosen]
                    detail_pairs: list[tuple[str, str]] = []
                    for dc in detail_cols_present:
                        v = sel_row.get(dc)
                        v_str = "" if pd.isna(v) else str(v)
                        detail_pairs.append((_col_label(dc), v_str or "—"))
                    for lbl, v in detail_pairs:
                        st.markdown(f"**{lbl}:**")
                        st.markdown(v if v != "—" else f'<span class="text-muted">—</span>',
                                    unsafe_allow_html=True)
