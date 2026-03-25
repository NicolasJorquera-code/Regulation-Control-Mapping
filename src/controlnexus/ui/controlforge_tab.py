"""ControlForge tab: section profile browser, global config viewer, pipeline runner.

Sub-tabs:
  1. Section Profiles — browse risk, affinity, registry, exemplars per section
  2. Global Config — taxonomy table, business units, placement/methods, standards
  3. Run Section — execute control generation pipeline
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import streamlit as st


def render_controlforge() -> None:
    """Main entry point for the ControlForge tab."""
    st.markdown(
        '<div class="report-title">ControlForge</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Configuration Explorer &amp; Section Runner"
        "</div>",
        unsafe_allow_html=True,
    )

    sub_profiles, sub_config, sub_run = st.tabs(
        ["Section Profiles", "Global Config", "Run Section"]
    )

    with sub_profiles:
        _render_section_profiles_subtab()
    with sub_config:
        _render_global_config_subtab()
    with sub_run:
        _render_run_section_subtab()


# -- Helpers ------------------------------------------------------------------


def _resolve_config_dir() -> Path:
    """Locate the config/ directory relative to the project root."""
    config_dir = Path("config")
    if config_dir.exists():
        return config_dir
    # src/controlnexus/ui/controlforge_tab.py -> parents[3] = project root
    return Path(__file__).resolve().parents[3] / "config"


@st.cache_data(show_spinner="Loading section profiles...")
def _get_cached_profiles(config_dir_str: str) -> dict[str, Any]:
    """Load all section profiles (cached). Uses str path for hashability."""
    from controlnexus.core.config import load_all_section_profiles

    profiles = load_all_section_profiles(Path(config_dir_str))
    # Convert to dicts for cache serialisation safety
    return {sid: p.model_dump() for sid, p in profiles.items()}


@st.cache_data(show_spinner="Loading taxonomy...")
def _get_cached_taxonomy(path_str: str) -> dict[str, Any]:
    from controlnexus.core.config import load_taxonomy_catalog

    catalog = load_taxonomy_catalog(Path(path_str))
    return catalog.model_dump()


@st.cache_data(show_spinner="Loading standards...")
def _get_cached_standards(path_str: str) -> dict[str, Any]:
    from controlnexus.core.config import load_standards

    return load_standards(Path(path_str))


@st.cache_data(show_spinner="Loading placement methods...")
def _get_cached_placement_methods(path_str: str) -> dict[str, Any]:
    from controlnexus.core.config import load_placement_methods

    return load_placement_methods(Path(path_str))


# -- Sub-tab 1: Section Profiles ---------------------------------------------


def _render_section_profiles_subtab() -> None:
    """Browse individual section profiles (1-13)."""
    config_dir = _resolve_config_dir()

    try:
        profiles_data = _get_cached_profiles(str(config_dir))
    except Exception as e:
        st.error(f"Failed to load section profiles: {e}")
        return

    # Reconstruct SectionProfile objects for typed access
    from controlnexus.core.models import SectionProfile

    profiles = {sid: SectionProfile(**data) for sid, data in profiles_data.items()}

    # Build human-readable labels
    profile_labels = {
        sid: f"Section {p.section_id} \u2014 {p.domain.replace('_', ' ').title()}"
        for sid, p in sorted(profiles.items(), key=lambda x: int(x[0]))
    }

    selected_id = st.selectbox(
        "Select Section",
        options=list(profile_labels.keys()),
        format_func=lambda x: profile_labels[x],
        key="controlforge_section_select",
    )

    if selected_id is None:
        return

    profile = profiles[selected_id]

    _render_risk_profile(profile)
    st.markdown("---")
    _render_affinity_matrix(profile)
    st.markdown("---")
    _render_domain_registry(profile)
    st.markdown("---")
    _render_exemplar_controls(profile)


def _render_risk_profile(profile: Any) -> None:
    """Display the 4 risk profile metrics + rationale."""
    st.markdown("### Risk Profile")

    rp = profile.risk_profile
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Inherent Risk", f"{rp.inherent_risk}/5")
    col2.metric("Regulatory Intensity", f"{rp.regulatory_intensity}/5")
    col3.metric("Control Density", f"{rp.control_density}/5")
    col4.metric("Multiplier", f"{rp.multiplier:.1f}x")

    with st.expander("Risk Rationale", expanded=False):
        st.markdown(rp.rationale)


def _render_affinity_matrix(profile: Any) -> None:
    """Display affinity buckets as colored badge groups."""
    st.markdown("### Affinity Matrix")

    affinity = profile.affinity
    bucket_config = [
        ("HIGH", affinity.HIGH, "affinity-high"),
        ("MEDIUM", affinity.MEDIUM, "affinity-medium"),
        ("LOW", affinity.LOW, "affinity-low"),
        ("NONE", affinity.NONE, "affinity-none"),
    ]

    for bucket_name, items, css_class in bucket_config:
        if not items:
            continue
        badges_html = " ".join(
            f'<span class="carbon-tag {css_class}">{item}</span>' for item in items
        )
        st.markdown(f"**{bucket_name}** ({len(items)})")
        st.markdown(badges_html, unsafe_allow_html=True)


def _render_domain_registry(profile: Any) -> None:
    """Display 6 registry lists as collapsible expanders."""
    st.markdown("### Domain Registry")

    reg = profile.registry
    registry_fields = [
        ("Roles", reg.roles),
        ("Systems", reg.systems),
        ("Data Objects", reg.data_objects),
        ("Evidence Artifacts", reg.evidence_artifacts),
        ("Event Triggers", reg.event_triggers),
        ("Regulatory Frameworks", reg.regulatory_frameworks),
    ]

    for field_name, items in registry_fields:
        with st.expander(f"{field_name} ({len(items)})"):
            if not items:
                st.caption("No items defined.")
            else:
                for item in items:
                    st.markdown(f"- {item}")


def _render_exemplar_controls(profile: Any) -> None:
    """Display exemplar controls as expandable cards."""
    st.markdown("### Exemplar Controls")

    if not profile.exemplars:
        st.info("No exemplar controls defined for this section.")
        return

    for i, ex in enumerate(profile.exemplars):
        header = f"{ex.control_type} \u2014 {ex.placement} / {ex.method}"
        with st.expander(header, expanded=(i == 0)):
            st.markdown(f"**Description:** {ex.full_description}")
            col1, col2 = st.columns(2)
            col1.metric("Word Count", ex.word_count)
            col2.metric("Quality Rating", ex.quality_rating)


# -- Sub-tab 2: Global Config ------------------------------------------------


def _render_global_config_subtab() -> None:
    """Browse taxonomy, business units, placement/methods, standards."""
    config_dir = _resolve_config_dir()

    _render_taxonomy_table(config_dir)
    st.markdown("---")
    _render_business_units(config_dir)
    st.markdown("---")
    _render_placement_methods_tree(config_dir)
    st.markdown("---")
    _render_standards(config_dir)


def _render_taxonomy_table(config_dir: Path) -> None:
    """Render control types as a searchable dataframe."""
    st.markdown("### Control Type Taxonomy")

    try:
        catalog_data = _get_cached_taxonomy(str(config_dir / "taxonomy.yaml"))
    except Exception as e:
        st.error(f"Failed to load taxonomy: {e}")
        return

    control_types = catalog_data.get("control_types", [])
    rows = [
        {"Control Type": ct["control_type"], "Definition": ct["definition"]}
        for ct in control_types
    ]
    st.caption(f"{len(control_types)} control types defined")
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_business_units(config_dir: Path) -> None:
    """Render business units as expandable cards."""
    st.markdown("### Business Units")

    try:
        catalog_data = _get_cached_taxonomy(str(config_dir / "taxonomy.yaml"))
    except Exception as e:
        st.error(f"Failed to load business units: {e}")
        return

    bus = catalog_data.get("business_units", [])
    if not bus:
        st.info("No business units defined.")
        return

    st.caption(f"{len(bus)} business units defined")

    for bu in bus:
        with st.expander(f"{bu['business_unit_id']} \u2014 {bu['name']}"):
            st.markdown(f"**Description:** {bu['description']}")
            st.markdown(
                f"**Primary Sections:** {', '.join(bu.get('primary_sections', []))}"
            )
            st.markdown(
                f"**Key Control Types:** {', '.join(bu.get('key_control_types', []))}"
            )
            st.markdown(
                f"**Regulatory Exposure:** {', '.join(bu.get('regulatory_exposure', []))}"
            )


def _render_placement_methods_tree(config_dir: Path) -> None:
    """Render placement, methods, and control taxonomy tree."""
    st.markdown("### Placement & Method Taxonomy")

    try:
        pm_data = _get_cached_placement_methods(
            str(config_dir / "placement_methods.yaml")
        )
    except Exception as e:
        st.error(f"Failed to load placement methods: {e}")
        return

    placements = pm_data.get("placements", [])
    methods = pm_data.get("methods", [])
    st.markdown(f"**Placements:** {', '.join(placements)}")
    st.markdown(f"**Methods:** {', '.join(methods)}")

    st.markdown("---")
    st.markdown("**Control Taxonomy (Level 1 \u2192 Level 2):**")

    taxonomy = pm_data.get("control_taxonomy", {})
    l2_by_l1 = taxonomy.get("level_2_by_level_1", {})

    for level_1, level_2_list in l2_by_l1.items():
        with st.expander(f"{level_1} ({len(level_2_list)} control types)"):
            for ct in level_2_list:
                st.markdown(f"- {ct}")


def _render_standards(config_dir: Path) -> None:
    """Render the 5W standards, phrase bank, and quality ratings."""
    st.markdown("### Narrative Standards")

    try:
        standards_data = _get_cached_standards(str(config_dir / "standards.yaml"))
    except Exception as e:
        st.error(f"Failed to load standards: {e}")
        return

    # 5W definitions
    five_w = standards_data.get("five_w", {})
    if five_w:
        st.markdown("**5W Field Definitions:**")
        for field, definition in five_w.items():
            st.markdown(f"- **{field.upper()}:** {definition}")

    # Phrase bank
    phrase_bank = standards_data.get("phrase_bank", {})
    if phrase_bank:
        st.markdown("**Phrase Bank:**")
        for category, phrases in phrase_bank.items():
            with st.expander(
                f"{category.replace('_', ' ').title()} ({len(phrases)})"
            ):
                st.markdown(", ".join(phrases))

    # Quality ratings
    ratings = standards_data.get("quality_ratings", [])
    if ratings:
        arrow = " \u2192 "
        st.markdown(f"**Quality Ratings:** {arrow.join(ratings)}")


# -- Sub-tab 3: Run Section ---------------------------------------------------


def _resolve_project_root() -> Path:
    """Resolve the project root directory."""
    root = Path.cwd()
    if (root / "config").exists():
        return root
    return Path(__file__).resolve().parents[3]


def _load_apqc_from_disk() -> list[Any] | None:
    """Try to load APQC hierarchy from the default data/ path."""
    default_path = _resolve_project_root() / "data" / "APQC_Template.xlsx"
    if not default_path.exists():
        return None
    from controlnexus.hierarchy.parser import load_apqc_hierarchy

    return load_apqc_hierarchy(default_path)


def _render_run_section_subtab() -> None:
    """Pipeline execution sub-tab: load hierarchy, configure, run, download."""
    st.markdown("### Run Control Generation Pipeline")

    # -- APQC Data Source ------------------------------------------------------
    _render_apqc_loader()

    nodes = st.session_state.get("cf_apqc_nodes")
    if not nodes:
        return

    st.markdown("---")

    # -- Pipeline Configuration ------------------------------------------------
    available_sections = sorted(
        {n.top_section for n in nodes},
        key=lambda s: int(s) if s.isdigit() else float("inf"),
    )

    col1, col2 = st.columns(2)
    with col1:
        selected_sections = st.multiselect(
            "Target Sections",
            options=available_sections,
            default=available_sections[:1] if available_sections else [],
            key="cf_run_sections",
        )
    with col2:
        target_count = st.number_input(
            "Target Control Count",
            min_value=1,
            max_value=10000,
            value=100,
            key="cf_run_target_count",
        )

    col3, col4 = st.columns(2)
    with col3:
        dry_run_limit = st.number_input(
            "Dry Run Limit (0 = no limit)",
            min_value=0,
            max_value=10000,
            value=20,
            help="Cap output for testing. 0 disables the limit.",
            key="cf_run_dry_limit",
        )
    with col4:
        max_parallel = st.number_input(
            "Max Parallel Controls (LLM)",
            min_value=1,
            max_value=10,
            value=1,
            help="Concurrency for LLM enrichment calls.",
            key="cf_run_max_parallel",
        )

    run_btn = st.button(
        "Run Pipeline",
        type="primary",
        width="stretch",
        disabled=len(selected_sections) == 0,
        key="cf_run_btn",
    )

    if run_btn:
        _execute_pipeline(
            nodes=nodes,
            selected_sections=selected_sections,
            target_count=target_count,
            dry_run_limit=dry_run_limit if dry_run_limit > 0 else None,
            max_parallel=max_parallel,
        )

    # -- Display previous results if available ---------------------------------
    result = st.session_state.get("cf_pipeline_result")
    if result:
        st.markdown("---")
        _display_pipeline_results(result)


def _render_apqc_loader() -> None:
    """Handle APQC hierarchy loading from disk or file upload."""
    # Try auto-loading from disk on first visit
    if "cf_apqc_nodes" not in st.session_state:
        nodes = _load_apqc_from_disk()
        if nodes:
            st.session_state["cf_apqc_nodes"] = nodes

    nodes = st.session_state.get("cf_apqc_nodes")
    if nodes:
        leaf_count = sum(1 for n in nodes if n.is_leaf)
        sections = sorted({n.top_section for n in nodes}, key=lambda s: int(s) if s.isdigit() else float("inf"))
        st.success(
            f"APQC hierarchy loaded: **{len(nodes)}** nodes, **{leaf_count}** leaves, "
            f"**{len(sections)}** sections ({', '.join(sections)})"
        )
    else:
        st.warning("No APQC hierarchy loaded. Upload a template or place `APQC_Template.xlsx` in `data/`.")

    uploaded = st.file_uploader(
        "Upload APQC Template",
        type=["xlsx", "csv"],
        key="cf_apqc_upload",
        help="Upload an APQC Process Classification Framework Excel template or CSV export.",
    )
    if uploaded is not None:
        try:
            from controlnexus.hierarchy.parser import load_apqc_hierarchy_from_bytes

            new_nodes = load_apqc_hierarchy_from_bytes(uploaded.getvalue(), uploaded.name)
            st.session_state["cf_apqc_nodes"] = new_nodes
            st.rerun()
        except Exception as e:
            st.error(f"Failed to parse uploaded file: {e}")


def _execute_pipeline(
    nodes: list[Any],
    selected_sections: list[str],
    target_count: int,
    dry_run_limit: int | None,
    max_parallel: int,
) -> None:
    """Build RunConfig, run the orchestrator, store results."""
    from controlnexus.core.models import (
        CheckpointConfig,
        ConcurrencyConfig,
        InputConfig,
        OutputConfig,
        RunConfig,
        ScopeConfig,
        SizingConfig,
        TransportConfig,
    )
    from controlnexus.pipeline.orchestrator import Orchestrator

    project_root = _resolve_project_root()
    config_dir = _resolve_config_dir()
    run_id = f"ui_run_{'_'.join(selected_sections)}"

    run_config = RunConfig(
        run_id=run_id,
        scope=ScopeConfig(sections=selected_sections),
        sizing=SizingConfig(
            target_count=target_count,
            dry_run_limit=dry_run_limit,
        ),
        input=InputConfig(),
        checkpoint=CheckpointConfig(),
        transport=TransportConfig(),
        concurrency=ConcurrencyConfig(max_parallel_controls=max_parallel),
        output=OutputConfig(),
    )

    orchestrator = Orchestrator(run_config, project_root)
    status = st.status("Running pipeline...", expanded=True)

    try:
        result = asyncio.run(
            orchestrator.execute_planning(
                config_dir=config_dir,
                verbose=True,
                progress_callback=lambda msg: status.write(msg),
                preloaded_nodes=nodes,
            )
        )
        status.update(label="Pipeline Complete", state="complete", expanded=False)
        st.session_state["cf_pipeline_result"] = result
        st.rerun()

    except Exception as e:
        status.update(label="Pipeline Failed", state="error")
        st.error(f"Error: {e}")
        st.exception(e)


def _display_pipeline_results(result: Any) -> None:
    """Display PlanningResult with metrics, tables, and download buttons."""
    st.markdown("### Results")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Target Controls", result.target_controls)
    col2.metric("Generated", result.generated_controls)
    col3.metric("Selected Leaves", result.selected_leaves)
    col4.metric("LLM Enabled", "Yes" if result.llm_enabled else "No")

    # Section allocation
    with st.expander("Section Allocation"):
        alloc_rows = [
            {"Section": sid, "Controls Allocated": count}
            for sid, count in result.section_allocation.items()
        ]
        st.dataframe(alloc_rows, width="stretch", hide_index=True)

    # Section breakdown
    with st.expander("Section Breakdown"):
        st.dataframe(result.section_breakdown, width="stretch", hide_index=True)

    # Plan JSON
    with st.expander("Plan JSON (raw)"):
        from controlnexus.pipeline.orchestrator import planning_result_to_dict

        st.json(planning_result_to_dict(result))

    # Generated controls preview
    if getattr(result, "control_records", None):
        st.markdown("### Generated Controls")
        from controlnexus.export.excel import EXPORT_COLUMNS
        from controlnexus.ui.components.data_table import render_data_table

        export_rows = [rec.to_export_dict() for rec in result.control_records]
        render_data_table(
            records=export_rows,
            default_columns=["control_id", "leaf_name", "who", "what", "when", "why"],
            all_columns=EXPORT_COLUMNS,
            key="cf_pipeline_controls",
            export_filename=f"{result.run_id}__controls.csv",
        )

    # Download buttons
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if result.excel_path:
            excel_path = Path(result.excel_path)
            if excel_path.exists():
                st.download_button(
                    "Download Excel",
                    data=excel_path.read_bytes(),
                    file_name=excel_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                )
    with col_dl2:
        plan_path = Path(result.plan_path)
        if plan_path.exists():
            st.download_button(
                "Download Plan JSON",
                data=plan_path.read_bytes(),
                file_name=plan_path.name,
                mime="application/json",
                width="stretch",
            )
