"""ControlNexus Streamlit Dashboard.

Main entry point for the four-tab web UI:
  1. Analysis — upload controls Excel, run gap analysis, view dashboard
  2. Playground — interactive agent testing environment
  3. Evaluation — view evaluation reports for generated controls
  4. ControlForge — configuration explorer and section runner

Launch:
    streamlit run src/controlnexus/ui/app.py
"""

from __future__ import annotations

import streamlit as st

from controlnexus.ui.styles import get_masthead_html, load_custom_css


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
        st.session_state.active_tab = "Analysis"

    # Masthead
    st.markdown(get_masthead_html(st.session_state.active_tab), unsafe_allow_html=True)

    # Four main tabs
    tab_analysis, tab_playground, tab_evaluation, tab_controlforge = st.tabs(
        ["Analysis", "Playground", "Evaluation", "ControlForge"]
    )

    with tab_analysis:
        _render_analysis_tab()

    with tab_playground:
        _render_playground_tab()

    with tab_evaluation:
        _render_evaluation_tab()

    with tab_controlforge:
        _render_controlforge_tab()


# -- Tab Renderers -------------------------------------------------------------


def _render_analysis_tab() -> None:
    """Analysis tab: upload, run scanners, view gap dashboard."""
    st.markdown(
        '<div class="report-title">Control Ecosystem Analysis</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Upload your control population, run gap analysis, and review findings"
        "</div>",
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


def _render_playground_tab() -> None:
    """Playground tab: interactive agent testing."""
    st.markdown(
        '<div class="report-title">Agent Playground</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Interactive testing environment for individual agents"
        "</div>",
        unsafe_allow_html=True,
    )

    from controlnexus.ui.playground import render_playground

    render_playground()


def _render_controlforge_tab() -> None:
    """ControlForge tab: browse config, run pipeline."""
    from controlnexus.ui.controlforge_tab import render_controlforge

    render_controlforge()


def _render_evaluation_tab() -> None:
    """Evaluation tab: display eval report if available."""
    st.markdown(
        '<div class="report-title">Evaluation Dashboard</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Quality scores for generated controls across 4 dimensions"
        "</div>",
        unsafe_allow_html=True,
    )

    eval_report = st.session_state.get("eval_report")

    if eval_report is not None:
        from controlnexus.ui.renderers.eval_dashboard import render_eval_dashboard

        render_eval_dashboard(eval_report)
    else:
        st.info(
            "No evaluation report available yet. "
            "Run the remediation pipeline and evaluation harness to generate one, "
            "or load one from a JSON file below."
        )

        _render_eval_loader()


def _render_eval_loader() -> None:
    """Allow loading an eval report from JSON."""
    import json

    from controlnexus.evaluation.models import EvalReport

    uploaded = st.file_uploader(
        "Upload Eval Report JSON",
        type=["json"],
        key="eval_json_upload",
    )

    if uploaded is not None:
        try:
            data = json.load(uploaded)
            report = EvalReport.model_validate(data)
            st.session_state["eval_report"] = report
            st.success("Eval report loaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to load eval report: {e}")


if __name__ == "__main__":
    main()
