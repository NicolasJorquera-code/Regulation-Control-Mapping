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
