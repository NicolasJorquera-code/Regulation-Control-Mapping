"""Analysis pipeline execution with progress display."""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st
import yaml

from controlnexus.analysis.pipeline import run_analysis
from controlnexus.core.models import SectionProfile

logger = logging.getLogger(__name__)


def _load_section_profiles(config_dir: Path) -> dict[str, SectionProfile]:
    """Load section profiles from config/sections/*.yaml."""
    profiles: dict[str, SectionProfile] = {}
    sections_dir = config_dir / "sections"
    if not sections_dir.exists():
        return profiles

    for yaml_path in sorted(sections_dir.glob("section_*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text())
            if isinstance(data, dict):
                section_id = yaml_path.stem.replace("section_", "")
                profiles[section_id] = SectionProfile.model_validate(data)
        except Exception:
            logger.warning("Failed to load %s", yaml_path, exc_info=True)
    return profiles


def render_analysis_runner() -> None:
    """Render the analysis execution controls and run the pipeline."""
    controls = st.session_state.get("controls", [])

    if not controls:
        st.warning("Upload a controls Excel file first (Analysis tab).")
        return

    st.markdown(f"**{len(controls)} controls loaded.** Ready to run analysis.")

    # Config directory
    config_dir = Path("config")
    if not config_dir.exists():
        config_dir = Path(__file__).resolve().parents[4] / "config"

    run_btn = st.button("Run Gap Analysis", type="primary", use_container_width=True)

    if run_btn:
        status = st.status("Running gap analysis...", expanded=True)

        try:
            status.write("Loading section profiles...")
            profiles = _load_section_profiles(config_dir)
            st.session_state["section_profiles"] = profiles
            status.write(f"Loaded {len(profiles)} section profile(s)")

            status.write("Running 4 scanners (regulatory, balance, frequency, evidence)...")
            gap_report = run_analysis(controls, profiles)
            st.session_state["gap_report"] = gap_report

            status.write(f"Overall score: **{gap_report.overall_score}**/100")
            status.update(label="Analysis Complete", state="complete", expanded=False)

            st.success(f"Analysis complete: {gap_report.summary}")
            st.rerun()

        except Exception as e:
            status.update(label="Analysis Failed", state="error")
            st.error(f"Error: {e}")
            logger.exception("Analysis pipeline error")
