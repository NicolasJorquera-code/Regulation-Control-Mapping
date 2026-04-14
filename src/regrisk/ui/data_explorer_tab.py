"""Tab: Data Source Explorer — interactive tables for the three core datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.ingest.apqc_loader import load_apqc_hierarchy
from regrisk.ingest.control_loader import discover_control_files, load_and_merge_controls
from regrisk.ingest.regulation_parser import parse_regulation_excel
from regrisk.ui.components import BADGE_RENDERERS, render_data_table

# ---------------------------------------------------------------------------
# Project root / data dir
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Auto-detect data files (mirrors upload_tab._detect_data_files)
# ---------------------------------------------------------------------------

def _detect_data_files() -> dict[str, Any]:
    found: dict[str, Any] = {
        "regulation": None,
        "apqc": None,
        "controls_dir": None,
        "control_files": [],
    }
    if not _DATA_DIR.is_dir():
        return found

    for f in _DATA_DIR.glob("*.xlsx"):
        if "regulation" in f.name.lower():
            found["regulation"] = str(f)
            break

    for f in _DATA_DIR.glob("*.xlsx"):
        if "apqc" in f.name.lower():
            found["apqc"] = str(f)
            break

    controls_dir = _DATA_DIR / "Control Dataset"
    if controls_dir.is_dir():
        xlsx_files = sorted(controls_dir.glob("*.xlsx"))
        if xlsx_files:
            found["controls_dir"] = str(controls_dir)
            found["control_files"] = [str(f) for f in xlsx_files]

    return found


# ---------------------------------------------------------------------------
# Cached full-dataset loaders
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading regulations…")
def _load_regulations(reg_path: str) -> tuple[int, pd.DataFrame]:
    _, obligations = parse_regulation_excel(reg_path)
    records = [ob.model_dump() for ob in obligations]
    df = pd.DataFrame(records)
    return len(obligations), df


@st.cache_data(show_spinner="Loading APQC hierarchy…")
def _load_apqc(apqc_path: str) -> tuple[int, pd.DataFrame]:
    nodes = load_apqc_hierarchy(apqc_path)
    records = [n.model_dump() for n in nodes]
    df = pd.DataFrame(records)
    return len(nodes), df


@st.cache_data(show_spinner="Loading controls…")
def _load_controls(control_files: tuple[str, ...]) -> tuple[int, pd.DataFrame]:
    controls = load_and_merge_controls(list(control_files))
    records = [c.model_dump() for c in controls]
    df = pd.DataFrame(records)
    return len(controls), df


# ---------------------------------------------------------------------------
# Table configurations
# ---------------------------------------------------------------------------

_REG_DEFAULT_COLS = [
    "citation",
    "mandate_title",
    "abstract",
    "citation_level_2",
    "citation_level_3",
    "applicability",
    "effective_date",
]

_REG_LABEL_OVERRIDES = {
    "mandate_title": "Regulation",
    "abstract": "Obligation Summary",
    "citation_level_2": "Subpart",
    "citation_level_3": "Section",
    "effective_date": "Effective Date",
}

_APQC_DEFAULT_COLS = [
    "hierarchy_id",
    "name",
    "pcf_id",
    "depth",
]

_APQC_LABEL_OVERRIDES = {
    "hierarchy_id": "Hierarchy ID",
    "name": "Process Name",
    "pcf_id": "PCF ID",
    "depth": "Level",
}

_CTRL_DEFAULT_COLS = [
    "control_id",
    "hierarchy_id",
    "leaf_name",
    "selected_level_1",
    "selected_level_2",
    "who",
    "what",
    "frequency",
    "business_unit_name",
    "quality_rating",
]

_CTRL_LABEL_OVERRIDES = {
    "hierarchy_id": "Process ID",
    "leaf_name": "Process Name",
    "selected_level_1": "Control Type",
    "selected_level_2": "Control Category",
    "who": "Performed By",
    "what": "Control Activity",
    "business_unit_name": "Business Unit",
    "quality_rating": "Rating",
}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_data_explorer_tab() -> None:
    """Main entry point for the Data Source Explorer tab."""

    st.markdown(
        "Browse the three core datasets that feed the control-mapping engine. "
        "Each table shows curated default columns — use ⚙️ Columns to reveal more."
    )

    data = _detect_data_files()

    # ── 1. Regulations ──
    reg_path = data["regulation"]
    if reg_path:
        try:
            total, df_reg = _load_regulations(reg_path)
        except Exception as exc:
            st.error(f"Could not load regulations: {exc}")
            df_reg, total = pd.DataFrame(), 0

        with st.expander(
            f"📜 Regulations — {Path(reg_path).name} ({total:,} obligations)",
            expanded=True,
        ):
            if df_reg.empty:
                st.info("No regulation data loaded.")
            else:
                render_data_table(
                    df_reg,
                    column_keys=_REG_DEFAULT_COLS,
                    key_prefix="expl_reg",
                    label_overrides=_REG_LABEL_OVERRIDES,
                    search_columns=["citation", "abstract"],
                    filter_columns=[
                        ("mandate_title", "Regulation"),
                        ("citation_level_2", "Subpart"),
                    ],
                    badge_columns={},
                    truncate_columns={"abstract": 120},
                    narrow_columns={"citation", "citation_level_2", "citation_level_3", "effective_date"},
                    total_label="obligations",
                )
    else:
        st.warning("Regulation file not found in `data/`.")

    # ── 2. APQC Process Hierarchy ──
    apqc_path = data["apqc"]
    if apqc_path:
        try:
            total, df_apqc = _load_apqc(apqc_path)
        except Exception as exc:
            st.error(f"Could not load APQC hierarchy: {exc}")
            df_apqc, total = pd.DataFrame(), 0

        with st.expander(
            f"🗂️ APQC Process Hierarchy — {Path(apqc_path).name} ({total:,} nodes)",
            expanded=False,
        ):
            if df_apqc.empty:
                st.info("No APQC data loaded.")
            else:
                # Build top-level category filter options (depth == 1 nodes)
                top_level = df_apqc[df_apqc["depth"] == 1].copy()
                cat_options: list[str] = []
                cat_map: dict[str, str] = {}  # display label → hierarchy_id prefix
                for _, row in top_level.iterrows():
                    hid = str(row["hierarchy_id"])
                    name = str(row["name"])
                    label = f"{hid} — {name}"
                    cat_options.append(label)
                    cat_map[label] = hid

                # Pre-filter by category if selected
                df_apqc_view = df_apqc
                cat_filter = st.multiselect(
                    "Process Family",
                    options=cat_options,
                    key="expl_apqc_cat",
                )
                if cat_filter:
                    prefixes = [cat_map[c] for c in cat_filter]
                    mask = pd.Series(False, index=df_apqc_view.index)
                    for pfx in prefixes:
                        mask = mask | df_apqc_view["hierarchy_id"].astype(str).str.startswith(pfx + ".")
                        mask = mask | (df_apqc_view["hierarchy_id"] == pfx)
                    df_apqc_view = df_apqc_view[mask]

                render_data_table(
                    df_apqc_view,
                    column_keys=_APQC_DEFAULT_COLS,
                    key_prefix="expl_apqc",
                    label_overrides=_APQC_LABEL_OVERRIDES,
                    search_columns=["hierarchy_id", "name"],
                    filter_columns=[],
                    badge_columns={},
                    indent_column="name",
                    indent_depth_column="depth",
                    narrow_columns={"hierarchy_id", "pcf_id", "depth"},
                    total_label="nodes",
                )
    else:
        st.warning("APQC file not found in `data/`.")

    # ── 3. Controls ──
    control_files = data["control_files"]
    if control_files:
        try:
            total, df_ctrl = _load_controls(tuple(control_files))
        except Exception as exc:
            st.error(f"Could not load controls: {exc}")
            df_ctrl, total = pd.DataFrame(), 0

        file_count = len(control_files)
        with st.expander(
            f"🛡️ Controls — {file_count} file(s) ({total:,} controls)",
            expanded=False,
        ):
            if df_ctrl.empty:
                st.info("No control data loaded.")
            else:
                render_data_table(
                    df_ctrl,
                    column_keys=_CTRL_DEFAULT_COLS,
                    key_prefix="expl_ctrl",
                    label_overrides=_CTRL_LABEL_OVERRIDES,
                    search_columns=["control_id", "leaf_name", "what"],
                    filter_columns=[
                        ("selected_level_1", "Control Type"),
                        ("selected_level_2", "Control Category"),
                        ("business_unit_name", "Business Unit"),
                        ("frequency", "Frequency"),
                        ("quality_rating", "Rating"),
                    ],
                    badge_columns={
                        "selected_level_1": BADGE_RENDERERS["selected_level_1"],
                        "quality_rating": BADGE_RENDERERS["quality_rating"],
                    },
                    truncate_columns={"what": 120},
                    narrow_columns={"control_id", "hierarchy_id", "frequency", "quality_rating"},
                    detail_columns=["when", "where", "why", "full_description", "evidence"],
                    total_label="controls",
                )
    else:
        st.info("No control files found in `data/Control Dataset/`.")
