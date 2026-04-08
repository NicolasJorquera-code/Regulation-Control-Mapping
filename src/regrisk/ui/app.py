"""
Streamlit 5-tab UI for the Regulatory Obligation Control Mapper.

Tab 1: Upload & Configure
Tab 2: Classification Review
Tab 3: Mapping Review
Tab 4: Results (coverage summary, risk heatmap, gaps, risk register)
Tab 5: Traceability

Two graph invocations bridged via st.session_state.
Checkpoint persistence allows resuming after mid-run failures.
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid

from dotenv import load_dotenv
load_dotenv()

# Configure logging so transport/agent messages appear in the terminal.
# INFO shows: provider detection, URL discovery, per-call success/token usage.
# Set to DEBUG for per-attempt request details.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet down noisy third-party loggers
for _quiet in ("httpx", "httpcore", "urllib3", "matplotlib", "PIL"):
    logging.getLogger(_quiet).setLevel(logging.WARNING)
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from regrisk.core.config import default_config_path, load_config
from regrisk.core.events import EventEmitter, EventType, PipelineEvent
from regrisk.export.excel_export import (
    export_compliance_matrix,
    export_for_review,
    export_gap_report,
    import_reviewed,
)
from regrisk.graphs.classify_graph import build_classify_graph
from regrisk.graphs.classify_graph import set_emitter as set_classify_emitter
from regrisk.graphs.classify_graph import get_emitter as get_classify_emitter
from regrisk.graphs.classify_graph import reset_caches as reset_classify_caches
from regrisk.graphs.assess_graph import build_assess_graph
from regrisk.graphs.assess_graph import set_emitter as set_assess_emitter
from regrisk.graphs.assess_graph import get_emitter as get_assess_emitter
from regrisk.graphs.assess_graph import reset_caches as reset_assess_caches
from regrisk.ingest.regulation_parser import parse_regulation_excel, group_obligations
from regrisk.ui.checkpoint import (
    STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED,
    save_checkpoint, load_checkpoint, list_checkpoints,
    stage_label, stage_keys,
)
from regrisk.tracing.db import TraceDB
from regrisk.tracing.listener import SQLiteTraceListener


# ---------------------------------------------------------------------------
# Event → UI mapping
# ---------------------------------------------------------------------------

_EVENT_EMOJI: dict[EventType, str] = {
    EventType.PIPELINE_STARTED: "🚀",
    EventType.PIPELINE_COMPLETED: "✅",
    EventType.PIPELINE_FAILED: "❌",
    EventType.STAGE_STARTED: "📋",
    EventType.STAGE_COMPLETED: "✔️",
    EventType.PROGRESS: "⏳",
    EventType.AGENT_STARTED: "🤖",
    EventType.AGENT_COMPLETED: "✔️",
    EventType.AGENT_FAILED: "❌",
    EventType.AGENT_RETRY: "🔄",
    EventType.VALIDATION_PASSED: "✅",
    EventType.VALIDATION_FAILED: "⚠️",
    EventType.TOOL_CALLED: "🔧",
    EventType.TOOL_COMPLETED: "🔧",
    EventType.ITEM_STARTED: "📝",
    EventType.ITEM_COMPLETED: "📝",
    EventType.WARNING: "⚠️",
    EventType.INGEST_COMPLETED: "📦",
    EventType.GROUP_CLASSIFIED: "🏷️",
    EventType.MAPPING_COMPLETED: "🗺️",
    EventType.COVERAGE_ASSESSED: "🛡️",
    EventType.RISK_SCORED: "⚡",
    EventType.REVIEW_CHECKPOINT: "👤",
}


class StreamlitEventListener:
    """Accumulates events and renders them in a Streamlit container."""

    def __init__(self, container: st.delta_generator.DeltaGenerator) -> None:
        self._container = container
        self._lines: list[str] = []

    def __call__(self, event: PipelineEvent) -> None:
        emoji = _EVENT_EMOJI.get(event.event_type, "•")
        line = f"{emoji} {event.message or event.stage}"
        self._lines.append(line)
        self._container.markdown("\n\n".join(self._lines[-20:]))


# ---------------------------------------------------------------------------
# Tracing helpers
# ---------------------------------------------------------------------------

def _get_trace_db() -> TraceDB:
    """Return the shared TraceDB instance (one per Streamlit session)."""
    if "trace_db" not in st.session_state:
        st.session_state["trace_db"] = TraceDB("data/traces.db")
    return st.session_state["trace_db"]


def _new_run_id() -> str:
    """Generate a unique run identifier and store it in session state."""
    rid = uuid.uuid4().hex[:12]
    st.session_state["current_trace_run_id"] = rid
    return rid


# ---------------------------------------------------------------------------
# Color coding for categories
# ---------------------------------------------------------------------------

_CATEGORY_COLORS = {
    "Controls": "background-color: #CCE5FF",
    "Documentation": "background-color: #D4EDDA",
    "Attestation": "background-color: #E2D5F1",
    "General Awareness": "background-color: #E2E3E5",
    "Not Assigned": "background-color: #F8D7DA",
}


def _color_category(val: str) -> str:
    return _CATEGORY_COLORS.get(val, "")


# ---------------------------------------------------------------------------
# Helper: save uploaded file to temp path
# ---------------------------------------------------------------------------

def _save_uploaded_file(uploaded_file: Any) -> str:
    """Save a Streamlit UploadedFile to a temporary path and return the path."""
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


# ---------------------------------------------------------------------------
# Auto-detect data files in the data/ directory
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/regrisk/ui -> project root
_DATA_DIR = _PROJECT_ROOT / "data"


def _detect_data_files() -> dict[str, Any]:
    """Check the data/ folder for known input files and return paths found."""
    found: dict[str, Any] = {"regulation": None, "apqc": None, "controls_dir": None, "control_files": []}

    if not _DATA_DIR.is_dir():
        return found

    # Regulation file — look for xlsx with 'regulation' in the name
    for f in _DATA_DIR.glob("*.xlsx"):
        if "regulation" in f.name.lower():
            found["regulation"] = str(f)
            break

    # APQC file — look for xlsx with 'apqc' in the name
    for f in _DATA_DIR.glob("*.xlsx"):
        if "apqc" in f.name.lower():
            found["apqc"] = str(f)
            break

    # Control files — look for the Control Dataset subdirectory
    controls_dir = _DATA_DIR / "Control Dataset"
    if controls_dir.is_dir():
        xlsx_files = sorted(controls_dir.glob("*.xlsx"))
        if xlsx_files:
            found["controls_dir"] = str(controls_dir)
            found["control_files"] = [str(f) for f in xlsx_files]

    return found


# ---------------------------------------------------------------------------
# Pre-scan: parse regulation to discover subparts & groups for scope UI
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Scanning regulation structure…")
def _prescan_regulation(reg_path: str) -> list[dict[str, Any]]:
    """Parse the regulation file to extract group metadata for the scope UI.

    Returns a list of dicts with: group_id, subpart, section_citation,
    section_title, topic_title, obligation_count.
    """
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


def _subpart_summary(groups: list[dict]) -> list[dict[str, Any]]:
    """Aggregate group metadata into per-subpart summaries."""
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
# Pipeline status helpers
# ---------------------------------------------------------------------------

def _pipeline_phase() -> str:
    """Return the furthest pipeline phase completed in session_state."""
    if st.session_state.get("gap_report"):
        return STAGE_ASSESSED
    if st.session_state.get("obligation_mappings"):
        return STAGE_MAPPED
    if st.session_state.get("classified_obligations"):
        return STAGE_CLASSIFIED
    return ""


def _phase_badge(label: str, complete: bool) -> str:
    return f"✅ {label}" if complete else f"⬜ {label}"


# ---------------------------------------------------------------------------
# Checkpoint UI helpers
# ---------------------------------------------------------------------------

def _render_checkpoint_save(stage: str, key_prefix: str) -> None:
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


def _render_checkpoint_load(allowed_stages: list[str], key_prefix: str) -> None:
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
                    _apply_checkpoint(data)

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
                    _apply_checkpoint(data)


def _apply_checkpoint(data: dict[str, Any]) -> None:
    """Write checkpoint data into session_state and rerun."""
    meta = data.pop("_meta", {})
    for k, v in data.items():
        st.session_state[k] = v
    st.success(f"Restored **{meta.get('stage_label', '?')}** checkpoint "
               f"for *{meta.get('regulation_name', '?')}*")
    st.rerun()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Regulatory Obligation Control Mapper",
        page_icon="📋",
        layout="wide",
    )

    # Reset graph-module caches once per Streamlit session so the LLM client
    # picks up the latest env-var configuration (timeout, model, etc.).
    if "caches_initialised" not in st.session_state:
        reset_classify_caches()
        reset_assess_caches()
        st.session_state["caches_initialised"] = True

    st.title("📋 Regulatory Obligation Control Mapper")
    st.caption("Map regulatory obligations → APQC processes → control coverage → risk scoring")

    # ── Pipeline status bar ──
    phase = _pipeline_phase()
    status_cols = st.columns(4)
    with status_cols[0]:
        st.markdown(_phase_badge("Classification", phase in (STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED)))
    with status_cols[1]:
        st.markdown(_phase_badge("APQC Mapping", phase in (STAGE_MAPPED, STAGE_ASSESSED)))
    with status_cols[2]:
        st.markdown(_phase_badge("Coverage & Risk", phase == STAGE_ASSESSED))
    with status_cols[3]:
        reg = st.session_state.get("regulation_name", "")
        if reg:
            st.markdown(f"📜 *{reg}*")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📁 Upload & Configure",
        "🏷️ Classification Review",
        "🗺️ Mapping Review",
        "📊 Results",
        "🔗 Traceability",
    ])

    # ── Tab 1: Upload & Configure ──
    with tab1:
        _render_upload_tab()

    # ── Tab 2: Classification Review ──
    with tab2:
        _render_classification_review_tab()

    # ── Tab 3: Mapping Review ──
    with tab3:
        _render_mapping_review_tab()

    # ── Tab 4: Results ──
    with tab4:
        _render_results_tab()

    # ── Tab 5: Traceability ──
    with tab5:
        _render_traceability_tab()


# ---------------------------------------------------------------------------
# Tab 1: Upload & Configure
# ---------------------------------------------------------------------------

def _render_upload_tab() -> None:

    # ── Panel A: Data Sources ──
    with st.container(border=True):
        st.subheader("📂 Data Sources")

        # Auto-detect existing files
        detected = _detect_data_files()
        has_detected = detected["regulation"] or detected["apqc"] or detected["control_files"]

        if has_detected:
            det_col1, det_col2, det_col3 = st.columns(3)
            with det_col1:
                if detected["regulation"]:
                    st.success(f"**Regulation**  \n`{Path(detected['regulation']).name}`")
                else:
                    st.warning("Regulation file not found")
            with det_col2:
                if detected["apqc"]:
                    st.success(f"**APQC**  \n`{Path(detected['apqc']).name}`")
                else:
                    st.warning("APQC file not found")
            with det_col3:
                if detected["control_files"]:
                    st.success(f"**Controls**  \n{len(detected['control_files'])} file(s)")
                else:
                    st.warning("No control files found")

            use_local = st.checkbox("Use files from data/ folder", value=True, key="use_local_files")
        else:
            use_local = False

        if not use_local:
            st.markdown("**Upload Files**")
            col1, col2 = st.columns(2)
            with col1:
                reg_file = st.file_uploader("Regulation Excel (Promontory format)", type=["xlsx"], key="reg_file")
                apqc_file = st.file_uploader("APQC Template Excel", type=["xlsx"], key="apqc_file")
            with col2:
                control_files = st.file_uploader("Control Files (multi-select)", type=["xlsx"],
                                                  accept_multiple_files=True, key="control_files")
        else:
            reg_file = None
            apqc_file = None
            control_files = None

    # ── Panel B: Pipeline Configuration ──
    with st.container(border=True):
        st.subheader("⚙️ Pipeline Configuration")
        try:
            config = load_config(str(default_config_path()))

            cfg_col1, cfg_col2, cfg_col3, cfg_col4, cfg_col5 = st.columns(5)
            with cfg_col1:
                st.metric("APQC Depth", config.apqc_mapping_depth)
            with cfg_col2:
                st.metric("Max Mappings", config.max_apqc_mappings_per_obligation)
            with cfg_col3:
                st.metric("Categories", len(config.obligation_categories))
            with cfg_col4:
                st.metric("Risk Scale", "4 × 4")
            with cfg_col5:
                st.metric("Risks / Gap", f"{config.min_risks_per_gap}–{config.max_risks_per_gap}")

            with st.expander("View configuration details"):
                detail_cols = st.columns(2)
                with detail_cols[0]:
                    st.markdown("**Obligation Categories**")
                    for cat in config.obligation_categories:
                        st.markdown(f"- {cat}")
                    st.markdown("**Actionable (mapped + assessed)**")
                    for cat in config.actionable_categories:
                        st.markdown(f"- *{cat}*")
                with detail_cols[1]:
                    st.markdown("**Risk Scoring**")
                    st.markdown("- **Impact** (1–4): Minor → Severe")
                    st.markdown("- **Frequency** (1–4): Remote → Likely")
                    st.markdown("- **Score** = Impact × Frequency (1–16)")
                    st.markdown("- Critical ≥12, High 8–11, Medium 4–7, Low 1–3")
                    st.markdown("**Coverage Thresholds**")
                    st.markdown(f"- Semantic match min: {config.coverage_thresholds.get('semantic_match_min_confidence', 0.6)}")
        except Exception:
            st.warning("Could not load config. Using defaults.")
            config = None

    # ── Determine regulation path for pre-scan ──
    reg_path_for_scan: str | None = None
    if use_local and detected.get("regulation"):
        reg_path_for_scan = detected["regulation"]

    # ── Panel C: Run Scope ──
    with st.container(border=True):
        st.subheader("🎯 Run Scope")

        # Pre-scan regulation for subpart/group metadata
        all_groups: list[dict] = []
        subpart_options: list[str] = []
        if reg_path_for_scan:
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

        # ── Mode-specific controls ──
        selected_groups = all_groups  # default to all
        scope_config: dict[str, Any] = {"mode": scope_mode}

        if scope_mode == "Filter by subpart":
            if subpart_options:
                selected = st.multiselect(
                    "Select subparts to include",
                    options=subpart_options,
                    default=[],
                    key="subpart_select",
                )
                # Extract subpart names from display strings
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

        # ── Run Summary ──
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

        # ── Group preview table ──
        if selected_groups:
            with st.expander(f"Preview: {run_groups} groups to process", expanded=False):
                preview_df = pd.DataFrame(selected_groups)[
                    ["group_id", "subpart", "section_citation", "section_title", "obligation_count"]
                ]
                preview_df.columns = ["Group ID", "Subpart", "Section", "Title", "Obligations"]
                st.dataframe(preview_df, width="stretch", height=min(400, 35 * len(preview_df) + 38),
                             hide_index=True)

    # ── Panel D: Resume from Checkpoint ──
    _render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED], "tab1")

    # ── Panel E: Launch ──
    with st.container(border=True):
        st.subheader("🚀 Launch Classification")

        if use_local:
            ready = bool(detected["regulation"] and detected["apqc"])
        else:
            ready = bool(reg_file and apqc_file)

        if not ready:
            st.warning("Please provide Regulation and APQC files to proceed.")

        if st.button("🚀 Start Classification", type="primary", disabled=not ready,
                     use_container_width=True):
            if use_local:
                _run_classification_from_paths(
                    detected["regulation"], detected["apqc"], detected["controls_dir"],
                    scope_config,
                )
            else:
                _run_classification(reg_file, apqc_file, control_files, scope_config)


def _run_classification_from_paths(
    reg_path: str, apqc_path: str, controls_dir: str | None,
    scope_config: dict[str, Any] | None = None,
) -> None:
    """Run Graph 1 using file paths already on disk."""
    progress_container = st.empty()
    emitter = EventEmitter()
    listener = StreamlitEventListener(progress_container)
    emitter.on(listener)

    reset_classify_caches()
    set_classify_emitter(emitter)

    input_state = {
        "regulation_path": reg_path,
        "apqc_path": apqc_path,
        "controls_dir": controls_dir or "",
        "config_path": str(default_config_path()),
        "scope_config": scope_config or {},
    }

    _invoke_classify_graph(input_state, progress_container)


def _run_classification(
    reg_file: Any, apqc_file: Any, control_files: list[Any],
    scope_config: dict[str, Any] | None = None,
) -> None:
    """Run Graph 1 (classification) from uploaded files."""
    progress_container = st.empty()
    emitter = EventEmitter()
    listener = StreamlitEventListener(progress_container)
    emitter.on(listener)

    reset_classify_caches()
    set_classify_emitter(emitter)

    # Save uploaded files to temp paths
    reg_path = _save_uploaded_file(reg_file)
    apqc_path = _save_uploaded_file(apqc_file)

    # Save control files to temp directory
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

    _invoke_classify_graph(input_state, progress_container)


def _invoke_classify_graph(input_state: dict, progress_container: Any) -> None:
    """Shared graph invocation for both local-path and uploaded-file modes."""

    # Set up tracing
    trace_db = _get_trace_db()
    run_id = _new_run_id()
    trace_db.insert_run(run_id, graph_name="classify")
    trace_listener = SQLiteTraceListener(trace_db, run_id)
    _emitter = get_classify_emitter()
    _emitter.on(trace_listener)

    with st.spinner("Running classification pipeline…"):
        try:
            graph = build_classify_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
        except Exception as exc:
            trace_db.update_run_status(run_id, "failed")
            st.error(f"Classification pipeline failed: {type(exc).__name__}: {exc}")
            return


    # Store results in session state
    st.session_state["classify_result"] = result
    st.session_state["classified_obligations"] = result.get("classified_obligations", [])
    st.session_state["obligation_groups"] = result.get("obligation_groups", [])
    st.session_state["apqc_nodes"] = result.get("apqc_nodes", [])
    st.session_state["controls"] = result.get("controls", [])
    st.session_state["regulation_name"] = result.get("regulation_name", "")
    st.session_state["pipeline_config"] = result.get("pipeline_config", {})
    st.session_state["risk_taxonomy"] = result.get("risk_taxonomy", {})
    st.session_state["llm_enabled"] = result.get("llm_enabled", False)

    # Auto-save checkpoint
    save_checkpoint(STAGE_CLASSIFIED, dict(st.session_state))

    progress_container.empty()
    st.success(f"Classification complete! {len(st.session_state['classified_obligations'])} obligations classified.")
    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Classification Review
# ---------------------------------------------------------------------------

def _render_classification_review_tab() -> None:
    classified = st.session_state.get("classified_obligations", [])

    if not classified:
        st.info("Run classification first (Tab 1).")
        return

    st.header(f"Classification Review ({len(classified)} obligations)")

    df = pd.DataFrame(classified)

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        cat_filter = st.multiselect(
            "Filter by Category",
            options=sorted(df["obligation_category"].unique()) if "obligation_category" in df.columns else [],
            key="cat_filter",
        )
    with col2:
        crit_filter = st.multiselect(
            "Filter by Criticality",
            options=["High", "Medium", "Low"],
            key="crit_filter",
        )

    if cat_filter:
        df = df[df["obligation_category"].isin(cat_filter)]
    if crit_filter:
        df = df[df["criticality_tier"].isin(crit_filter)]

    # Display with color coding
    display_cols = [
        "citation", "obligation_category", "relationship_type",
        "criticality_tier", "section_citation", "subpart",
        "classification_rationale",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    styled = df[display_cols].style.map(
        _color_category, subset=["obligation_category"]
    ) if "obligation_category" in display_cols else df[display_cols]
    st.dataframe(styled, width="stretch", height=400)

    # Download / Upload review
    col1, col2 = st.columns(2)
    with col1:
        buf = io.BytesIO()
        export_for_review(classified, "classification", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="classification_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_classify_review",
        )
        if uploaded_review:
            review_path = _save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "classification")
            st.session_state["classified_obligations"] = reviewed
            st.success(f"Imported {len(reviewed)} approved classifications.")
            st.rerun()

    # Checkpoint save/load
    st.divider()
    _render_checkpoint_save(STAGE_CLASSIFIED, "tab2")
    _render_checkpoint_load([STAGE_CLASSIFIED], "tab2")

    st.divider()

    if st.button("✅ Approve and Continue to Mapping", type="primary"):
        st.session_state["approved_for_mapping"] = True
        _run_mapping()


# ---------------------------------------------------------------------------
# Tab 3: Mapping Review
# ---------------------------------------------------------------------------

def _render_mapping_review_tab() -> None:
    mappings = st.session_state.get("obligation_mappings", [])

    if not mappings:
        st.info("Run APQC mapping first (approve classifications in Tab 2).")
        return

    st.header(f"APQC Mapping Review ({len(mappings)} mappings)")

    df = pd.DataFrame(mappings)
    display_cols = [
        "citation", "apqc_hierarchy_id", "apqc_process_name",
        "relationship_type", "relationship_detail", "confidence",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols], width="stretch", height=400)

    # Download / Upload review
    col1, col2 = st.columns(2)
    with col1:
        buf = io.BytesIO()
        export_for_review(mappings, "mapping", buf)
        st.download_button(
            "📥 Download for Review",
            data=buf.getvalue(),
            file_name="mapping_review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        uploaded_review = st.file_uploader(
            "📤 Upload Reviewed File",
            type=["xlsx"],
            key="upload_mapping_review",
        )
        if uploaded_review:
            review_path = _save_uploaded_file(uploaded_review)
            reviewed = import_reviewed(review_path, "mapping")
            st.session_state["obligation_mappings"] = reviewed
            st.success(f"Imported {len(reviewed)} approved mappings.")
            st.rerun()

    # Checkpoint save/load
    st.divider()
    _render_checkpoint_save(STAGE_MAPPED, "tab3")
    _render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED], "tab3")

    st.divider()

    if st.button("✅ Approve and Run Coverage Assessment", type="primary"):
        _run_assessment()


def _run_mapping() -> None:
    """Run Graph 2 mapping phase."""
    progress_container = st.empty()
    emitter = EventEmitter()
    listener = StreamlitEventListener(progress_container)
    emitter.on(listener)

    reset_assess_caches()
    set_assess_emitter(emitter)

    classified = st.session_state.get("classified_obligations", [])
    config = st.session_state.get("pipeline_config", {})
    actionable = set(config.get("actionable_categories", ["Controls", "Documentation", "Attestation"]))

    # Build mappable groups from approved classifications
    groups_by_section: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        if ob.get("obligation_category") in actionable:
            key = ob.get("section_citation", "unknown")
            groups_by_section[key].append(ob)

    mappable_groups = []
    for section_cit, obs in groups_by_section.items():
        first = obs[0]
        mappable_groups.append({
            "section_citation": section_cit,
            "section_title": first.get("section_title", ""),
            "subpart": first.get("subpart", ""),
            "obligations": obs,
        })

    # We only run the mapping phase here — build a lightweight assess state
    input_state: dict[str, Any] = {
        "regulation_name": st.session_state.get("regulation_name", ""),
        "pipeline_config": config,
        "risk_taxonomy": st.session_state.get("risk_taxonomy", {}),
        "llm_enabled": st.session_state.get("llm_enabled", False),
        "apqc_nodes": st.session_state.get("apqc_nodes", []),
        "controls": st.session_state.get("controls", []),
        "approved_obligations": classified,
        "mappable_groups": mappable_groups,
        "map_idx": 0,
    }

    with st.spinner("Running APQC mapping…"):
        try:
            trace_db = _get_trace_db()
            run_id = _new_run_id()
            trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-mapping")
            trace_listener = SQLiteTraceListener(trace_db, run_id)
            emitter.on(trace_listener)

            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
        except Exception as exc:
            st.error(f"Mapping pipeline failed: {type(exc).__name__}: {exc}")
            return

    st.session_state["obligation_mappings"] = result.get("obligation_mappings", [])
    st.session_state["assess_result"] = result

    # Auto-save checkpoint
    save_checkpoint(STAGE_MAPPED, dict(st.session_state))

    progress_container.empty()
    st.success(f"Mapping complete! {len(st.session_state['obligation_mappings'])} mappings produced.")
    st.rerun()


def _run_assessment() -> None:
    """Run Graph 2 with full assessment (mapping already done — re-run full graph)."""
    progress_container = st.empty()
    emitter = EventEmitter()
    listener = StreamlitEventListener(progress_container)
    emitter.on(listener)

    reset_assess_caches()
    set_assess_emitter(emitter)

    classified = st.session_state.get("classified_obligations", [])
    config = st.session_state.get("pipeline_config", {})
    actionable = set(config.get("actionable_categories", ["Controls", "Documentation", "Attestation"]))

    groups_by_section: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        if ob.get("obligation_category") in actionable:
            key = ob.get("section_citation", "unknown")
            groups_by_section[key].append(ob)

    mappable_groups = []
    for section_cit, obs in groups_by_section.items():
        first = obs[0]
        mappable_groups.append({
            "section_citation": section_cit,
            "section_title": first.get("section_title", ""),
            "subpart": first.get("subpart", ""),
            "obligations": obs,
        })

    input_state: dict[str, Any] = {
        "regulation_name": st.session_state.get("regulation_name", ""),
        "pipeline_config": config,
        "risk_taxonomy": st.session_state.get("risk_taxonomy", {}),
        "llm_enabled": st.session_state.get("llm_enabled", False),
        "apqc_nodes": st.session_state.get("apqc_nodes", []),
        "controls": st.session_state.get("controls", []),
        "approved_obligations": classified,
        "mappable_groups": mappable_groups,
        "map_idx": 0,
    }

    with st.spinner("Running full assessment pipeline…"):
        try:
            trace_db = _get_trace_db()
            run_id = _new_run_id()
            trace_db.insert_run(run_id, regulation_name=st.session_state.get("regulation_name", ""), graph_name="assess-full")
            trace_listener = SQLiteTraceListener(trace_db, run_id)
            emitter.on(trace_listener)

            graph = build_assess_graph(trace_db=trace_db, run_id=run_id)
            result = graph.invoke(input_state)
        except Exception as exc:
            st.error(f"Assessment pipeline failed: {type(exc).__name__}: {exc}")
            return

    st.session_state["assess_result"] = result
    st.session_state["obligation_mappings"] = result.get("obligation_mappings", [])
    st.session_state["coverage_assessments"] = result.get("coverage_assessments", [])
    st.session_state["scored_risks"] = result.get("scored_risks", [])
    st.session_state["gap_report"] = result.get("gap_report", {})
    st.session_state["compliance_matrix"] = result.get("compliance_matrix", {})
    st.session_state["risk_register"] = result.get("risk_register", {})

    # Auto-save checkpoint
    save_checkpoint(STAGE_ASSESSED, dict(st.session_state))

    progress_container.empty()
    st.success("Assessment complete!")
    st.rerun()


# ---------------------------------------------------------------------------
# Tab 4: Results
# ---------------------------------------------------------------------------

def _render_results_tab() -> None:
    gap_report = st.session_state.get("gap_report", {})
    if not gap_report:
        st.info("Run the full assessment pipeline first (Tabs 1–3).")
        return

    st.header("Results")

    # Coverage summary cards
    coverage = gap_report.get("coverage_summary", {})
    total_assessed = sum(coverage.values())
    col1, col2, col3 = st.columns(3)
    with col1:
        covered = coverage.get("Covered", 0)
        pct = f"{covered / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("✅ Covered", f"{covered} ({pct})")
    with col2:
        partial = coverage.get("Partially Covered", 0)
        pct = f"{partial / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("⚠️ Partially Covered", f"{partial} ({pct})")
    with col3:
        not_covered = coverage.get("Not Covered", 0)
        pct = f"{not_covered / total_assessed * 100:.0f}%" if total_assessed > 0 else "N/A"
        st.metric("❌ Not Covered", f"{not_covered} ({pct})")

    st.divider()

    # Risk heatmap
    risks = st.session_state.get("scored_risks", [])
    if risks:
        st.subheader("Risk Heatmap (Impact × Frequency)")
        _render_risk_heatmap(risks)

    st.divider()

    # Gap analysis table
    st.subheader("Gap Analysis")
    gaps = gap_report.get("gaps", [])
    if gaps:
        df_gaps = pd.DataFrame(gaps)
        display_cols = ["citation", "apqc_hierarchy_id", "control_id", "overall_coverage",
                        "semantic_match", "relationship_match"]
        display_cols = [c for c in display_cols if c in df_gaps.columns]
        st.dataframe(df_gaps[display_cols], width="stretch", height=300)
    else:
        st.success("No gaps found — all obligations have coverage!")

    st.divider()

    # Risk register
    st.subheader("Risk Register")
    if risks:
        df_risks = pd.DataFrame(risks)
        display_cols = [
            "risk_id", "source_citation", "risk_description",
            "risk_category", "impact_rating", "frequency_rating",
            "inherent_risk_rating", "coverage_status",
        ]
        display_cols = [c for c in display_cols if c in df_risks.columns]
        st.dataframe(df_risks[display_cols], width="stretch", height=300)
    else:
        st.info("No risks extracted.")

    st.divider()

    # Download full report
    buf = io.BytesIO()
    export_gap_report(
        gap_report,
        st.session_state.get("classified_obligations", []),
        st.session_state.get("obligation_mappings", []),
        st.session_state.get("coverage_assessments", []),
        risks,
        buf,
    )
    st.download_button(
        "📥 Download Full Report",
        data=buf.getvalue(),
        file_name="compliance_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Checkpoint save/load
    st.divider()
    _render_checkpoint_save(STAGE_ASSESSED, "tab4")
    _render_checkpoint_load([STAGE_CLASSIFIED, STAGE_MAPPED, STAGE_ASSESSED], "tab4")


def _render_risk_heatmap(risks: list[dict]) -> None:
    """4×4 risk heatmap using matplotlib."""
    grid = np.zeros((4, 4), dtype=int)
    for r in risks:
        impact = r.get("impact_rating", 1)
        freq = r.get("frequency_rating", 1)
        if 1 <= impact <= 4 and 1 <= freq <= 4:
            grid[4 - impact][freq - 1] += 1

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = np.array([
        [0.2, 0.8, 0.2, 1],  # green
        [1.0, 1.0, 0.0, 1],  # yellow
        [1.0, 0.6, 0.0, 1],  # orange
        [1.0, 0.0, 0.0, 1],  # red
    ])

    # Build color grid based on risk score (impact × frequency)
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


# ---------------------------------------------------------------------------
# Tab 5: Traceability — SQLite-backed execution trace viewer
# ---------------------------------------------------------------------------

def _render_traceability_tab() -> None:
    import time as _time

    trace_db = _get_trace_db()
    runs = trace_db.list_runs(limit=50)

    # ── Section A: Run Selector ──
    st.header("🔍 Execution Trace Viewer")
    st.caption(
        "Every pipeline run is recorded to a local SQLite database at "
        "**data/traces.db**. You can also query it directly in a terminal: "
        "`sqlite3 data/traces.db \"SELECT * FROM runs;\"`"
    )

    if not runs:
        st.info("No traced runs yet. Run the pipeline to start recording traces.")
        _render_data_lineage()
        return

    # Build display labels
    run_labels: dict[str, str] = {}
    for r in runs:
        ts = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(r["started_at"]))
        status_icon = {"running": "🟡", "completed": "🟢", "failed": "🔴"}.get(r["status"], "⚪")
        label = f"{status_icon} {r['graph_name']} — {r.get('regulation_name') or '(unnamed)'} — {ts}"
        run_labels[r["run_id"]] = label

    # Auto-select the current run if one just finished
    current_run_id = st.session_state.get("current_trace_run_id", "")
    default_idx = 0
    run_ids = [r["run_id"] for r in runs]
    if current_run_id in run_ids:
        default_idx = run_ids.index(current_run_id)

    selected_id = st.selectbox(
        "Select a run",
        options=run_ids,
        index=default_idx,
        format_func=lambda rid: run_labels.get(rid, rid),
    )

    if not selected_id:
        return

    summary = trace_db.get_run_summary(selected_id)
    if not summary:
        st.warning("Run not found.")
        return

    # ── Section B: Run Overview ──
    st.subheader("📊 Run Overview")
    status_badge = {"running": "🟡 Running", "completed": "🟢 Completed", "failed": "🔴 Failed"}.get(
        summary.get("status", ""), summary.get("status", "")
    )
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Status", status_badge)
    col2.metric("Nodes Executed", summary.get("node_count", 0))
    col3.metric("LLM Calls", summary.get("llm_call_count", 0))
    col4.metric("Total Tokens", f"{summary.get('total_tokens', 0):,}")
    duration_s = (summary.get("total_node_ms", 0) or 0) / 1000
    col5.metric("Node Time", f"{duration_s:.1f}s")

    # ── Section C: Event Timeline ──
    st.subheader("📋 Event Timeline")
    events = trace_db.get_run_events(selected_id)
    if events:
        _EVENT_COLOR: dict[str, str] = {
            "pipeline_started": "#1E88E5",
            "pipeline_completed": "#43A047",
            "pipeline_failed": "#E53935",
            "stage_started": "#1E88E5",
            "stage_completed": "#43A047",
            "item_started": "#FDD835",
            "item_completed": "#43A047",
            "group_classified": "#7E57C2",
            "mapping_completed": "#26A69A",
            "coverage_assessed": "#42A5F5",
            "risk_scored": "#FF7043",
            "warning": "#FFA726",
        }

        event_rows = []
        for e in events:
            ts = _time.strftime("%H:%M:%S", _time.localtime(e["timestamp"]))
            color = _EVENT_COLOR.get(e["event_type"], "#90A4AE")
            event_rows.append({
                "Time": ts,
                "Event": e["event_type"],
                "Stage": e.get("stage") or "",
                "Message": e.get("message") or "",
            })
        df_events = pd.DataFrame(event_rows)
        st.dataframe(df_events, use_container_width=True, hide_index=True)
    else:
        st.caption("No events recorded.")

    # ── Section D: Node Executions ──
    st.subheader("⚙️ Node Executions")
    nodes = trace_db.get_run_nodes(selected_id)
    if nodes:
        node_rows = []
        for n in nodes:
            node_rows.append({
                "Node": n["node_name"],
                "Duration (ms)": round(n.get("duration_ms") or 0, 1),
                "Input": n.get("input_summary") or "",
                "Output": n.get("output_summary") or "",
                "Error": n.get("error") or "",
            })
        df_nodes = pd.DataFrame(node_rows)
        st.dataframe(df_nodes, use_container_width=True, hide_index=True)

        # Bar chart of durations
        if len(node_rows) > 1:
            chart_df = df_nodes[["Node", "Duration (ms)"]].set_index("Node")
            st.bar_chart(chart_df)
    else:
        st.caption("No node executions recorded.")

    # ── Section E: LLM Call Inspector ──
    st.subheader("🤖 LLM Call Inspector")
    llm_calls = trace_db.get_run_llm_calls(selected_id)
    if llm_calls:
        # Summary metrics
        total_prompt_tok = sum(c.get("prompt_tokens") or 0 for c in llm_calls)
        total_comp_tok = sum(c.get("completion_tokens") or 0 for c in llm_calls)
        total_latency = sum(c.get("latency_ms") or 0 for c in llm_calls)
        avg_latency = total_latency / len(llm_calls) if llm_calls else 0

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total LLM Calls", len(llm_calls))
        mc2.metric("Prompt Tokens", f"{total_prompt_tok:,}")
        mc3.metric("Completion Tokens", f"{total_comp_tok:,}")
        mc4.metric("Avg Latency", f"{avg_latency:.0f}ms")

        # Call table
        call_rows = []
        for i, c in enumerate(llm_calls):
            ts = _time.strftime("%H:%M:%S", _time.localtime(c["timestamp"]))
            call_rows.append({
                "#": i + 1,
                "Time": ts,
                "Node": c.get("node_name") or "",
                "Agent": c.get("agent_name") or "",
                "Model": c.get("model") or "",
                "Prompt Tok": c.get("prompt_tokens") or 0,
                "Comp Tok": c.get("completion_tokens") or 0,
                "Latency (ms)": round(c.get("latency_ms") or 0, 0),
                "Error": c.get("error") or "",
            })
        st.dataframe(pd.DataFrame(call_rows), use_container_width=True, hide_index=True)

        # Token distribution by node
        if len(llm_calls) > 1:
            tok_by_node: dict[str, int] = defaultdict(int)
            for c in llm_calls:
                tok_by_node[c.get("node_name") or "unknown"] += (c.get("total_tokens") or 0)
            if tok_by_node:
                st.caption("Token usage by node")
                tok_df = pd.DataFrame(
                    [{"Node": k, "Tokens": v} for k, v in tok_by_node.items()]
                ).set_index("Node")
                st.bar_chart(tok_df)

        # Expandable detail per call
        st.caption("Click to expand individual LLM call details:")
        for i, c in enumerate(llm_calls):
            label = f"Call #{i+1} — {c.get('node_name', '')} / {c.get('agent_name', '')} ({c.get('latency_ms', 0):.0f}ms)"
            with st.expander(label):
                st.markdown("**System Prompt:**")
                st.code(c.get("system_prompt") or "(none)", language="text")
                st.markdown("**User Prompt:**")
                st.code(c.get("user_prompt") or "(none)", language="text")
                st.markdown("**Response:**")
                st.code(c.get("response_text") or "(none)", language="text")
                if c.get("error"):
                    st.error(f"Error: {c['error']}")
    else:
        st.caption("No LLM calls recorded (pipeline may have run in deterministic/CPU-only mode).")

    # ── Section F: Maintenance ──
    st.divider()
    col_purge, col_delete = st.columns(2)
    with col_purge:
        if st.button("🗑️ Purge old runs (keep latest 20)"):
            deleted = trace_db.purge_old_runs(keep_latest=20)
            st.success(f"Purged {deleted} old run(s).")
            st.rerun()
    with col_delete:
        if st.button("❌ Delete this run"):
            trace_db.delete_run(selected_id)
            st.success("Run deleted.")
            st.rerun()

    # ── Existing data lineage view ──
    st.divider()
    _render_data_lineage()


def _render_data_lineage() -> None:
    """Show obligation → mapping → assessment → risk chains (original Tab 5 content)."""
    classified = st.session_state.get("classified_obligations", [])
    if not classified:
        return

    st.subheader("🔗 Data Lineage Chains")
    st.caption("End-to-end traceability from obligation through mapping, coverage, and risk.")

    mappings = st.session_state.get("obligation_mappings", [])
    assessments = st.session_state.get("coverage_assessments", [])
    risks = st.session_state.get("scored_risks", [])

    mapping_lookup: dict[str, list[dict]] = defaultdict(list)
    for m in mappings:
        mapping_lookup[m.get("citation", "")].append(m)
    assessment_lookup: dict[str, list[dict]] = defaultdict(list)
    for a in assessments:
        assessment_lookup[a.get("citation", "")].append(a)
    risk_lookup: dict[str, list[dict]] = defaultdict(list)
    for r in risks:
        risk_lookup[r.get("source_citation", "")].append(r)

    by_subpart: dict[str, list[dict]] = defaultdict(list)
    for ob in classified:
        by_subpart[ob.get("subpart", "Unknown")].append(ob)

    for subpart in sorted(by_subpart.keys()):
        obs = by_subpart[subpart]
        with st.expander(f"📂 {subpart} ({len(obs)} obligations)"):
            for ob in obs:
                cit = ob.get("citation", "")
                cat = ob.get("obligation_category", "")
                crit = ob.get("criticality_tier", "")

                st.markdown(f"**{cit}** — {cat} ({crit})")

                ob_mappings = mapping_lookup.get(cit, [])
                if ob_mappings:
                    for m in ob_mappings:
                        st.markdown(f"  → APQC: {m.get('apqc_hierarchy_id', '')} — {m.get('apqc_process_name', '')}")

                ob_assessments = assessment_lookup.get(cit, [])
                if ob_assessments:
                    for a in ob_assessments:
                        coverage = a.get("overall_coverage", "")
                        ctrl = a.get("control_id", "None")
                        st.markdown(f"  → Coverage: {coverage} (Control: {ctrl})")

                ob_risks = risk_lookup.get(cit, [])
                if ob_risks:
                    for r in ob_risks:
                        rating = r.get("inherent_risk_rating", "")
                        st.markdown(f"  → Risk: {r.get('risk_id', '')} — {rating} — {r.get('risk_description', '')[:80]}")

                st.markdown("---")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
