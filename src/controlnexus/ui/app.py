"""ControlNexus Streamlit Dashboard.

Main entry point for the four-tab web UI:
  1. Control Builder — guided wizard for creating DomainConfig
  2. ControlForge Modular — config-driven control generation
  3. Analysis — upload controls Excel, run gap analysis, view dashboard
  4. Playground — interactive agent testing environment

Launch:
    streamlit run src/controlnexus/ui/app.py
"""

from __future__ import annotations

import logging
import sys

import streamlit as st

from controlnexus.ui.styles import get_masthead_html, load_custom_css

# ---------------------------------------------------------------------------
# Logging — route all controlnexus.* loggers to stderr so they appear in the
# terminal where Streamlit was launched.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
    stream=sys.stderr,
)
# Quiet noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


def main() -> None:
    """Application entry point."""
    st.set_page_config(
        page_title="ControlNexus",
        page_icon="",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    load_custom_css()

    # Session state defaults
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Control Builder"

    # Masthead
    st.markdown(get_masthead_html(st.session_state.active_tab), unsafe_allow_html=True)

    # Four main tabs
    tab_builder, tab_modular, tab_analysis, tab_playground = st.tabs(
        ["Control Builder", "ControlForge Modular", "Analysis", "Playground"]
    )

    with tab_builder:
        _render_control_builder_tab()

    with tab_modular:
        _render_modular_tab()

    with tab_analysis:
        _render_analysis_tab()

    with tab_playground:
        _render_playground_tab()


# -- Tab Renderers -------------------------------------------------------------


def _render_analysis_tab() -> None:
    """Analysis tab: upload, run scanners, view gap dashboard."""
    st.markdown(
        '<div class="report-title">Control Ecosystem Analysis</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">Upload your control population, run gap analysis, and review findings</div>',
        unsafe_allow_html=True,
    )

    from controlnexus.ui.components.upload import render_upload_widget

    render_upload_widget()

    st.markdown("---")

    from controlnexus.ui.components.analysis_runner import render_analysis_runner

    render_analysis_runner()

    # Show gap dashboard if report exists
    gap_report = st.session_state.get("gap_report")
    if gap_report is not None:
        st.markdown("---")
        st.markdown("### Gap Analysis Results")

        from controlnexus.ui.renderers.gap_dashboard import render_gap_dashboard

        render_gap_dashboard(gap_report)

    # Show remediation section if gaps have been accepted
    if st.session_state.get("accepted_gaps") is not None:
        st.markdown("---")

        from controlnexus.ui.components.remediation_runner import render_remediation_runner

        render_remediation_runner()


def _render_playground_tab() -> None:
    """Playground tab: interactive agent testing."""
    st.markdown(
        '<div class="report-title">Agent Playground</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">Interactive testing environment for individual agents</div>',
        unsafe_allow_html=True,
    )

    from controlnexus.ui.playground import render_playground

    render_playground()


def _render_control_builder_tab() -> None:
    """Control Builder tab: guided wizard for creating DomainConfig."""
    from controlnexus.ui.control_builder import render_control_builder_tab

    render_control_builder_tab()


def _render_modular_tab() -> None:
    """ControlForge Modular tab: config-driven generation."""
    from controlnexus.ui.modular_tab import render_modular_tab

    render_modular_tab()


if __name__ == "__main__":
    main()
