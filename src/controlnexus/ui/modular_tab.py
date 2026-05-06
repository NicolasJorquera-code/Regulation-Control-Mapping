"""ControlForge Modular — Streamlit tab for config-driven control generation.

Users select or upload an organization config YAML, optionally customize
distribution weights, then generate controls via the modular graph.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

from controlnexus.core.events import EventEmitter, EventType, PipelineEvent
from controlnexus.graphs.forge_modular_graph import build_forge_graph, set_emitter
from controlnexus.ui.components.data_table import render_data_table
from controlnexus.ui.config_input import render_config_input

logger = logging.getLogger(__name__)


KNOWLEDGE_BASE_TABS = [
    "Business Units",
    "Processes",
    "Risk Taxonomy (2-Tier)",
    "Control Taxonomy",
]


# ── Modular Knowledge Base data prep ──────────────────────────────────────────


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _placement_methods_path() -> Path:
    return _repo_root() / "config" / "placement_methods.yaml"


def _dash_if_empty(value: Any) -> Any:
    if value is None:
        return "—"
    if isinstance(value, str) and not value.strip():
        return "—"
    return value


def _format_employee_count(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return "—"
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: max(limit - 1, 0)].rstrip() + "…"


def _join_truncated(values: list[str], limit: int, separator: str = "; ") -> str:
    if not values:
        return "—"
    rendered = list(values[:limit])
    if len(values) > limit:
        rendered.append("…")
    return separator.join(rendered)


def _title_case_snake(value: str) -> str:
    return value.replace("_", " ").strip().title() if value else "—"


def _control_type_code(name: str, code: str = "") -> str:
    if code:
        return code
    letters = "".join(ch for ch in name if ch.isalpha())
    return letters[:3].upper() or "UNK"


def _processes_for_config(config: Any) -> tuple[list[Any], bool]:
    """Return displayable processes and whether the source is pivot-mode."""
    processes = list(getattr(config, "processes", []) or [])
    process_areas = list(getattr(config, "process_areas", []) or [])
    is_pivot = bool(processes and not process_areas)
    if processes:
        return processes, is_pivot
    return process_areas, False


def _owner_bu_ids_for_process(process: Any, config: Any) -> list[str]:
    owner_ids = list(getattr(process, "owner_bu_ids", []) or [])
    if owner_ids:
        return owner_ids

    process_id = str(getattr(process, "id", ""))
    return [
        str(getattr(bu, "id", ""))
        for bu in getattr(config, "business_units", []) or []
        if process_id and process_id in (getattr(bu, "primary_sections", []) or [])
    ]


def _process_hierarchy(process: Any, is_pivot: bool) -> str:
    if is_pivot:
        return str(_dash_if_empty(getattr(process, "hierarchy_id", "")))

    domain_metadata = getattr(process, "domain_metadata", {}) or {}
    apqc_id = domain_metadata.get("apqc_section_id", getattr(process, "apqc_section_id", ""))
    return str(_dash_if_empty(apqc_id or getattr(process, "hierarchy_id", "") or getattr(process, "id", "")))


def _process_registry(process: Any) -> Any:
    return getattr(process, "registry", None)


def prepare_business_units_table(config: Any) -> list[dict[str, Any]]:
    """Prepare Business Units rows for the Modular Knowledge Base."""
    processes, _is_pivot = _processes_for_config(config)
    process_counts: Counter[str] = Counter()
    for process in processes:
        for bu_id in _owner_bu_ids_for_process(process, config):
            process_counts[bu_id] += 1

    rows: list[dict[str, Any]] = []
    for bu in getattr(config, "business_units", []) or []:
        exposures = list(getattr(bu, "regulatory_exposure", []) or [])
        rows.append(
            {
                "Business Unit ID": getattr(bu, "id", ""),
                "Business Unit": getattr(bu, "name", ""),
                "Head": _dash_if_empty(getattr(bu, "head_role", "")),
                "Employees": _format_employee_count(getattr(bu, "employee_count", None)),
                "Process Count": process_counts.get(getattr(bu, "id", ""), 0),
                "Description": getattr(bu, "description", ""),
                "Risk Profile": _join_truncated(exposures, 5),
            }
        )
    return rows


def _prepare_process_view_models(config: Any) -> list[dict[str, Any]]:
    processes, is_pivot = _processes_for_config(config)
    bu_lookup = {
        getattr(bu, "id", ""): getattr(bu, "name", "")
        for bu in getattr(config, "business_units", []) or []
    }
    view_models: list[dict[str, Any]] = []
    for process in processes:
        registry = _process_registry(process)
        owner_ids = _owner_bu_ids_for_process(process, config)
        frameworks = list(getattr(registry, "regulatory_frameworks", []) or []) if registry else []
        risk_count: int | str = len(getattr(process, "risks", []) or []) if is_pivot else "0 · Migration pending"
        view_models.append(
            {
                "process": process,
                "is_pivot": is_pivot,
                "row": {
                    "Process Name": getattr(process, "name", ""),
                    "Domain": _title_case_snake(getattr(process, "domain", "")),
                    "Hierarchy": _process_hierarchy(process, is_pivot),
                    "Owner BUs": ", ".join(bu_lookup.get(bu_id, bu_id) for bu_id in owner_ids) or "—",
                    "# Risks": risk_count,
                    "# Roles": len(getattr(registry, "roles", []) or []) if registry else 0,
                    "# Systems": len(getattr(registry, "systems", []) or []) if registry else 0,
                    "Regulatory Frameworks": _join_truncated(frameworks, 3),
                },
            }
        )
    return view_models


def prepare_processes_table(config: Any) -> list[dict[str, Any]]:
    """Prepare Processes rows for the Modular Knowledge Base."""
    return [item["row"] for item in _prepare_process_view_models(config)]


def _risk_taxonomy_parts(config: Any) -> tuple[list[Any], list[Any]]:
    taxonomy = getattr(config, "risk_taxonomy", None)
    if taxonomy is not None:
        return (
            list(getattr(taxonomy, "risk_level_1_categories", []) or []),
            list(getattr(taxonomy, "risk_catalog", []) or []),
        )
    categories = list(getattr(config, "risk_level_1_categories", []) or [])
    risk_catalog = list(getattr(config, "risk_catalog", []) or [])
    if categories and risk_catalog:
        return categories, risk_catalog
    return [], []


def _severity_dots(severity: int) -> str:
    return f"{'●' * severity} {severity}"


def prepare_risk_taxonomy_tables(config: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Prepare Level 1 and Level 2 Risk Taxonomy rows."""
    categories, risk_catalog = _risk_taxonomy_parts(config)
    risk_counts = Counter(getattr(risk, "level_1", "") for risk in risk_catalog)

    category_rows = [
        {
            "Code": getattr(cat, "code", ""),
            "Category": getattr(cat, "name", ""),
            "Definition": getattr(cat, "definition", ""),
            "Sub-groups": ", ".join(getattr(cat, "sub_groups", []) or []) or "—",
            "Risk Count": risk_counts.get(getattr(cat, "name", ""), 0),
            "Grounding": _truncate(getattr(cat, "grounding", None), 60),
        }
        for cat in categories
    ]

    sorted_risks = sorted(
        risk_catalog,
        key=lambda risk: (getattr(risk, "level_1_code", ""), getattr(risk, "id", "")),
    )
    risk_rows = [
        {
            "Risk ID": getattr(risk, "id", ""),
            "Name": getattr(risk, "name", ""),
            "Level 1": getattr(risk, "level_1", ""),
            "Sub-group": _dash_if_empty(getattr(risk, "sub_group", None)),
            "Default Severity": _severity_dots(int(getattr(risk, "default_severity", 3) or 3)),
            "Description": getattr(risk, "description", ""),
            "Mitigated By": _join_truncated(list(getattr(risk, "default_mitigating_types", []) or []), 3, ", "),
            "Grounding": f"ℹ️ {_truncate(getattr(risk, 'grounding', None), 60)}"
            if getattr(risk, "grounding", None)
            else "",
        }
        for risk in sorted_risks
    ]
    return category_rows, risk_rows


