"""ControlForge Modular — Streamlit tab for config-driven control generation.

Users select or upload an organization config YAML, optionally customize
distribution weights, then generate controls via the modular graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from controlnexus.core.domain_config import DomainConfig, load_domain_config
from controlnexus.core.events import EventEmitter, EventType, PipelineEvent
from controlnexus.graphs.forge_modular_graph import build_forge_graph, set_emitter
from controlnexus.ui.components.data_table import render_data_table


# ── Streamlit event listener ──────────────────────────────────────────────────


class StreamlitEventListener:
    """Maps pipeline events to st.status() live-feed updates."""

    def __init__(self, status: Any) -> None:
        self._status = status

    def __call__(self, event: PipelineEvent) -> None:
        et = event.event_type
        msg = event.message

        if et == EventType.PIPELINE_STARTED:
            self._status.write(f"\U0001F680 Pipeline started: {msg}")
        elif et == EventType.CONTROL_STARTED:
            idx = event.data.get("index", "?")
            total = event.data.get("total", "?")
            self._status.write(f"\n\U0001F4CB Control {idx}/{total}: {msg}")
        elif et == EventType.AGENT_STARTED:
            self._status.write(f"\u23F3 {msg} started")
        elif et == EventType.AGENT_COMPLETED:
            self._status.write(f"\u2713 {msg}")
        elif et == EventType.AGENT_FAILED:
            self._status.write(f"\u2717 {msg}")
        elif et == EventType.VALIDATION_PASSED:
            self._status.write(f"\u2713 {msg}")
        elif et == EventType.VALIDATION_FAILED:
            self._status.write(f"\u2717 {msg}")
        elif et == EventType.AGENT_RETRY:
            self._status.write(f"\u27F3 {msg}")
        elif et == EventType.TOOL_CALLED:
            self._status.write(f"\U0001F527 {msg}")
        elif et == EventType.TOOL_COMPLETED:
            pass  # tool completion is included in agent completed message
        elif et == EventType.CONTROL_COMPLETED:
            self._status.write(f"\u2714\uFE0F {msg}")
        elif et == EventType.PIPELINE_COMPLETED:
            self._status.update(label=f"\u2705 {msg}", state="complete", expanded=True)


# ── Config resolution ─────────────────────────────────────────────────────────

_PROFILES_DIR: Path | None = None


def _profiles_dir() -> Path:
    """Resolve the config/profiles directory."""
    global _PROFILES_DIR
    if _PROFILES_DIR is not None:
        return _PROFILES_DIR

    candidates = [
        Path.cwd() / "config" / "profiles",
        Path(__file__).resolve().parents[3] / "config" / "profiles",
    ]
    for c in candidates:
        if c.is_dir():
            _PROFILES_DIR = c
            return c

    # Fallback — return first candidate even if it doesn't exist
    _PROFILES_DIR = candidates[0]
    return _PROFILES_DIR


@st.cache_data(show_spinner="Loading config…")
def _load_config(path_str: str) -> dict[str, Any]:
    """Load and cache a DomainConfig, returning its model_dump()."""
    config = load_domain_config(Path(path_str))
    return config.model_dump()


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

    # ── Config selection ──────────────────────────────────────────────────
    st.markdown("### Organization Config")

    col_select, col_upload = st.columns([3, 2])

    with col_select:
        profiles = sorted(_profiles_dir().glob("*.yaml"))
        if not profiles:
            st.warning("No config profiles found in `config/profiles/`.")
            return

        selected_path = st.selectbox(
            "Select config profile",
            profiles,
            format_func=lambda p: p.stem.replace("_", " ").replace("-", " ").title(),
        )

    with col_upload:
        uploaded = st.file_uploader(
            "…or upload a custom YAML",
            type=["yaml", "yml"],
            help="Upload a DomainConfig YAML file for a custom organization.",
        )

    # Determine which config to use
    config_path: Path | None = None
    if uploaded is not None:
        # Write to a temp location and load
        import tempfile

        tmp = Path(tempfile.gettempdir()) / f"controlforge_upload_{uploaded.name}"
        tmp.write_bytes(uploaded.getvalue())
        config_path = tmp
    elif selected_path:
        config_path = selected_path

    if config_path is None:
        return

    # Load and validate
    try:
        config_data = _load_config(str(config_path))
        config = DomainConfig(**config_data)
    except Exception as e:
        st.error(f"Config validation error: {e}")
        return

    # ── Config preview ────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Control Types", len(config.control_types))
    col2.metric("Business Units", len(config.business_units))
    col3.metric("Process Areas", len(config.process_areas))

    with st.expander("Config Details", expanded=False):
        st.markdown("**Control Types:**")
        type_data = [{"Name": ct.name, "Code": ct.code or "(auto)", "Min Frequency": ct.min_frequency_tier or "—"}
                     for ct in config.control_types]
        st.dataframe(pd.DataFrame(type_data), width="stretch", hide_index=True)

        if config.business_units:
            st.markdown("**Business Units:**")
            bu_data = [{"ID": bu.id, "Name": bu.name, "Key Types": ", ".join(bu.key_control_types[:3])}
                       for bu in config.business_units]
            st.dataframe(pd.DataFrame(bu_data), width="stretch", hide_index=True)

        if config.process_areas:
            st.markdown("**Process Areas:**")
            pa_data = [{"ID": pa.id, "Name": pa.name, "Risk Multiplier": pa.risk_profile.multiplier}
                       for pa in config.process_areas]
            st.dataframe(pd.DataFrame(pa_data), width="stretch", hide_index=True)

    # ── Generation settings ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Generation Settings")

    target_count = st.number_input(
        "Number of controls to generate",
        min_value=1,
        max_value=500,
        value=10,
    )

    llm_enabled = st.toggle(
        "Enable LLM Generation",
        value=False,
        help="Uses LLM agents for richer control output. Requires API credentials (ICA/OpenAI/Anthropic).",
    )
    if llm_enabled:
        from controlnexus.core.transport import build_client_from_env

        if build_client_from_env() is None:
            st.warning(
                "No LLM credentials found. Set ICA_API_KEY, OPENAI_API_KEY, or "
                "ANTHROPIC_API_KEY environment variables. Generation will use "
                "deterministic fallback."
            )

    # Optional distribution customization
    distribution_config: dict[str, Any] | None = None

    with st.expander("Customize Distribution", expanded=False):
        st.caption("Adjust relative weights for control type and section emphasis. Leave defaults for even/risk-weighted distribution.")

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

        section_weights: dict[str, float] = {}
        section_changed = False

        if config.process_areas:
            st.markdown("**Section Emphasis:**")
            s_cols = st.columns(min(len(config.process_areas), 4))
            for i, pa in enumerate(config.process_areas):
                with s_cols[i % len(s_cols)]:
                    w = st.slider(
                        f"{pa.id}: {pa.name[:20]}",
                        0.0, 10.0,
                        float(pa.risk_profile.multiplier),
                        0.5,
                        key=f"sw_{pa.id}",
                    )
                    section_weights[pa.id] = w
                    if w != pa.risk_profile.multiplier:
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
                }
                if distribution_config:
                    input_state["distribution_config"] = distribution_config

                result = graph.invoke(input_state)
            finally:
                # Reset to no-op emitter so other tabs aren't affected
                set_emitter(EventEmitter())

        payload = result.get("plan_payload", {})
        records = payload.get("final_records", [])
        st.session_state["modular_result"] = payload

        st.success(f"Generated **{payload.get('total_controls', 0)}** controls for **{payload.get('config_name', '')}**")

        # Show tool usage summary if any tools were called
        tool_log = result.get("tool_calls_log", [])
        if tool_log:
            with st.expander(f"Tool Usage ({len(tool_log)} calls)", expanded=False):
                st.dataframe(pd.DataFrame(tool_log), hide_index=True)

    # ── Display results ───────────────────────────────────────────────────
    payload = st.session_state.get("modular_result")
    if payload:
        records = payload.get("final_records", [])
        if records:
            st.markdown("### Generated Controls")

            # Summary metrics
            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("Total Controls", len(records))
            types_used = set(r.get("control_type", "") for r in records)
            mcol2.metric("Control Types Used", len(types_used))
            bus_used = set(r.get("business_unit_name", "") for r in records)
            mcol3.metric("Business Units Used", len(bus_used))

            # All available columns for the toggler
            all_cols = [
                "control_id", "hierarchy_id", "leaf_name", "selected_level_1",
                "selected_level_2", "business_unit_id", "business_unit_name",
                "who", "what", "when", "frequency", "where", "why",
                "full_description", "quality_rating", "evidence",
            ]

            render_data_table(
                records=records,
                default_columns=[
                    "control_id", "business_unit_name", "selected_level_1",
                    "selected_level_2", "frequency", "full_description",
                ],
                all_columns=all_cols,
                key="modular_controls",
                export_filename=f"{payload.get('config_name', 'controls')}_controls.csv",
            )
