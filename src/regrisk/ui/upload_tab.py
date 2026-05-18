"""Tab 1: Upload & Configure — data source selection, scope control, pipeline launch."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from regrisk.core.config import default_config_path
from regrisk.core.constants import DEFAULT_TRACE_DB_PATH
from regrisk.core.events import EventEmitter
from regrisk.graphs.classify_graph import (
    build_classify_graph,
    get_emitter as get_classify_emitter,
    reset_caches as reset_classify_caches,
    set_emitter as set_classify_emitter,
)
from regrisk.ingest.apqc_loader import load_apqc_hierarchy
from regrisk.ingest.control_loader import load_and_merge_controls
from regrisk.ingest.policy_parser import (
    detect_source_inventory,
    group_policy_obligations,
    parse_policy_excel,
)
from regrisk.ingest.regulation_parser import group_obligations, parse_regulation_excel
from regrisk.tracing.db import TraceDB
from regrisk.tracing.listener import SQLiteTraceListener
from regrisk.ui.progress import StreamlitProgressListener
from regrisk.ui.checkpoint import (
    STAGE_ASSESSED,
    STAGE_ASSESS_PARTIAL,
    STAGE_CLASSIFIED,
    STAGE_MAPPED,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from regrisk.ui.components import (
    apply_checkpoint,
    render_checkpoint_load,
    render_page_header,
    save_uploaded_file,
)


# ---------------------------------------------------------------------------
# Project root / data dir
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Tracing helpers
# ---------------------------------------------------------------------------

def _get_trace_db() -> TraceDB:
    """Return the shared TraceDB instance (one per Streamlit session)."""
    if "trace_db" not in st.session_state:
        st.session_state["trace_db"] = TraceDB(DEFAULT_TRACE_DB_PATH)
    return st.session_state["trace_db"]


def _new_run_id() -> str:
    """Generate a unique run identifier and store it in session state."""
    rid = uuid.uuid4().hex[:12]
    st.session_state["current_trace_run_id"] = rid
    return rid


# ---------------------------------------------------------------------------
# Auto-detect data files
# ---------------------------------------------------------------------------

def _detect_data_files() -> dict[str, Any]:
    """Check the data/ folder for known input files and return paths found."""
    found: dict[str, Any] = {"regulation": None, "policy": None, "apqc": None, "controls_dir": None, "control_files": []}

    if not _DATA_DIR.is_dir():
        return found

    for f in _DATA_DIR.glob("*.xlsx"):
        if "regulation" in f.name.lower():
            found["regulation"] = str(f)
            break

    # Detect policy / procedure source inventory workbook
    for f in _DATA_DIR.glob("*.xlsx"):
        if "policy" in f.name.lower() or "source_inventory" in f.name.lower():
            if detect_source_inventory(str(f)):
                found["policy"] = str(f)
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
# Cached data previews
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading regulation preview…")
def _preview_regulation(reg_path: str) -> tuple[int, list[str], pd.DataFrame]:
    _, obligations = parse_regulation_excel(reg_path)
    records = [
        {
            "citation": ob.citation,
            "mandate_title": ob.mandate_title,
            "abstract": ob.abstract[:200] if ob.abstract else "",
            "citation_level_2": ob.citation_level_2,
            "citation_level_3": ob.citation_level_3,
            "applicability": ob.applicability,
        }
        for ob in obligations
    ]
    df = pd.DataFrame(records)
    return len(obligations), list(df.columns), df.head(20)


@st.cache_data(show_spinner="Loading APQC preview…")
def _preview_apqc(apqc_path: str) -> tuple[int, list[str], pd.DataFrame]:
    nodes = load_apqc_hierarchy(apqc_path)
    records = [
        {
            "pcf_id": n.pcf_id,
            "hierarchy_id": n.hierarchy_id,
            "name": n.name,
            "depth": n.depth,
            "parent_id": n.parent_id,
        }
        for n in nodes
    ]
    df = pd.DataFrame(records)
    return len(nodes), list(df.columns), df.head(20)


@st.cache_data(show_spinner="Loading controls preview…")
def _preview_controls(control_files: tuple[str, ...]) -> tuple[int, list[str], pd.DataFrame]:
    controls = load_and_merge_controls(list(control_files))
    records = [
        {
            "control_id": c.control_id,
            "hierarchy_id": c.hierarchy_id,
            "leaf_name": c.leaf_name,
            "full_description": c.full_description[:200] if c.full_description else "",
            "selected_level_1": c.selected_level_1,
            "selected_level_2": c.selected_level_2,
            "business_unit_name": c.business_unit_name,
        }
        for c in controls
    ]
    df = pd.DataFrame(records)
    return len(controls), list(df.columns), df.head(20)


@st.cache_data(show_spinner="Scanning regulation structure…")
def _prescan_regulation(reg_path: str) -> list[dict[str, Any]]:
    _, obligations = parse_regulation_excel(reg_path)
    groups = group_obligations(obligations)
    return [
        {
            "group_id": g.group_id,
            "subpart": g.subpart,
            "section_citation": g.section_citation,
            "section_title": g.section_title,
            "topic_title": g.topic_title,
            "obligation_count": g.obligation_count,
        }
        for g in groups
    ]


# Policy / Procedure previews (Phase 5 — hybrid source model)

@st.cache_data(show_spinner="Loading policy inventory preview…")
def _preview_policy(policy_path: str) -> tuple[int, int, list[str], pd.DataFrame]:
    """Return (policy_count, procedure_count, columns, preview_df)."""
    _, obligations = parse_policy_excel(policy_path)
    policies = [o for o in obligations if o.source_type == "Policy_Requirement"]
    procedures = [o for o in obligations if o.source_type == "Procedure_Step"]
    records = [
        {
            "source_id": o.source_id or o.citation,
            "source_type": o.source_type,
            "title": o.mandate_title,
            "parent": o.parent_source_id or "",
            "business_unit": o.applicability,
            "owner": (o.source_metadata or {}).get("source_owner", ""),
            "abstract": (o.abstract or "")[:200],
        }
        for o in obligations
    ]
    df = pd.DataFrame(records)
    return len(policies), len(procedures), list(df.columns), df


@st.cache_data(show_spinner="Scanning policy structure…")
def _prescan_policy(policy_path: str) -> list[dict[str, Any]]:
    """Like _prescan_regulation but for policy workbooks."""
    _, obligations = parse_policy_excel(policy_path)
    groups = group_policy_obligations(obligations)
    return [
        {
            "group_id": g.group_id,
            "subpart": g.subpart,
            "section_citation": g.section_citation,
            "section_title": g.section_title,
            "topic_title": g.topic_title,
            "obligation_count": g.obligation_count,
        }
        for g in groups
    ]


def _subpart_summary(groups: list[dict]) -> list[dict[str, Any]]:
    by_subpart: dict[str, dict] = {}
    for g in groups:
        sp = g["subpart"] or "Unknown"
        if sp not in by_subpart:
            by_subpart[sp] = {
                "subpart": sp,
                "topic": g.get("topic_title", ""),
                "groups": 0,
                "obligations": 0,
            }
        by_subpart[sp]["groups"] += 1
        by_subpart[sp]["obligations"] += g["obligation_count"]
    return sorted(by_subpart.values(), key=lambda x: x["subpart"])


# ---------------------------------------------------------------------------
# Demo data loader
# ---------------------------------------------------------------------------

def _find_best_demo_checkpoint() -> dict[str, Any] | None:
    """Find the newest fully-assessed checkpoint for demo mode.

    Prefers patched checkpoints over regular assessed ones.
    """
    checkpoints = list_checkpoints()
    assessed = [cp for cp in checkpoints if cp["stage"] in (STAGE_ASSESSED, STAGE_ASSESS_PARTIAL)]
    if assessed:
        # Prefer patched checkpoints
        patched = [cp for cp in assessed if cp.get("patched")]
        return patched[0] if patched else assessed[0]
    # Fall back to any checkpoint (mapped, classified)
    return checkpoints[0] if checkpoints else None


def _load_demo_data() -> None:
    """Load the best available checkpoint into session state."""
    cp = _find_best_demo_checkpoint()
    if cp is None:
        st.error("No checkpoint files found in data/checkpoints/. Cannot load demo data.")
        return
    data = load_checkpoint(cp["path"])
    apply_checkpoint(data)


# ---------------------------------------------------------------------------
# Post-classification summary (removed — see git history)


# ---------------------------------------------------------------------------
# Tab renderer
# ---------------------------------------------------------------------------

def render_upload_tab() -> None:
    """Render the Upload & Configure tab."""

    render_page_header(
        "Upload & Configure",
        caption=("Pick a regulation or policy dataset, the APQC reference taxonomy and your "
                 "controls inventory, then run classification → mapping → assessment."),
        icon="⚙️",
    )

    classified = st.session_state.get("classified_obligations", [])

    # ── One-time success toast after classification completes ──
    if st.session_state.pop("classification_just_completed", False):
        st.success(f"Classification complete! {len(classified)} obligations classified.")

    if not classified:
        pass  # No demo banner — users load via checkpoint resume instead

    # ── Panel A: Data Sources ──
    detected = _detect_data_files()
    reg_path: str | None = detected["regulation"]
    policy_path: str | None = detected["policy"]
    apqc_path: str | None = detected["apqc"]
    control_files_list: list[str] = detected["control_files"]
    controls_dir: str | None = detected["controls_dir"]

    reg_file = None
    apqc_file = None
    uploaded_controls: list[Any] | None = None

    _ds_expanded = not bool(classified)

    # ── Source mode selector (regulation vs policy/procedure) ──
    available_modes: list[str] = []
    if reg_path:
        available_modes.append("Regulation Dataset")
    if policy_path:
        available_modes.append("Policy / Procedure Inventory")
    if not available_modes:
        available_modes.append("Regulation Dataset")

    if len(available_modes) > 1:
        source_mode_label = st.radio(
            "Source type",
            options=available_modes,
            index=0,
            horizontal=True,
            key="source_mode_radio",
            help="Choose which dataset to classify: a traditional regulation or an internal policy/procedure inventory.",
        )
    else:
        source_mode_label = available_modes[0]

    is_policy_mode = source_mode_label == "Policy / Procedure Inventory"

    with st.expander("📂 Data Sources", expanded=_ds_expanded):

        # --- Policy / Procedure preview ---
        if policy_path and is_policy_mode:
            try:
                n_pol, n_proc, cols, preview_df = _preview_policy(policy_path)
                with st.expander(
                    f"📋 Policy Inventory — {Path(policy_path).name} ({n_pol} policies, {n_proc} procedures)",
                    expanded=False,
                ):
                    st.caption(f"Columns: {', '.join(cols)}")
                    st.dataframe(preview_df, width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"Could not preview policy inventory: {exc}")
        elif is_policy_mode:
            st.warning("No policy inventory file found in data/. Expected a file with 'policy' or 'source_inventory' in the name containing a `Source_Inventory` sheet.")

        # --- Regulation preview ---
        if reg_path and not is_policy_mode:
            try:
                total, cols, preview_df = _preview_regulation(reg_path)
                with st.expander(f"📜 Regulation — {Path(reg_path).name} ({total:,} obligations)", expanded=False):
                    st.caption(f"Columns: {', '.join(cols)}")
                    st.dataframe(preview_df, width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"Could not preview regulation: {exc}")
        elif not is_policy_mode and not reg_path:
            st.warning("Regulation file not found in data/")
            reg_file = st.file_uploader("Upload Regulation Excel (Promontory format)", type=["xlsx"], key="reg_file")

        if apqc_path:
            try:
                total, cols, preview_df = _preview_apqc(apqc_path)
                with st.expander(f"🗂️ APQC Hierarchy — {Path(apqc_path).name} ({total:,} nodes)", expanded=False):
                    st.caption(f"Columns: {', '.join(cols)}")
                    st.dataframe(preview_df, width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"Could not preview APQC: {exc}")
        else:
            st.warning("APQC file not found in data/")
            apqc_file = st.file_uploader("Upload APQC Template Excel", type=["xlsx"], key="apqc_file")

        if control_files_list:
            try:
                total, cols, preview_df = _preview_controls(tuple(control_files_list))
                with st.expander(f"🛡️ Controls — {len(control_files_list)} file(s) ({total:,} controls)", expanded=False):
                    st.caption(f"Columns: {', '.join(cols)}")
                    st.dataframe(preview_df, width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"Could not preview controls: {exc}")
        else:
            st.info("No control files found in data/Control Dataset/")
            uploaded_controls = st.file_uploader(
                "Upload Control Files (multi-select)", type=["xlsx"],
                accept_multiple_files=True, key="control_files",
            )

    reg_path_for_scan: str | None = reg_path
    # Effective source path: regulation or policy depending on mode
    effective_source_path: str | None = policy_path if is_policy_mode else reg_path

    # ── Panel B: Run Scope ──
    with st.expander("🎯 Run Scope", expanded=_ds_expanded):

        all_groups: list[dict] = []
        subpart_options: list[str] = []

        if is_policy_mode and policy_path:
            try:
                all_groups = _prescan_policy(policy_path)
                subpart_summaries = _subpart_summary(all_groups)
                subpart_options = [
                    f"{s['subpart']} — {s['topic'][:50]} ({s['groups']} groups, {s['obligations']} items)"
                    for s in subpart_summaries
                ]
            except Exception as exc:
                st.warning(f"Could not pre-scan policy inventory: {exc}")
        elif reg_path_for_scan:
            try:
                all_groups = _prescan_regulation(reg_path_for_scan)
                subpart_summaries = _subpart_summary(all_groups)
                subpart_options = [
                    f"{s['subpart']} — {s['topic'][:50]} ({s['groups']} groups, {s['obligations']} obligations)"
                    for s in subpart_summaries
                ]
            except Exception as exc:
                st.warning(f"Could not pre-scan regulation: {exc}")

        total_groups = len(all_groups)
        total_obligations = sum(g["obligation_count"] for g in all_groups)

        scope_mode = st.radio(
            "What to classify",
            options=["All obligations", "Filter by subpart", "Quick sample"],
            index=0,
            key="scope_mode",
            horizontal=True,
        )

        selected_groups = all_groups
        scope_config: dict[str, Any] = {
            "mode": scope_mode,
            "source_mode": "policy" if is_policy_mode else "regulation",
        }

        if scope_mode == "Filter by subpart":
            if subpart_options:
                selected = st.multiselect(
                    "Select subparts to include",
                    options=subpart_options,
                    default=[],
                    key="subpart_select",
                )
                selected_names = [s.split(" — ")[0] for s in selected]
                scope_config["subparts"] = selected_names
                if selected_names:
                    selected_groups = [g for g in all_groups
                                       if g["subpart"] in selected_names]
                else:
                    selected_groups = []
            else:
                subpart_filter = st.text_input(
                    "Subpart(s) to include (comma-separated)",
                    value="Subpart C",
                    key="subpart_filter",
                    help='e.g. "Subpart C, Subpart D"',
                )
                scope_config["subparts"] = [s.strip() for s in subpart_filter.split(",") if s.strip()]

        elif scope_mode == "Quick sample":
            max_val = max(total_groups, 1)
            sample_count = st.slider(
                "Number of obligation groups to classify",
                min_value=1,
                max_value=max_val,
                value=min(3, max_val),
                key="sample_count",
                help="Each group is one CFR section (typically 5–15 obligations).",
            )
            scope_config["sample_count"] = sample_count
            selected_groups = all_groups[:sample_count]

        run_groups = len(selected_groups)
        run_obligations = sum(g["obligation_count"] for g in selected_groups)

        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("Groups to Process", run_groups,
                      delta=f"of {total_groups}" if run_groups != total_groups else None,
                      delta_color="off")
        with summary_cols[1]:
            st.metric("Obligations", run_obligations,
                      delta=f"of {total_obligations}" if run_obligations != total_obligations else None,
                      delta_color="off")
        with summary_cols[2]:
            st.metric("Est. LLM Calls", run_groups,
                      help="One LLM call per obligation group for classification")
        with summary_cols[3]:
            llm_status = "🟢 ICA" if os.environ.get("ICA_API_KEY") else \
                         "🟢 OpenAI" if os.environ.get("OPENAI_API_KEY") else \
                         "⚪ Deterministic"
            st.metric("LLM Provider", llm_status)

        if selected_groups:
            with st.expander(f"Preview: {run_groups} groups to process", expanded=False):
                preview_df = pd.DataFrame(selected_groups)[
                    ["group_id", "subpart", "section_citation", "section_title", "obligation_count"]
                ]
                preview_df.columns = ["Group ID", "Subpart", "Section", "Title", "Obligations"]
                st.dataframe(preview_df, width="stretch", height=min(400, 35 * len(preview_df) + 38),
                             hide_index=True)

    # ── Resume from Checkpoint ──
    render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED, STAGE_ASSESS_PARTIAL], "tab1")

    # ── Launch / Re-run ──
    if classified:
        with st.expander("🔄 Re-run Classification", expanded=False):
            st.caption("This will discard current classification results and re-run the pipeline.")
            has_source = bool(effective_source_path or reg_file)
            has_apqc = bool(apqc_path or apqc_file)
            ready = has_source and has_apqc

            if not ready:
                missing = []
                if not has_source:
                    missing.append("Policy Inventory" if is_policy_mode else "Regulation")
                if not has_apqc:
                    missing.append("APQC")
                st.warning(f"Please provide {' and '.join(missing)} file(s) to proceed.")

            if st.button("🔄 Re-run Classification", type="secondary", disabled=not ready,
                         width='stretch'):
                if effective_source_path and apqc_path:
                    _run_classification_from_paths(
                        effective_source_path, apqc_path, controls_dir,
                        scope_config,
                    )
                else:
                    _run_classification(reg_file, apqc_file, uploaded_controls, scope_config)
    else:
        with st.container(border=True):
            label = "📋 Launch Policy Classification" if is_policy_mode else "🚀 Launch Classification"
            st.subheader(label)

            has_source = bool(effective_source_path or reg_file)
            has_apqc = bool(apqc_path or apqc_file)
            ready = has_source and has_apqc

            if not ready:
                missing = []
                if not has_source:
                    missing.append("Policy Inventory" if is_policy_mode else "Regulation")
                if not has_apqc:
                    missing.append("APQC")
                st.warning(f"Please provide {' and '.join(missing)} file(s) to proceed.")

            btn_label = "📋 Start Policy Classification" if is_policy_mode else "🚀 Start Classification"
            if st.button(btn_label, type="primary", disabled=not ready,
                         width='stretch'):
                if effective_source_path and apqc_path:
                    _run_classification_from_paths(
                        effective_source_path, apqc_path, controls_dir,
                        scope_config,
                    )
                else:
                    _run_classification(reg_file, apqc_file, uploaded_controls, scope_config)


# ---------------------------------------------------------------------------
# Classification pipeline runners
# ---------------------------------------------------------------------------

def _run_classification_from_paths(
    reg_path: str, apqc_path: str, controls_dir: str | None,
    scope_config: dict[str, Any] | None = None,
) -> None:
    """Run Graph 1 using file paths already on disk."""
    emitter = EventEmitter()
    reset_classify_caches()
    set_classify_emitter(emitter)

    input_state = {
        "regulation_path": reg_path,
        "apqc_path": apqc_path,
        "controls_dir": controls_dir or "",
        "config_path": str(default_config_path()),
        "scope_config": scope_config or {},
    }

    _invoke_classify_graph(input_state)


def _run_classification(
    reg_file: Any, apqc_file: Any, control_files: list[Any] | None,
    scope_config: dict[str, Any] | None = None,
) -> None:
    """Run Graph 1 (classification) from uploaded files."""
    emitter = EventEmitter()
    reset_classify_caches()
    set_classify_emitter(emitter)

    reg_path = save_uploaded_file(reg_file)
    apqc_path = save_uploaded_file(apqc_file)

    controls_dir = tempfile.mkdtemp()
    for cf in (control_files or []):
        cf_path = os.path.join(controls_dir, cf.name)
        with open(cf_path, "wb") as f:
            f.write(cf.getvalue())

    input_state = {
        "regulation_path": reg_path,
        "apqc_path": apqc_path,
        "controls_dir": controls_dir,
        "config_path": str(default_config_path()),
        "scope_config": scope_config or {},
    }

    _invoke_classify_graph(input_state)


def _invoke_classify_graph(input_state: dict) -> None:
    """Shared graph invocation for both local-path and uploaded-file modes."""
    trace_db = _get_trace_db()
    run_id = _new_run_id()
    trace_db.insert_run(run_id, graph_name="classify")
    trace_listener = SQLiteTraceListener(trace_db, run_id)
    emitter = get_classify_emitter()
    emitter.on(trace_listener)

    progress_bar = st.progress(0, text="Initializing classification pipeline…")
    with st.status("Classification Pipeline", expanded=True) as status:
        progress_listener = StreamlitProgressListener(progress_bar, status, "classify")
        emitter.on(progress_listener)
        try:
            graph = build_classify_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
            status.update(label="Classification complete!", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="Classification failed", state="error")
            trace_db.update_run_status(run_id, "failed")
            st.error(f"Classification pipeline failed: {type(exc).__name__}: {exc}")
            return
        finally:
            progress_listener.detach()
    progress_bar.progress(100, text="Classification complete!")

    st.session_state["classify_result"] = result
    st.session_state["classified_obligations"] = result.get("classified_obligations", [])
    st.session_state["obligation_groups"] = result.get("obligation_groups", [])
    st.session_state["apqc_nodes"] = result.get("apqc_nodes", [])
    st.session_state["controls"] = result.get("controls", [])
    st.session_state["regulation_name"] = result.get("regulation_name", "")
    st.session_state["pipeline_config"] = result.get("pipeline_config", {})
    st.session_state["risk_taxonomy"] = result.get("risk_taxonomy", {})
    st.session_state["llm_enabled"] = result.get("llm_enabled", False)

    save_checkpoint(STAGE_CLASSIFIED, dict(st.session_state))

    st.session_state["classification_just_completed"] = True
    st.rerun()