def load_placement_methods_config(path: Path | None = None) -> dict[str, Any]:
    """Load placement/method reference data used by the control taxonomy tab."""
    selected_path = path or _placement_methods_path()
    if not selected_path.exists():
        return {"placements": [], "methods": [], "control_taxonomy": {}}
    with selected_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def prepare_control_taxonomy_tables(
    config: Any,
    placement_methods: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare Control Taxonomy rows and reference tables."""
    placement_methods = placement_methods or load_placement_methods_config()
    placements = placement_methods.get("placements", []) or []
    methods = placement_methods.get("methods", []) or []

    return {
        "placements": [{"Placements": item.get("name", "") if isinstance(item, dict) else str(item)} for item in placements],
        "methods": [{"Methods": item.get("name", "") if isinstance(item, dict) else str(item)} for item in methods],
        "control_taxonomy": placement_methods.get("control_taxonomy", {}) or {},
        "control_types": [
            {
                "Code": _control_type_code(getattr(ct, "name", ""), getattr(ct, "code", "")),
                "Control Type": getattr(ct, "name", ""),
                "Placement(s)": ", ".join(getattr(ct, "placement_categories", []) or []) or "—",
                "Min Frequency": _dash_if_empty(getattr(ct, "min_frequency_tier", None)),
                "Definition": getattr(ct, "definition", ""),
            }
            for ct in getattr(config, "control_types", []) or []
        ],
    }


# ── Modular Knowledge Base rendering ──────────────────────────────────────────


def _dataframe_height(row_count: int, min_height: int = 180, max_height: int = 620) -> int:
    return min(max_height, max(min_height, 70 + row_count * 36))


def _render_dataframe(
    rows: list[dict[str, Any]],
    *,
    key: str,
    column_config: dict[str, Any] | None = None,
    height: int | None = None,
    selectable: bool = False,
) -> Any:
    if not rows:
        st.info("No records available.")
        return None

    frame = pd.DataFrame(rows)
    options: dict[str, Any] = {
        "hide_index": True,
        "use_container_width": True,
        "column_config": column_config or {},
        "height": height or _dataframe_height(len(rows)),
    }
    if selectable:
        options.update({"key": key, "on_select": "rerun", "selection_mode": "single-row"})
    return st.dataframe(frame, **options)


def _selected_row_index(event: Any) -> int | None:
    if event is None:
        return None
    rows: list[int] = []
    selection = getattr(event, "selection", None)
    if selection is not None:
        rows = list(getattr(selection, "rows", []) or [])
    elif isinstance(event, dict):
        rows = list(event.get("selection", {}).get("rows", []) or [])
    return rows[0] if rows else None


def _business_unit_column_config() -> dict[str, Any]:
    return {
        "Business Unit ID": st.column_config.TextColumn("Business Unit ID", width=150, pinned=True),
        "Business Unit": st.column_config.TextColumn("Business Unit", width=220, pinned=True),
        "Head": st.column_config.TextColumn("Head", width=220),
        "Employees": st.column_config.TextColumn("Employees", width=120),
        "Process Count": st.column_config.NumberColumn("Process Count", width=130),
        "Description": st.column_config.TextColumn("Description", width=520),
        "Risk Profile": st.column_config.TextColumn("Risk Profile", width=420),
    }


def _process_column_config() -> dict[str, Any]:
    return {
        "Process Name": st.column_config.TextColumn("Process Name", width=260, pinned=True),
        "Domain": st.column_config.TextColumn("Domain", width=190),
        "Hierarchy": st.column_config.TextColumn("Hierarchy", width=130),
        "Owner BUs": st.column_config.TextColumn("Owner BUs", width=280),
        "# Risks": st.column_config.TextColumn("# Risks", width=160),
        "# Roles": st.column_config.NumberColumn("# Roles", width=110),
        "# Systems": st.column_config.NumberColumn("# Systems", width=120),
        "Regulatory Frameworks": st.column_config.TextColumn("Regulatory Frameworks", width=360),
    }


def _risk_level_1_column_config() -> dict[str, Any]:
    return {
        "Code": st.column_config.TextColumn("Code", width=90, pinned=True),
        "Category": st.column_config.TextColumn("Category", width=220, pinned=True),
        "Definition": st.column_config.TextColumn("Definition", width=520),
        "Sub-groups": st.column_config.TextColumn("Sub-groups", width=360),
        "Risk Count": st.column_config.NumberColumn("Risk Count", width=120),
        "Grounding": st.column_config.TextColumn("Grounding", width=260),
    }


def _risk_catalog_column_config() -> dict[str, Any]:
    return {
        "Risk ID": st.column_config.TextColumn("Risk ID", width=150, pinned=True),
        "Name": st.column_config.TextColumn("Name", width=260, pinned=True),
        "Level 1": st.column_config.TextColumn("Level 1", width=190),
        "Sub-group": st.column_config.TextColumn("Sub-group", width=180),
        "Default Severity": st.column_config.TextColumn("Default Severity", width=160),
        "Description": st.column_config.TextColumn("Description", width=540),
        "Mitigated By": st.column_config.TextColumn("Mitigated By", width=360),
        "Grounding": st.column_config.TextColumn("Grounding", width=260),
    }


def _control_type_column_config() -> dict[str, Any]:
    return {
        "Code": st.column_config.TextColumn("Code", width=90, pinned=True),
        "Control Type": st.column_config.TextColumn("Control Type", width=300, pinned=True),
        "Placement(s)": st.column_config.TextColumn("Placement(s)", width=220),
        "Min Frequency": st.column_config.TextColumn("Min Frequency", width=150),
        "Definition": st.column_config.TextColumn("Definition", width=560),
    }


def _render_modular_knowledge_base(config: Any) -> None:
    st.markdown("---")
    st.markdown("### Modular Knowledge Base")
    st.caption("Read-only view of the loaded DomainConfig and its attached reference data.")

    tabs = st.tabs(KNOWLEDGE_BASE_TABS)
    renderers = [
        _render_business_units_tab,
        _render_processes_tab,
        _render_risk_taxonomy_tab,
        _render_control_taxonomy_tab,
    ]

    for tab, label, renderer in zip(tabs, KNOWLEDGE_BASE_TABS, renderers):
        with tab:
            try:
                renderer(config)
            except Exception as exc:
                logger.exception("Failed to render Modular Knowledge Base tab '%s'", label)
                st.error(f"Unable to render {label}: {exc}")


def _render_business_units_tab(config: Any) -> None:
    rows = prepare_business_units_table(config)
    _render_dataframe(
        rows,
        key=f"modkb_business_units_{getattr(config, 'name', 'config')}",
        column_config=_business_unit_column_config(),
    )


def _render_processes_tab(config: Any) -> None:
    view_models = _prepare_process_view_models(config)
    rows = [item["row"] for item in view_models]
    event = _render_dataframe(
        rows,
        key=f"modkb_processes_{getattr(config, 'name', 'config')}",
        column_config=_process_column_config(),
        selectable=True,
        height=_dataframe_height(len(rows), max_height=500),
    )

    selected_idx = _selected_row_index(event)
    with st.expander("Process detail", expanded=selected_idx is not None):
        if selected_idx is None or selected_idx >= len(view_models):
            st.info("Select a process row to inspect its registry, risks, and exemplars.")
            return

        selected = view_models[selected_idx]
        process = selected["process"]
        is_pivot = bool(selected["is_pivot"])
        registry = _process_registry(process)

        col_left, col_right = st.columns(2)
        with col_left:
            _render_registry_list("Roles", getattr(registry, "roles", []) if registry else [])
            _render_registry_list("Systems", getattr(registry, "systems", []) if registry else [])
            _render_registry_list("Data Objects", getattr(registry, "data_objects", []) if registry else [])
        with col_right:
            _render_registry_list(
                "Evidence Artifacts",
                getattr(registry, "evidence_artifacts", []) if registry else [],
            )
            _render_registry_list(
                "Event Triggers",
                getattr(registry, "event_triggers", []) if registry else [],
            )

        st.markdown("**Risks**")
        risk_rows = _process_risk_rows(config, process, is_pivot)
        if risk_rows:
            _render_dataframe(
                risk_rows,
                key=f"modkb_process_risks_{getattr(config, 'name', 'config')}_{getattr(process, 'id', '')}",
                height=_dataframe_height(len(risk_rows), min_height=130, max_height=320),
            )
        elif is_pivot:
            st.info("No risks are attached to this process.")
        else:
            st.info("Migration pending: legacy process areas do not carry process-level risks.")

        with st.expander("Exemplars", expanded=False):
            exemplars = list(getattr(process, "exemplars", []) or [])
            if not exemplars:
                st.info("No exemplars available for this process.")
                return
            exemplar_rows = [
                {
                    "Control Type": getattr(item, "control_type", ""),
                    "Placement": getattr(item, "placement", ""),
                    "Method": getattr(item, "method", ""),
                    "Description": getattr(item, "full_description", ""),
                    "Quality": getattr(item, "quality_rating", ""),
                }
                for item in exemplars
            ]
            _render_dataframe(
                exemplar_rows,
                key=f"modkb_exemplars_{getattr(config, 'name', 'config')}_{getattr(process, 'id', '')}",
                height=_dataframe_height(len(exemplar_rows), min_height=160, max_height=360),
            )


def _render_registry_list(label: str, values: list[str]) -> None:
    st.markdown(f"**{label}**")
    if not values:
        st.caption("—")
        return
    for value in values:
        st.markdown(f"- {value}")


def _process_risk_rows(config: Any, process: Any, is_pivot: bool) -> list[dict[str, Any]]:
    if not is_pivot:
        return []
    risk_lookup = {getattr(risk, "id", ""): risk for risk in getattr(config, "risk_catalog", []) or []}
    rows: list[dict[str, Any]] = []
    for risk in getattr(process, "risks", []) or []:
        catalog_entry = risk_lookup.get(getattr(risk, "risk_id", ""))
        mitigating_types = list(getattr(risk, "mitigating_type_names", []) or [])
        if not mitigating_types and catalog_entry is not None:
            mitigating_types = list(getattr(catalog_entry, "default_mitigating_types", []) or [])
        rows.append(
            {
                "Risk ID": getattr(risk, "risk_id", ""),
                "Risk": getattr(catalog_entry, "name", getattr(risk, "risk_id", "")),
                "Severity": getattr(risk, "severity", ""),
                "Multiplier": getattr(risk, "multiplier", ""),
                "Mitigating Control Types": ", ".join(mitigating_types) or "—",
            }
        )
    return rows


def _render_risk_taxonomy_tab(config: Any) -> None:
    category_rows, risk_rows = prepare_risk_taxonomy_tables(config)
    if not category_rows and not risk_rows:
        st.info("No risk taxonomy loaded for this profile.")
        return

    st.markdown("**Level 1 Categories**")
    _render_dataframe(
        category_rows,
        key=f"modkb_risk_l1_table_{getattr(config, 'name', 'config')}",
        column_config=_risk_level_1_column_config(),
        height=_dataframe_height(len(category_rows), min_height=240, max_height=420),
    )

    st.markdown("**Level 2 Risks**")
    category_options = ["All"] + [row["Category"] for row in category_rows]
    filter_col, search_col = st.columns([1, 2])
    with filter_col:
        selected_category = st.selectbox(
            "Level 1 category",
            category_options,
            key=f"modkb_risk_l1_filter_{getattr(config, 'name', 'config')}",
        )
    with search_col:
        search_text = st.text_input(
            "Search risks",
            key=f"modkb_risk_search_{getattr(config, 'name', 'config')}",
        ).strip().lower()

    filtered_rows = risk_rows
    if selected_category != "All":
        filtered_rows = [row for row in filtered_rows if row["Level 1"] == selected_category]
    if search_text:
        filtered_rows = [
            row
            for row in filtered_rows
            if search_text in row["Name"].lower() or search_text in row["Description"].lower()
        ]

    _render_dataframe(
        filtered_rows,
        key=f"modkb_risk_l2_table_{getattr(config, 'name', 'config')}",
        column_config=_risk_catalog_column_config(),
        height=_dataframe_height(len(filtered_rows), min_height=260, max_height=640),
    )


def _render_control_taxonomy_tab(config: Any) -> None:
    data = prepare_control_taxonomy_tables(config)
    placement_col, method_col = st.columns(2)
    with placement_col:
        st.markdown("**Placements**")
        _render_dataframe(
            data["placements"],
            key=f"modkb_placements_{getattr(config, 'name', 'config')}",
            height=180,
        )
    with method_col:
        st.markdown("**Methods**")
        _render_dataframe(
            data["methods"],
            key=f"modkb_methods_{getattr(config, 'name', 'config')}",
            height=180,
        )

    st.markdown("**Control Taxonomy**")
    _render_control_taxonomy_tree(data["control_taxonomy"])

    st.markdown("**Control Types**")
    _render_dataframe(
        data["control_types"],
        key=f"modkb_control_types_{getattr(config, 'name', 'config')}",
        column_config=_control_type_column_config(),
        height=_dataframe_height(len(data["control_types"]), min_height=300, max_height=620),
    )


def _render_control_taxonomy_tree(control_taxonomy: dict[str, Any]) -> None:
    level_1_options = list(control_taxonomy.get("level_1_options", []) or [])
    level_2_by_level_1 = control_taxonomy.get("level_2_by_level_1", {}) or {}
    if not level_1_options:
        st.info("No placement-to-control taxonomy loaded.")
        return

    for level_1 in level_1_options:
        with st.expander(str(level_1), expanded=False):
            items = level_2_by_level_1.get(level_1, []) or []
            if not items:
                st.caption("—")
                continue
            for item in items:
                st.markdown(f"- {item}")
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
        cols[1].metric("Processes", len(config.processes or config.process_areas))
        cols[2].metric("Risk Catalog", len(config.risk_catalog))
        category_rows, risk_rows = prepare_risk_taxonomy_tables(config)
        cols[3].metric("Risk Taxonomy", f"{len(category_rows)} / {len(risk_rows)}")
        categories, _risks = _risk_taxonomy_parts(config)
        if categories:
            st.caption(
                "Risk categories: "
                + ", ".join(f"**{c.name}** ({c.code})" for c in categories)
            )

    # ── Read-only Knowledge Base ─────────────────────────────────────────
    _render_modular_knowledge_base(config)

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
