"""ControlForge Modular — Streamlit tab for config-driven control generation.

Users select or upload an organization config YAML, optionally customize
distribution weights, then generate controls via the modular graph.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from controlnexus.core.events import EventEmitter, EventType, PipelineEvent
from controlnexus.graphs.forge_modular_graph import build_forge_graph, set_emitter
from controlnexus.ui.components.data_table import render_data_table
from controlnexus.ui.config_input import render_config_input

logger = logging.getLogger(__name__)
# ── Streamlit event listener ──────────────────────────────────────────────────


class StreamlitEventListener:
    """Maps pipeline events to st.status() live-feed updates."""

    def __init__(self, status: Any) -> None:
        self._status = status

    def __call__(self, event: PipelineEvent) -> None:
        et = event.event_type
        msg = event.message

        if et == EventType.PIPELINE_STARTED:
            self._status.write(f"\U0001f680 Pipeline started: {msg}")
        elif et == EventType.CONTROL_STARTED:
            idx = event.data.get("index", "?")
            total = event.data.get("total", "?")
            self._status.write(f"\n\U0001f4cb Control {idx}/{total}: {msg}")
        elif et == EventType.AGENT_STARTED:
            self._status.write(f"\u23f3 {msg} started")
        elif et == EventType.AGENT_COMPLETED:
            self._status.write(f"\u2713 {msg}")
        elif et == EventType.AGENT_FAILED:
            self._status.write(f"\u2717 {msg}")
        elif et == EventType.VALIDATION_PASSED:
            self._status.write(f"\u2713 {msg}")
        elif et == EventType.VALIDATION_FAILED:
            self._status.write(f"\u2717 {msg}")
        elif et == EventType.AGENT_RETRY:
            self._status.write(f"\u27f3 {msg}")
        elif et == EventType.TOOL_CALLED:
            self._status.write(f"\U0001f527 {msg}")
        elif et == EventType.TOOL_COMPLETED:
            pass  # tool completion is included in agent completed message
        elif et == EventType.CONTROL_COMPLETED:
            self._status.write(f"\u2714\ufe0f {msg}")
        elif et == EventType.PIPELINE_COMPLETED:
            self._status.update(label=f"\u2705 {msg}", state="complete", expanded=True)


# ── Main render function ──────────────────────────────────────────────────────


def render_modular_tab() -> None:
    """Render the ControlForge Modular tab."""
    st.markdown(
        '<div class="report-title">ControlForge Modular</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Config-driven control generation — select an organization profile and generate controls"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Config input (Select Profile / Build from Form / Import from Excel) ──
    config = render_config_input()

    if config is None:
        return

    # Resolve config_path for the graph (needed for backward compat)
    config_path: Path | None = None
    if "ci_selected_path" in st.session_state:
        config_path = st.session_state["ci_selected_path"]
    else:
        # Write the active config to a temp file so the graph can load it
        import tempfile
        import yaml as _yaml

        tmp = Path(tempfile.gettempdir()) / f"controlforge_{config.name}.yaml"
        tmp.write_text(
            _yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        config_path = tmp

    if config_path is None:
        return

    # ── Config Summary ────────────────────────────────────────────────────
    with st.expander("Profile Summary", expanded=False):
        cols = st.columns(4)
        cols[0].metric("Control Types", len(config.control_types))
        cols[1].metric("Processes", len(config.processes))
        cols[2].metric("Risk Catalog", len(config.risk_catalog))
        cols[3].metric("L1 Categories", len(config.risk_level_1_categories))
        if config.risk_level_1_categories:
            st.caption(
                "Risk categories: "
                + ", ".join(f"**{c.name}** ({c.code})" for c in config.risk_level_1_categories)
            )

    # ── Quick Section Run ─────────────────────────────────────────────────
    _render_quick_section_run(config, config_path)

    # ── Full Generation (all sections) ────────────────────────────────────
    with st.expander("Full Generation (All Sections)", expanded=False):
        _render_full_generation(config, config_path)

    # ── Display full-run results ──────────────────────────────────────────
    _render_results(
        session_key="modular_result",
        table_key="modular_controls",
        csv_key="modular_export_csv",
        json_key="modular_export_json",
        config_name=config.name,
    )


# ── Quick Section Run ─────────────────────────────────────────────────────────


def _render_quick_section_run(config: Any, config_path: Path) -> None:
    """Generate controls for a single process (or legacy process area)."""
    st.markdown("---")
    st.markdown("### Quick Process Run")
    st.caption("Generate controls for a single process or APQC process area.")

    # Support both new processes and legacy process_areas
    processes = getattr(config, "processes", []) or []
    process_areas = getattr(config, "process_areas", []) or []
    items = processes or process_areas

    if not items:
        st.info("No processes defined in this config.")
        return

    col_sec, col_count = st.columns([3, 1])
    with col_sec:
        section_options = list(range(len(items)))
        selected_idx = st.selectbox(
            "Process",
            options=section_options,
            format_func=lambda i: f"{items[i].id} — {items[i].name}",
            key="qsr_section",
        )
    with col_count:
        qsr_count = st.number_input(
            "Controls",
            min_value=1,
            max_value=50,
            value=5,
            key="qsr_count",
        )

    qsr_llm = st.toggle(
        "Enable LLM Generation",
        value=False,
        key="qsr_llm",
        help="Uses LLM agents for richer output. Requires API credentials.",
    )
    if qsr_llm:
        from controlnexus.core.transport import build_client_from_env

        if build_client_from_env() is None:
            st.warning(
                "No LLM credentials found. Generation will use deterministic fallback."
            )

    selected_item = items[selected_idx]

    if st.button(
        f"Generate {qsr_count} controls for {selected_item.id}",
        type="primary",
        use_container_width=True,
        key="qsr_generate",
    ):
        with st.status(
            f"Generating {qsr_count} controls for {selected_item.id}: {selected_item.name}…",
            expanded=True,
        ) as status:
            emitter = EventEmitter()
            listener = StreamlitEventListener(status)
            emitter.on(listener)
            set_emitter(emitter)

            try:
                graph = build_forge_graph().compile()
                input_state: dict[str, Any] = {
                    "config_path": str(config_path),
                    "target_count": qsr_count,
                    "llm_enabled": qsr_llm,
                }
                # Use process_filter for new configs, section_filter for legacy
                if processes:
                    input_state["process_filter"] = selected_item.id
                else:
                    input_state["section_filter"] = selected_item.id
                result = graph.invoke(input_state, config={"recursion_limit": 300})
            finally:
                set_emitter(EventEmitter())

        payload = result.get("plan_payload", {})
        st.session_state["section_run_result"] = payload

        st.success(
            f"Generated **{payload.get('total_controls', 0)}** controls "
            f"for **{selected_item.id}: {selected_item.name}**"
        )

        tool_log = result.get("tool_calls_log", [])
        if tool_log:
            with st.expander(f"Tool Usage ({len(tool_log)} calls)", expanded=False):
                st.dataframe(pd.DataFrame(tool_log), hide_index=True)

    # Display section-run results
    _render_results(
        session_key="section_run_result",
        table_key="qsr_controls",
        csv_key="qsr_export_csv",
        json_key="qsr_export_json",
        config_name=config.name,
    )


# ── Full Generation ───────────────────────────────────────────────────────────


def _render_full_generation(config: Any, config_path: Path) -> None:
    """Full multi-section generation settings and execution."""
    target_count = st.number_input(
        "Number of controls to generate",
        min_value=1,
        max_value=500,
        value=10,
        key="full_gen_count",
    )

    llm_enabled = st.toggle(
        "Enable LLM Generation",
        value=False,
        help="Uses LLM agents for richer control output. Requires API credentials (ICA/OpenAI/Anthropic).",
        key="full_gen_llm",
    )
    if llm_enabled:
        from controlnexus.core.transport import build_client_from_env

        if build_client_from_env() is None:
            st.warning(
                "No LLM credentials found. Set ICA_API_KEY, OPENAI_API_KEY, or "
                "ANTHROPIC_API_KEY environment variables. Generation will use "
                "deterministic fallback."
            )

    # Generation mode toggle
    generation_mode = st.radio(
        "Generation Mode",
        options=["synthetic", "policy_first"],
        index=0,
        horizontal=True,
        help=(
            "**Synthetic**: Generate controls from catalog risks and config. "
            "**Policy First**: Ingest a policy document to derive risks "
            "(requires LLM — stub implementation)."
        ),
        key="full_gen_mode",
    )
    if generation_mode == "policy_first" and not llm_enabled:
        st.info("Policy-first mode works best with LLM enabled. Currently uses synthetic fallback.")

    # Optional distribution customization
    distribution_config: dict[str, Any] | None = None

    with st.expander("Customize Distribution", expanded=False):
        st.caption(
            "Adjust relative weights for control type and process emphasis. Leave defaults for even/risk-weighted distribution."
        )

        type_names = [ct.name for ct in config.control_types]
        type_weights: dict[str, float] = {}
        type_changed = False

        cols = st.columns(min(len(type_names), 3))
        for i, ct_name in enumerate(type_names):
            with cols[i % len(cols)]:
                w = st.slider(ct_name, 0.0, 10.0, 1.0, 0.5, key=f"tw_{ct_name}")
                type_weights[ct_name] = w
                if w != 1.0:
                    type_changed = True

        # Support both new processes and legacy process_areas
        processes = getattr(config, "processes", []) or []
        process_areas = getattr(config, "process_areas", []) or []
        items = processes or process_areas

        section_weights: dict[str, float] = {}
        section_changed = False

        if items:
            st.markdown("**Process Emphasis:**")
            s_cols = st.columns(min(len(items), 4))
            for i, item in enumerate(items):
                with s_cols[i % len(s_cols)]:
                    # Get default weight: from risk_profile multiplier (legacy) or 1.0 (new)
                    default_w = 1.0
                    if hasattr(item, "risk_profile") and hasattr(item.risk_profile, "multiplier"):
                        default_w = float(item.risk_profile.multiplier)
                    elif hasattr(item, "risks") and item.risks:
                        default_w = float(max(r.multiplier for r in item.risks))
                    w = st.slider(
                        f"{item.id}: {item.name[:20]}",
                        0.0,
                        10.0,
                        default_w,
                        0.5,
                        key=f"sw_{item.id}",
                    )
                    section_weights[item.id] = w
                    if w != default_w:
                        section_changed = True

        if type_changed or section_changed:
            distribution_config = {}
            if type_changed:
                distribution_config["type_weights"] = type_weights
            if section_changed:
                distribution_config["section_weights"] = section_weights

    # ── Generate ──────────────────────────────────────────────────────────
    st.markdown("---")

    if st.button("Generate Controls", type="primary", use_container_width=True):
        with st.status(f"Generating {target_count} controls\u2026", expanded=True) as status:
            # Wire up real-time event feed
            emitter = EventEmitter()
            listener = StreamlitEventListener(status)
            emitter.on(listener)
            set_emitter(emitter)

            try:
                graph = build_forge_graph().compile()
                input_state: dict[str, Any] = {
                    "config_path": str(config_path),
                    "target_count": target_count,
                    "llm_enabled": llm_enabled,
                    "generation_mode": generation_mode,
                }
                if distribution_config:
                    input_state["distribution_config"] = distribution_config

                result = graph.invoke(input_state, config={"recursion_limit": 300})
            finally:
                # Reset to no-op emitter so other tabs aren't affected
                set_emitter(EventEmitter())

        payload = result.get("plan_payload", {})
        records = payload.get("final_records", [])
        st.session_state["modular_result"] = payload

        st.success(
            f"Generated **{payload.get('total_controls', 0)}** controls for **{payload.get('config_name', '')}**"
        )

        # Show tool usage summary if any tools were called
        tool_log = result.get("tool_calls_log", [])
        if tool_log:
            with st.expander(f"Tool Usage ({len(tool_log)} calls)", expanded=False):
                st.dataframe(pd.DataFrame(tool_log), hide_index=True)


# ── Shared results display ────────────────────────────────────────────────────


def _render_results(
    session_key: str,
    table_key: str,
    csv_key: str,
    json_key: str,
    config_name: str,
) -> None:
    """Display generated controls from session state."""
    payload = st.session_state.get(session_key)
    if not payload:
        return
    records = payload.get("final_records", [])
    if not records:
        return

    st.markdown("### Generated Controls")

    # Summary metrics
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Total Controls", len(records))
    types_used = set(r.get("control_type", "") for r in records)
    mcol2.metric("Control Types Used", len(types_used))
    bus_used = set(r.get("business_unit_name", "") for r in records)
    mcol3.metric("Business Units Used", len(bus_used))
    processes_used = set(r.get("process_name", "") for r in records if r.get("process_name"))
    mcol4.metric("Processes", len(processes_used) if processes_used else "–")

    # Controls table
    all_cols = [
        "control_id", "hierarchy_id", "leaf_name",
        "selected_level_1", "selected_level_2",
        "business_unit_id", "business_unit_name",
        "process_id", "process_name",
        "risk_id", "risk_name", "risk_severity",
        "who", "what", "when", "frequency",
        "where", "why", "full_description",
        "quality_rating", "evidence",
    ]
    render_data_table(
        records=records,
        default_columns=[
            "control_id", "business_unit_name",
            "process_name", "risk_id",
            "selected_level_1", "selected_level_2",
            "frequency", "full_description",
        ],
        all_columns=all_cols,
        key=table_key,
        export_filename=f"{config_name}_controls.csv",
    )

    # Downloads
    import json as _json
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Download CSV",
            data=pd.DataFrame(records).to_csv(index=False),
            file_name=f"{config_name}_controls.csv",
            mime="text/csv",
            key=csv_key,
        )
    with dl2:
        st.download_button(
            "📥 Download JSON",
            data=_json.dumps(records, indent=2),
            file_name=f"{config_name}_controls.json",
            mime="application/json",
            key=json_key,
        )
