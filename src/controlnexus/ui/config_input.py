"""Config input orchestrator — three sub-tabs for providing a DomainConfig.

Renders sub-tabs inside the Modular tab:
  1. **Select Profile** — pick from existing YAML profiles
  2. **Build from Form** — guided multi-step wizard
  3. **Import from Excel** — upload a register and get a proposed config

All three sub-tabs converge on the same output: a validated ``DomainConfig``
stored in ``st.session_state["wizard_active_config"]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from controlnexus.core.domain_config import DomainConfig, load_domain_config


# ── Caching ───────────────────────────────────────────────────────────────────

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

    _PROFILES_DIR = candidates[0]
    return _PROFILES_DIR


@st.cache_data(show_spinner="Loading config\u2026")
def _load_config(path_str: str) -> dict[str, Any]:
    """Load and cache a DomainConfig, returning its model_dump()."""
    config = load_domain_config(Path(path_str))
    return config.model_dump()


# ── Sub-tab 1: Select Profile ─────────────────────────────────────────────────


def _render_select_profile() -> DomainConfig | None:
    """Profile selector + optional YAML upload."""
    col_select, col_upload = st.columns([3, 2])

    with col_select:
        profiles = sorted(_profiles_dir().glob("*.yaml"))
        if not profiles:
            st.warning("No config profiles found in `config/profiles/`.")
            return None

        selected_path = st.selectbox(
            "Select config profile",
            profiles,
            format_func=lambda p: p.stem.replace("_", " ").replace("-", " ").title(),
            key="ci_select_profile",
        )

    with col_upload:
        uploaded = st.file_uploader(
            "\u2026or upload a custom YAML",
            type=["yaml", "yml"],
            help="Upload a DomainConfig YAML file for a custom organization.",
            key="ci_upload_yaml",
        )

    config_path: Path | None = None
    if uploaded is not None:
        import tempfile

        tmp = Path(tempfile.gettempdir()) / f"controlforge_upload_{uploaded.name}"
        tmp.write_bytes(uploaded.getvalue())
        config_path = tmp
    elif selected_path:
        config_path = selected_path

    if config_path is None:
        return None

    try:
        config_data = _load_config(str(config_path))
        config = DomainConfig(**config_data)
        st.session_state["wizard_config_path"] = str(config_path)
        return config
    except Exception as e:
        st.error(f"Config validation error: {e}")
        return None


# ── Config preview (shared) ───────────────────────────────────────────────────


def render_config_preview(config: DomainConfig) -> None:
    """Display a compact preview of a DomainConfig."""
    import pandas as pd

    col1, col2, col3 = st.columns(3)
    col1.metric("Control Types", len(config.control_types))
    col2.metric("Business Units", len(config.business_units))
    col3.metric("Process Areas", len(config.process_areas))

    with st.expander("Config Details", expanded=False):
        st.markdown("**Control Types:**")
        type_data = [
            {
                "Name": ct.name,
                "Code": ct.code or "(auto)",
                "Min Frequency": ct.min_frequency_tier or "\u2014",
            }
            for ct in config.control_types
        ]
        st.dataframe(pd.DataFrame(type_data), width="stretch", hide_index=True)

        if config.business_units:
            st.markdown("**Business Units:**")
            bu_data = [
                {
                    "ID": bu.id,
                    "Name": bu.name,
                    "Key Types": ", ".join(bu.key_control_types[:3]),
                }
                for bu in config.business_units
            ]
            st.dataframe(pd.DataFrame(bu_data), width="stretch", hide_index=True)

        if config.process_areas:
            st.markdown("**Process Areas:**")
            pa_data = [
                {
                    "ID": pa.id,
                    "Name": pa.name,
                    "Risk Multiplier": pa.risk_profile.multiplier,
                }
                for pa in config.process_areas
            ]
            st.dataframe(pd.DataFrame(pa_data), width="stretch", hide_index=True)


# ── Main entry point ──────────────────────────────────────────────────────────


def render_config_input() -> DomainConfig | None:
    """Render the Organization Config section — profile selector only.

    Build-from-Form and Import-from-Excel have moved to the Control Builder tab.
    Returns the active DomainConfig, or None if no config is ready.
    """
    st.markdown("### Organization Config")
    st.caption(
        "Select a saved profile below, or use the **Control Builder** tab to "
        "create a new configuration from scratch."
    )

    # Check if a config was activated from the Control Builder
    builder_config = st.session_state.get("wizard_active_config")
    if builder_config:
        try:
            config = DomainConfig(**builder_config)
            st.success(f"Using config: **{config.name}**")
            render_config_preview(config)
            if st.button("Change config", key="ci_change_config"):
                st.session_state.pop("wizard_active_config", None)
                st.rerun()
            return config
        except Exception:
            pass

    config = _render_select_profile()

    if config is not None:
        st.session_state["wizard_active_config"] = config.model_dump()
        st.markdown("---")
        render_config_preview(config)

    return config
