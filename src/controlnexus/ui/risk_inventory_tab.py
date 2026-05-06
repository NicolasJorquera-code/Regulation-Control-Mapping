"""Risk Inventory Builder Streamlit tab.

Front-end-only experience that supports two storylines:

1. **Single-process demo:** Demo Mode defaults to a realistic Payment Exception
   Handling workbench while preserving a scope selector for the business unit
   and no-process dashboard view.
2. **User workflow:** Non-demo mode lets the user upload process documents and
   run the deterministic graph as before.

In non-demo mode, the Knowledge Base tab starts the workflow: the user can
review bank source tables, upload process/control evidence, and run the
deterministic graph from one intake surface.
"""

from __future__ import annotations

import html
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
import yaml  # type: ignore[import-untyped]

from controlnexus.analysis.ingest import ingest_excel
from controlnexus.risk_inventory.demo import (
    default_demo_fixture_path,
    load_demo_workspace,
)
from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.document_ingest import DocumentAnalysis, analyze_process_document
from controlnexus.risk_inventory.export import (
    risk_inventory_excel_bytes,
    risk_inventory_review_excel_bytes,
    risk_inventory_workspace_excel_bytes,
)
from controlnexus.risk_inventory.graph import build_risk_inventory_graph
from controlnexus.risk_inventory.models import (
    ApprovalStatus,
    ControlInventoryEntry,
    ControlMapping,
    KRIDefinition,
    ReviewDecision,
    ReviewStatus,
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskInventoryWorkspace,
)
from controlnexus.risk_inventory.services import (
    apply_review_decisions,
    build_control_gaps,
    build_synthetic_control_recommendations,
)

DEMO_RISK_INVENTORY_TABS = [
    "Knowledge Base",
    "Risk Inventory",
    "Control Mapping",
    "Gap Analysis",
]

USER_RISK_INVENTORY_TABS = [
    "Knowledge Base",
    "Risk Inventory",
    "Control Mapping",
    "Gap Analysis",
]

KNOWLEDGE_BASE_TABS = [
    "Business Units",
    "Processes",
    "Risk Taxonomy (2-Tier)",
    "Control Taxonomy",
    "Controls Register",
    "KRI Library",
]

DEFAULT_KNOWLEDGE_BASE_PROFILE = "Payment Exception Handling"

KNOWLEDGE_BASE_PROFILES: dict[str, dict[str, Any]] = {
    "Payment Exception Handling": {
        "model": "Single-process payment-operations scenario based on public erroneous wire-transfer lessons.",
        "source_emphasis": "Focused source pack across payment workflow evidence, controls, KRIs, issues, obligations, and public scenario trace.",
        "sample_business_unit": "Payment Operations",
        "sample_process": "Payment Exception Handling",
        "complexity": "Focused",
    },
}


def knowledge_base_profile_options() -> list[str]:
    """Return the supported demo profile labels in display order."""
    return list(KNOWLEDGE_BASE_PROFILES)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_risk_inventory_tab() -> None:
    """Render the full Risk Inventory Builder experience."""
    _inject_risk_inventory_css()
    _, toggle_col = st.columns([6, 1])
    with toggle_col:
        demo_enabled = st.toggle(
            "Demo",
            value=bool(st.session_state.get("demo_mode", False)),
            key="demo_mode",
        )

    if demo_enabled:
        _render_demo_workspace()
    else:
        _render_user_workflow()


# ---------------------------------------------------------------------------
# Demo workspace experience (Storylines 1 & 2)
# ---------------------------------------------------------------------------


def _render_demo_workspace() -> None:
    profile_name = DEFAULT_KNOWLEDGE_BASE_PROFILE

    if (
        "risk_inventory_workspace" not in st.session_state
        or st.session_state.get("risk_inventory_workspace_profile") != profile_name
    ):
        st.session_state["risk_inventory_workspace"] = load_demo_workspace().model_dump()
        st.session_state["risk_inventory_workspace_profile"] = profile_name
    workspace = RiskInventoryWorkspace.model_validate(st.session_state["risk_inventory_workspace"])
    selected_bu_id, selected_run = _render_demo_scope_selector(workspace)

    tabs = st.tabs(DEMO_RISK_INVENTORY_TABS)

    with tabs[0]:
        _render_knowledge_base(workspace, profile_name)
    with tabs[1]:
        if selected_run:
            _render_risk_inventory_combined(selected_run, workspace)
        else:
            _render_workspace_aggregated_inventory(workspace, selected_bu_id)
    with tabs[2]:
        if selected_run:
            _render_control_mapping(selected_run, workspace)
        else:
            _render_workspace_control_mapping(workspace, selected_bu_id)
    with tabs[3]:
        _render_control_gap_lab(selected_run, workspace, selected_bu_id)


def _render_demo_scope_selector(
    workspace: RiskInventoryWorkspace,
) -> tuple[str | None, RiskInventoryRun | None]:
    st.markdown('<div class="ri-section-title">Scope Selector</div>', unsafe_allow_html=True)
    business_unit_labels = ["All Business Units"] + [bu.bu_name for bu in workspace.business_units]
    default_bu_index = 1 if workspace.business_units else 0
    if st.session_state.get("ri_demo_bu_choice") not in business_unit_labels:
        st.session_state["ri_demo_bu_choice"] = business_unit_labels[default_bu_index]

    scope_cols = st.columns([1, 1.4])
    with scope_cols[0]:
        bu_choice = st.selectbox(
            "Business Unit",
            business_unit_labels,
            index=default_bu_index,
            key="ri_demo_bu_choice",
        )

    selected_bu_id: str | None = None
    process_pool = workspace.processes
    if bu_choice != "All Business Units":
        selected_bu = next((bu for bu in workspace.business_units if bu.bu_name == bu_choice), None)
        selected_bu_id = selected_bu.bu_id if selected_bu else None
        if selected_bu_id:
            process_pool = workspace.processes_for_bu(selected_bu_id)

    dashboard_label = "Workspace Dashboard (no process focus)"
    process_labels = [dashboard_label] + [process.process_name for process in process_pool]
    default_process_index = 1 if process_pool else 0
    if st.session_state.get("ri_demo_process_choice") not in process_labels:
        st.session_state["ri_demo_process_choice"] = process_labels[default_process_index]

    with scope_cols[1]:
        process_choice = st.selectbox(
            "Process",
            process_labels,
            index=default_process_index,
            key="ri_demo_process_choice",
        )

    selected_run: RiskInventoryRun | None = None
    if process_choice != dashboard_label:
        selected_process = next((process for process in process_pool if process.process_name == process_choice), None)
        selected_run = workspace.run_for_process(selected_process.process_id) if selected_process else None

    return selected_bu_id, selected_run


# ---------------------------------------------------------------------------
# User workflow (non-demo)
# ---------------------------------------------------------------------------


def _render_user_workflow() -> None:
    user_run_data = st.session_state.get("risk_inventory_user_run")
    run = RiskInventoryRun.model_validate(user_run_data) if user_run_data else None

    tabs = st.tabs(USER_RISK_INVENTORY_TABS)

    with tabs[0]:
        _render_input_and_maybe_run()
    with tabs[1]:
        _render_risk_inventory_combined(run, None) if run else _render_empty_panel(
            "Risk records will appear after you run the workflow from Knowledge Base."
        )
    with tabs[2]:
        _render_control_mapping(run) if run else _render_empty_panel(
            "Control mappings will appear after inventory creation from Knowledge Base."
        )
    with tabs[3]:
        _render_control_gap_lab(run, None, None) if run else _render_empty_panel(
            "Gap analysis will appear after inventory creation from Knowledge Base."
        )


def _render_workspace_aggregated_inventory(
    workspace: RiskInventoryWorkspace, selected_bu_id: str | None
) -> None:
    st.markdown('<div class="ri-section-title">Aggregated Risk Inventory</div>', unsafe_allow_html=True)
    rows = workspace_aggregated_inventory_rows(workspace, selected_bu_id)
    if rows:
        _render_workspace_inventory_summary(rows, workspace, selected_bu_id)
        _render_prominent_table(rows)
    else:
        _render_neutral_callout("No runs are available for the selected scope.")

    st.markdown('<div class="ri-section-title">Portfolio Risk Heatmap</div>', unsafe_allow_html=True)
    heatmap_rows = portfolio_heatmap_rows(workspace, selected_bu_id)
    if heatmap_rows:
        _render_portfolio_heatmap(heatmap_rows)


def workspace_aggregated_inventory_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> list[dict[str, Any]]:
    """Table rows for the workspace-level risk inventory board."""
    rows: list[dict[str, Any]] = []
    procedures = workspace.procedures
    if selected_bu_id:
        procedures = workspace.procedures_for_bu(selected_bu_id)
    for proc in procedures:
        run = workspace.run_for_procedure(proc.procedure_id)
        if not run:
            continue
        for rec in run.records:
            rows.append(
                {
                    "Risk Record ID": rec.risk_id,
                    "Business Unit": next(
                        (bu.bu_name for bu in workspace.business_units if bu.bu_id == proc.bu_id),
                        proc.bu_id,
                    ),
                    "Process": proc.procedure_name,
                    "Enterprise Risk Category": rec.taxonomy_node.level_1_category,
                    "Risk Subcategory": rec.taxonomy_node.level_2_category,
                    "Risk Statement": rec.risk_statement.risk_description,
                    "Impact Score": int(rec.impact_assessment.overall_impact_score),
                    "Frequency Score": int(rec.likelihood_assessment.likelihood_score),
                    "Inherent Risk Rating": rec.inherent_risk.inherent_rating.value,
                    "Residual Risk Rating": rec.residual_risk.residual_rating.value,
                }
            )
    return rows


def _render_workspace_inventory_summary(
    rows: list[dict[str, Any]],
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None,
) -> None:
    process_count = len(workspace.processes_for_bu(selected_bu_id)) if selected_bu_id else len(workspace.processes)
    business_unit_count = 1 if selected_bu_id else len({str(row["Business Unit"]) for row in rows})
    high_plus = sum(row["Residual Risk Rating"] in {"High", "Critical"} for row in rows)
    summary = {
        "Risks": str(len(rows)),
        "Business Units": str(business_unit_count),
        "Processes": str(process_count),
        "High+ Residual": str(high_plus),
        "Avg Impact": f"{sum(int(row.get('Impact Score', 0)) for row in rows) / max(len(rows), 1):.1f}",
        "Avg Frequency": f"{sum(int(row.get('Frequency Score', 0)) for row in rows) / max(len(rows), 1):.1f}",
    }
    cells = "".join(
        f"<div><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>"
        for label, value in summary.items()
    )
    st.markdown(f'<div class="ri-neutral-summary">{cells}</div>', unsafe_allow_html=True)


def bu_risk_divergence_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    business_units = (
        [bu for bu in workspace.business_units if bu.bu_id == selected_bu_id]
        if selected_bu_id
        else list(workspace.business_units)
    )
    for bu in business_units:
        records = _records_for_bu(workspace, bu.bu_id)
        if not records:
            continue
        grouped: dict[tuple[str, str], list[RiskInventoryRecord]] = {}
        for record in records:
            key = (record.taxonomy_node.level_1_category, record.taxonomy_node.level_2_category)
            grouped.setdefault(key, []).append(record)
        ranked = sorted(
            grouped.items(),
            key=lambda item: (
                sum(r.residual_risk.residual_rating.value in {"High", "Critical"} for r in item[1]),
                len(item[1]),
                sum(len(build_control_gaps(r)) for r in item[1]),
            ),
            reverse=True,
        )
        for (l1_category, l2_category), category_records in ranked[:2]:
            process_counts = Counter(record.process_name for record in category_records)
            rows.append(
                {
                    "Business Unit": bu.bu_name,
                    "Level 2 Risk Category": l2_category,
                    "Enterprise Category": l1_category,
                    "Risk Records": len(category_records),
                    "High+ Residual": sum(
                        r.residual_risk.residual_rating.value in {"High", "Critical"}
                        for r in category_records
                    ),
                    "Control Gap Count": sum(len(build_control_gaps(r)) for r in category_records),
                    "Representative Process": process_counts.most_common(1)[0][0] if process_counts else "",
                    "Risk Capture Signal": bu.risk_profile_summary,
                }
            )
    return rows


def _records_for_bu(workspace: RiskInventoryWorkspace, bu_id: str) -> list[RiskInventoryRecord]:
    records: list[RiskInventoryRecord] = []
    for process in workspace.processes_for_bu(bu_id):
        run = workspace.run_for_process(process.process_id)
        if run:
            records.extend(run.records)
    return records


def _render_bu_difference_cards(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> None:
    business_units = (
        [bu for bu in workspace.business_units if bu.bu_id == selected_bu_id]
        if selected_bu_id
        else list(workspace.business_units)
    )
    cards = []
    for bu in business_units:
        records = _records_for_bu(workspace, bu.bu_id)
        if not records:
            continue
        category_counts = Counter(record.taxonomy_node.level_1_category for record in records)
        dominant = category_counts.most_common(1)[0][0]
        high_plus = sum(record.residual_risk.residual_rating.value in {"High", "Critical"} for record in records)
        gap_count = sum(len(build_control_gaps(record)) for record in records)
        cards.append(
            (
                '<div class="ri-bu-diff-card">'
                f"<span>{html.escape(bu.bu_name)}</span>"
                f"<b>{html.escape(dominant)}</b>"
                f"<p>{html.escape(bu.risk_profile_summary)}</p>"
                "<div>"
                f'{_badge("High+ Residual", str(high_plus), "high" if high_plus else "neutral")}'
                f'{_badge("Gaps", str(gap_count), "high" if gap_count else "neutral")}'
                "</div>"
                "</div>"
            )
        )
    st.markdown(f'<div class="ri-bu-diff-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_portfolio_heatmap(rows: list[dict[str, Any]]) -> None:
    business_units = sorted({str(row["Business Unit"]) for row in rows})
    categories = sorted({str(row["Enterprise Risk Category"]) for row in rows})
    header = "".join(f"<div class='ri-port-head'>{html.escape(category)}</div>" for category in categories)
    body = []
    for bu_name in business_units:
        body.append(f"<div class='ri-port-bu'>{html.escape(bu_name)}</div>")
        for category in categories:
            row = next(
                (
                    item
                    for item in rows
                    if item["Business Unit"] == bu_name and item["Enterprise Risk Category"] == category
                ),
                {},
            )
            heat = str(row.get("Heat", "None"))
            body.append(
                f"<div class='ri-port-cell ri-port-{_portfolio_tone(heat)}'>"
                f"<b>{html.escape(str(row.get('Risk Records', 0)))}</b>"
                f"<span>{html.escape(str(row.get('High+ Residual', 0)))} high+</span></div>"
            )
    st.markdown(
        f"""
        <div class="ri-port-grid" style="grid-template-columns: 180px repeat({max(len(categories), 1)}, minmax(110px, 1fr));">
            <div class="ri-port-corner">Business Unit</div>
            {header}
            {''.join(body)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _portfolio_tone(heat: str) -> str:
    lowered = heat.lower()
    if lowered == "high":
        return "high"
    if lowered in {"medium", "elevated"}:
        return "medium"
    if lowered == "low":
        return "low"
    return "none"


def _render_workspace_executive(
    workspace: RiskInventoryWorkspace, selected_bu_id: str | None
) -> None:
    st.markdown('<div class="ri-section-title">Workspace Executive Roll-up</div>', unsafe_allow_html=True)
    procedures = workspace.procedures
    if selected_bu_id:
        procedures = workspace.procedures_for_bu(selected_bu_id)
    for proc in procedures:
        run = workspace.run_for_procedure(proc.procedure_id)
        if not run:
            continue
        with st.expander(f"{proc.procedure_name} — {run.executive_summary.headline}", expanded=False):
            st.write(run.executive_summary.headline)
            cols = st.columns(2)
            with cols[0]:
                st.markdown("**Top residual risks**")
                for risk in run.executive_summary.top_residual_risks:
                    st.markdown(f"- {html.escape(risk)}")
            with cols[1]:
                st.markdown("**Recommended actions**")
                for action in run.executive_summary.recommended_actions:
                    st.markdown(f"- {html.escape(action)}")


# ---------------------------------------------------------------------------
# Process map / agent trace support panels
# ---------------------------------------------------------------------------


def _render_process_map(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None,
    selected_run: RiskInventoryRun | None,
) -> None:
    st.markdown('<div class="ri-section-title">BU -> Process -> Risks -> Controls -> KRIs</div>', unsafe_allow_html=True)
    rows = _process_map_rows(workspace, selected_bu_id, selected_run)
    if not rows:
        st.info("No process map rows are available for the selected scope.")
        return
    high_plus = sum(row["Residual Risk Rating"] in {"High", "Critical"} for row in rows)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_metric_card("Map Rows", str(len(rows)), "blue"), unsafe_allow_html=True)
    c2.markdown(_metric_card("High+ Residual", str(high_plus), "red" if high_plus else "green"), unsafe_allow_html=True)
    c3.markdown(_metric_card("Avg Impact", f"{sum(int(row.get('Impact Score', 0)) for row in rows) / max(len(rows), 1):.1f}", "teal"), unsafe_allow_html=True)
    c4.markdown(_metric_card("KRI Links", str(sum(int(row["Mapped KRIs"]) for row in rows)), "teal"), unsafe_allow_html=True)
    _render_table(rows)


def _process_map_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None,
    selected_run: RiskInventoryRun | None,
) -> list[dict[str, Any]]:
    bu_lookup = {bu.bu_id: bu.bu_name for bu in workspace.business_units}
    if selected_run:
        run_process_ids = {selected_run.input_context.process_id}
        processes = [process for process in workspace.processes if process.process_id in run_process_ids]
    else:
        processes = workspace.processes_for_bu(selected_bu_id) if selected_bu_id else workspace.processes

    rows: list[dict[str, Any]] = []
    for process in processes:
        run = selected_run if selected_run and selected_run.input_context.process_id == process.process_id else workspace.run_for_process(process.process_id)
        if not run:
            continue
        for record in run.records:
            kris = workspace.kris_for_taxonomy(record.taxonomy_node.id)
            rows.append(
                {
                    "Business Unit": bu_lookup.get(process.bu_id, process.bu_id),
                    "Process": process.process_name,
                    "Risk Record ID": record.risk_id,
                    "Risk Subcategory": record.taxonomy_node.level_2_category,
                    "Risk Statement": record.risk_statement.risk_description,
                    "Impact Score": int(record.impact_assessment.overall_impact_score),
                    "Frequency Score": int(record.likelihood_assessment.likelihood_score),
                    "Mapped KRIs": len(kris),
                    "Residual Risk Rating": record.residual_risk.residual_rating.value,
                }
            )
    return rows


def _render_agent_trace(
    selected_run: RiskInventoryRun | None,
    workspace: RiskInventoryWorkspace,
) -> None:
    st.markdown('<div class="ri-section-title">Agent Run Trace</div>', unsafe_allow_html=True)
    raw_events: list[dict[str, Any]] = []
    if selected_run:
        raw_events.extend(selected_run.events)
    raw_events.extend(event.model_dump() for event in workspace.agent_trace)
    if not raw_events:
        st.info("No trace events are available yet.")
        return

    rows = [
        {
            "Stage": event.get("stage", ""),
            "Agent": event.get("agent", ""),
            "Mode": event.get("mode", "deterministic_fallback"),
            "Status": event.get("status", "completed"),
            "Inputs Used": ", ".join(event.get("inputs_used", []) or []),
            "Tools Called": ", ".join(event.get("tools_called", []) or []),
            "Output References": ", ".join(event.get("output_refs", []) or []),
            "Summary": event.get("summary", ""),
        }
        for event in raw_events
    ]
    _render_table(rows)

# ---------------------------------------------------------------------------
# Knowledge Base tab
# ---------------------------------------------------------------------------


def knowledge_base_complexity_metrics(
    workspace: RiskInventoryWorkspace,
    profile_name: str,
) -> list[dict[str, Any]]:
    """Return profile-level complexity metrics for the Knowledge Base selector."""
    risk_count = sum(len(run.records) for run in workspace.runs)
    control_count = len({control.get("control_id", "") for control in workspace.bank_controls if control.get("control_id")})
    high_plus = sum(
        record.residual_risk.residual_rating.value in {"High", "Critical"}
        for run in workspace.runs
        for record in run.records
    )
    profile = KNOWLEDGE_BASE_PROFILES.get(profile_name, KNOWLEDGE_BASE_PROFILES[DEFAULT_KNOWLEDGE_BASE_PROFILE])
    return [
        {"Metric": "Profile", "Value": profile_name, "Detail": str(profile["complexity"])},
        {"Metric": "Business Units", "Value": len(workspace.business_units), "Detail": "Operating-model breadth"},
        {"Metric": "Processes", "Value": len(workspace.processes), "Detail": "Process fixtures wired"},
        {"Metric": "Risks", "Value": risk_count, "Detail": f"{high_plus} high or critical residual"},
        {"Metric": "Controls", "Value": control_count, "Detail": "Distinct controls in source packs"},
        {"Metric": "KRIs", "Value": len(workspace.kri_library), "Detail": "Thresholded indicators"},
        {"Metric": "Evidence", "Value": len(workspace.evidence_artifacts), "Detail": "Reusable artifacts"},
    ]


def _render_profile_complexity_cards(
    workspace: RiskInventoryWorkspace,
    profile_name: str,
) -> None:
    profile = KNOWLEDGE_BASE_PROFILES.get(profile_name, KNOWLEDGE_BASE_PROFILES[DEFAULT_KNOWLEDGE_BASE_PROFILE])
    st.markdown(
        f"""
        <div class="ri-intake-profile">
            <b>{html.escape(profile_name)}</b>
            <p>{html.escape(str(profile["model"]))}</p>
            <span>{html.escape(str(profile["source_emphasis"]))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metrics = knowledge_base_complexity_metrics(workspace, profile_name)
    cards = [
        (
            '<div class="ri-source-card">'
            f'<span>{html.escape(str(row["Metric"]))}</span>'
            f'<b>{html.escape(str(row["Value"]))}</b>'
            f'<p>{html.escape(str(row["Detail"]))}</p>'
            "</div>"
        )
        for row in metrics
    ]
    st.markdown(f'<div class="ri-source-grid ri-profile-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def bu_risk_capture_rows(workspace: RiskInventoryWorkspace) -> list[dict[str, Any]]:
    """Show how each BU captures different risk types in the same modular model."""
    rows: list[dict[str, Any]] = []
    for bu in workspace.business_units:
        processes = workspace.processes_for_bu(bu.bu_id)
        records = _records_for_bu(workspace, bu.bu_id)
        if not records:
            continue
        category_counts = Counter(record.taxonomy_node.level_1_category for record in records)
        dominant_categories = ", ".join(
            f"{category} ({count})" for category, count in category_counts.most_common(3)
        )
        high_plus = sum(record.residual_risk.residual_rating.value in {"High", "Critical"} for record in records)
        process_ids = {process.process_id for process in processes}
        evidence_count = sum(item.process_id in process_ids for item in workspace.evidence_artifacts)
        issue_count = sum(item.process_id in process_ids for item in workspace.issues)
        obligation_count = sum(
            bool(process_ids.intersection(item.process_ids))
            for item in workspace.regulatory_obligations
        )
        kri_ids = {
            kri.kri_id
            for record in records
            for kri in workspace.kris_for_taxonomy(record.taxonomy_node.id)
        }
        source_packs = [
            "Processes",
            "Controls",
            "KRIs" if kri_ids else "",
            "Evidence" if evidence_count else "",
            "Issues" if issue_count else "",
            "Obligations" if obligation_count else "",
        ]
        avg_impact = sum(int(record.impact_assessment.overall_impact_score) for record in records) / max(len(records), 1)
        avg_frequency = sum(int(record.likelihood_assessment.likelihood_score) for record in records) / max(len(records), 1)
        rows.append(
            {
                "Business Unit": bu.bu_name,
                "Processes": len(processes),
                "Risk Records": len(records),
                "Dominant Captured Risk Types": dominant_categories,
                "Avg Impact": f"{avg_impact:.1f}",
                "Avg Frequency": f"{avg_frequency:.1f}",
                "High+ Residual": high_plus,
                "Key Source Packs": ", ".join(item for item in source_packs if item),
                "Capture Rationale": bu.risk_profile_summary,
            }
        )
    return rows


def _render_knowledge_base(workspace: RiskInventoryWorkspace, profile_name: str | None = None) -> None:
    st.markdown('<div class="ri-section-title">Modular Knowledge Base</div>', unsafe_allow_html=True)
    st.caption(
        "Read-only view of the supplied source packs: business units, processes, risk taxonomy, "
        "control taxonomy, synthetic controls register, and KRI library."
    )

    sub_tabs = st.tabs(KNOWLEDGE_BASE_TABS)

    with sub_tabs[0]:
        _render_table(
            [
                {
                    "Business Unit ID": bu.bu_id,
                    "Business Unit": bu.bu_name,
                    "Head": bu.head,
                    "Employees": bu.employee_count,
                    "Process Count": len(workspace.procedures_for_bu(bu.bu_id)),
                    "Description": bu.description,
                    "Risk Profile": bu.risk_profile_summary,
                }
                for bu in workspace.business_units
            ],
        )

    with sub_tabs[1]:
        bu_lookup = {bu.bu_id: bu.bu_name for bu in workspace.business_units}
        _render_table(
            [
                {
                    "Process ID": p.procedure_id,
                    "Process": p.procedure_name,
                    "Business Unit": bu_lookup.get(p.bu_id, p.bu_id),
                    "Owner": p.owner,
                    "Criticality": p.criticality,
                    "Review Cadence": p.cadence,
                    "Last Reviewed": p.last_reviewed,
                    "Systems": ", ".join(p.related_systems),
                }
                for p in workspace.procedures
            ],
        )

    with sub_tabs[2]:
        st.markdown("**Level 1 — Enterprise Risk Categories**")
        _render_table(
            [
                {
                    "Level 1 Code": l1.code,
                    "Enterprise Risk Category": l1.name,
                    "Definition": l1.definition,
                    "Risk Subcategory Count": len(l1.level_2_codes),
                }
                for l1 in workspace.risk_taxonomy_l1
            ],
        )
        st.markdown("**Level 2 — Risk Sub-Categories**")
        l2_to_l1: dict[str, str] = {}
        for l1 in workspace.risk_taxonomy_l1:
            for code in l1.level_2_codes:
                l2_to_l1[code] = f"{l1.code} · {l1.name}"
        _render_table(
            [
                {
                    "Level 2 Code": node.id,
                    "Enterprise Risk Category": l2_to_l1.get(node.id, node.level_1_category),
                    "Risk Subcategory": node.level_2_category,
                    "Definition": node.definition,
                    "Regulatory Relevance": ", ".join(node.regulatory_relevance),
                }
                for node in workspace.risk_taxonomy_l2
            ],
        )

    with sub_tabs[3]:
        _render_table(
            [
                {
                    "Code": c.code,
                    "Family": c.family,
                    "Control Family": c.name,
                    "Description": c.description,
                    "Typical Evidence": ", ".join(c.typical_evidence),
                }
                for c in workspace.control_taxonomy
            ],
        )

    with sub_tabs[4]:
        _render_table(synthetic_control_inventory_rows(workspace))

    with sub_tabs[5]:
        l2_lookup = {node.id: node.level_2_category for node in workspace.risk_taxonomy_l2}
        _render_table(
            [
                {
                    "KRI ID": k.kri_id,
                    "KRI": k.kri_name,
                    "Risk Subcategory": l2_lookup.get(k.risk_taxonomy_id, k.risk_taxonomy_id),
                    "Owner": k.owner,
                    "Frequency": k.measurement_frequency,
                    "Green": k.thresholds.green,
                    "Amber": k.thresholds.amber,
                    "Red": k.thresholds.red,
                }
                for k in workspace.kri_library
            ],
        )


def synthetic_control_inventory_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> list[dict[str, Any]]:
    """Rows for the Knowledge Base synthetic control inventory."""
    bu_lookup = {bu.bu_id: bu.bu_name for bu in workspace.business_units}
    processes = workspace.processes_for_bu(selected_bu_id) if selected_bu_id else workspace.processes
    rows: list[dict[str, Any]] = []
    for process in processes:
        run = workspace.run_for_process(process.process_id)
        if not run:
            continue
        for record in run.records:
            recommendations = (
                record.synthetic_control_recommendations
                or build_synthetic_control_recommendations(record, workspace)
            )
            for recommendation in recommendations:
                rows.append(
                    {
                        "Recommendation ID": recommendation.recommendation_id,
                        "Risk Record ID": record.risk_id,
                        "Business Unit": bu_lookup.get(process.bu_id, process.bu_id),
                        "Process": process.process_name,
                        "Risk Subcategory": record.taxonomy_node.level_2_category,
                        "Control": recommendation.control_name,
                        "Control Type": recommendation.control_type,
                        "Priority": recommendation.priority,
                        "Owner": recommendation.suggested_owner,
                        "Frequency": recommendation.frequency,
                        "Control Statement": recommendation.control_statement,
                        "Rationale": recommendation.rationale,
                        "Expected Evidence": recommendation.expected_evidence,
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# Risk Inventory tab (combined Inherent + Inventory)
# ---------------------------------------------------------------------------


def _render_risk_inventory_combined(
    run: RiskInventoryRun, workspace: RiskInventoryWorkspace | None
) -> None:
    rows = risk_inventory_workbench_rows(run, workspace)
    if not rows:
        _render_empty_panel("No risk records are available for this process.")
        return

    selected_id = st.session_state.get("ri_selected_risk_id")
    if selected_id not in {record.risk_id for record in run.records}:
        selected_id = run.records[0].risk_id if run.records else ""
        st.session_state["ri_selected_risk_id"] = selected_id

    st.markdown('<div class="ri-section-title">Risk Inventory Command View</div>', unsafe_allow_html=True)
    _render_process_command_header(run, workspace)
    selected_id = _render_risk_inventory_browser(rows, selected_id)

    selected_record = next(record for record in run.records if record.risk_id == selected_id)
    _render_risk_command_center(selected_record, workspace, run)
    _render_risk_command_review_summary(selected_record, workspace)


def _risk_statement_display(record: RiskInventoryRecord) -> str:
    """Return the approved risk statement without appending root-cause notes."""
    return record.risk_statement.risk_description.strip()


def risk_inventory_workbench_rows(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None,
) -> list[dict[str, Any]]:
    """Rows used by the left-side risk workbench selector."""
    rows: list[dict[str, Any]] = []
    for record in run.records:
        validation = required_validation_level(record, workspace)
        rows.append(
            {
                "Risk Record ID": record.risk_id,
                "Business Unit": _business_unit_for_record(record, workspace) or run.input_context.business_unit,
                "Process": record.process_name,
                "Risk Subcategory": record.taxonomy_node.level_2_category,
                "Risk Statement": _risk_statement_display(record),
                "Enterprise Risk Category": record.taxonomy_node.level_1_category,
                "Impact": int(record.impact_assessment.overall_impact_score),
                "Frequency": int(record.likelihood_assessment.likelihood_score),
                "Inherent Risk": record.inherent_risk.inherent_rating.value,
                "Controls": len(record.control_mappings),
                "Gaps": len(build_control_gaps(record)),
                "KRIs": len(workspace.kris_for_taxonomy(record.taxonomy_node.id)) if workspace else 0,
                "Validation Level": validation["validation_level"],
                "Required Reviewer": validation["required_reviewer"],
                "Review": record.review_challenges[0].review_status.value if record.review_challenges else "",
            }
        )
    return rows


def selected_risk_detail(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> dict[str, Any]:
    """Build a single risk profile payload for UI/tests/export projections."""
    process = (
        next((p for p in workspace.processes if p.process_id == record.process_id), None)
        if workspace
        else None
    )
    business_unit = (
        next((bu.bu_name for bu in workspace.business_units if process and bu.bu_id == process.bu_id), "")
        if workspace
        else ""
    )
    kris = workspace.kris_for_taxonomy(record.taxonomy_node.id) if workspace else []
    issues = [
        issue
        for issue in (workspace.issues if workspace else [])
        if issue.risk_id == record.risk_id or issue.process_id == record.process_id
    ]
    evidence = list(record.evidence_references)
    if workspace:
        evidence.extend(
            item
            for item in workspace.evidence_artifacts
            if item.process_id == record.process_id
            or any(item.control_id == mapping.control_id for mapping in record.control_mappings)
        )
    return {
        "risk_id": record.risk_id,
        "process_id": record.process_id,
        "process_name": record.process_name,
        "business_unit": business_unit,
        "level_1_category": record.taxonomy_node.level_1_category,
        "level_2_category": record.taxonomy_node.level_2_category,
        "risk_statement": _risk_statement_display(record),
        "root_causes": record.risk_statement.causes or record.taxonomy_node.typical_root_causes,
        "impact_score": int(record.impact_assessment.overall_impact_score),
        "frequency_score": int(record.likelihood_assessment.likelihood_score),
        "frequency_rating": record.likelihood_assessment.likelihood_rating,
        "inherent_risk": record.inherent_risk.inherent_rating.value,
        "residual_risk": record.residual_risk.residual_rating.value,
        "management_response": record.residual_risk.management_response.response_type.value.title(),
        "mitigation_plan": record.residual_risk.management_response.recommended_action,
        "controls": [mapping.model_dump() for mapping in record.control_mappings],
        "control_gaps": [gap.model_dump() for gap in build_control_gaps(record)],
        "synthetic_controls": [
            recommendation.model_dump()
            for recommendation in build_synthetic_control_recommendations(record, workspace)
        ],
        "kris": [kri.model_dump() for kri in kris],
        "evidence": [_evidence_detail_dict(item) for item in evidence],
        "issues": [issue.model_dump() for issue in issues],
        "review": record.review_challenges[0].model_dump() if record.review_challenges else {},
        "apqc_crosswalk": process.apqc_crosswalk if process else {},
        "validation": required_validation_level(record, workspace),
    }


def impact_frequency_heatmap_rows(
    record: RiskInventoryRecord,
    matrix_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic 4x4 heatmap rows with the selected cell marked."""
    matrix_config = matrix_config or MatrixConfigLoader().inherent_matrix()
    matrix = matrix_config.get("matrix", {})
    selected_impact = int(record.impact_assessment.overall_impact_score)
    selected_frequency = int(record.likelihood_assessment.likelihood_score)
    rows: list[dict[str, Any]] = []
    for frequency in [4, 3, 2, 1]:
        for impact in [1, 2, 3, 4]:
            result = matrix.get(impact, matrix.get(str(impact), {})).get(
                frequency,
                matrix.get(impact, matrix.get(str(impact), {})).get(str(frequency), {}),
            )
            rows.append(
                {
                    "Impact": impact,
                    "Frequency": frequency,
                    "Rating": result.get("rating", ""),
                    "Score": result.get("score", impact * frequency),
                    "Label": result.get("label", ""),
                    "Selected": impact == selected_impact and frequency == selected_frequency,
                }
            )
    return rows


def portfolio_heatmap_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate BU x risk-category heatmap rows for the portfolio view."""
    rows = _workspace_control_mapping_rows(workspace, selected_bu_id)
    business_units = sorted({str(row["Business Unit"]) for row in rows})
    categories = sorted({str(row["Enterprise Risk Category"]) for row in rows})
    heatmap_rows: list[dict[str, Any]] = []
    for bu_name in business_units:
        bu_rows = [row for row in rows if row["Business Unit"] == bu_name]
        for category in categories:
            category_rows = [row for row in bu_rows if row["Enterprise Risk Category"] == category]
            heatmap_rows.append(
                {
                    "Business Unit": bu_name,
                    "Enterprise Risk Category": category,
                    "Risk Records": len(category_rows),
                    "High+ Residual": _high_plus_count(category_rows),
                    "Mapped Controls": sum(int(row["Mapped Controls"]) for row in category_rows),
                    "Heat": _portfolio_heat_value(category_rows),
                }
            )
    return heatmap_rows


def _render_process_command_header(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None,
) -> None:
    business_unit = (
        run.input_context.business_unit
        or (_business_unit_for_record(run.records[0], workspace) if run.records else "")
    )
    facts = {
        "Business Unit": business_unit,
        "Process": run.input_context.process_name,
    }
    st.markdown(
        f"""
        <div class="ri-command-header">
            <div>
                <span>Process Dossier</span>
                <b>{html.escape(run.input_context.process_name)}</b>
            </div>
            <p>{html.escape(run.input_context.description or "Risk inventory generated from process context, configured taxonomy, controls, evidence, KRIs, and scoring matrices.")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_fact_block(facts)


def _render_risk_inventory_browser(rows: list[dict[str, Any]], selected_id: str) -> str:
    st.markdown("**Risk Inventory Browser**")
    browser_rows = [
        {
            "Risk ID": row["Risk Record ID"],
            "Business Unit": row["Business Unit"],
            "Process": row["Process"],
            "Enterprise Category": row["Enterprise Risk Category"],
            "Risk Subcategory": row["Risk Subcategory"],
            "Risk Statement": row["Risk Statement"],
            "Inherent Risk": row["Inherent Risk"],
            "Impact": row["Impact"],
            "Frequency": row["Frequency"],
            "Controls": row["Controls"],
            "Gaps": row["Gaps"],
            "KRIs": row["KRIs"],
            "Validation": row["Validation Level"],
            "Review": row["Review"],
        }
        for row in rows
    ]
    selected_index = next(
        (idx for idx, row in enumerate(browser_rows) if row["Risk ID"] == selected_id),
        0,
    )
    row_height = max(156, _table_row_height(browser_rows))
    event = st.dataframe(
        browser_rows,
        hide_index=True,
        width="stretch",
        height=min(760, 64 + len(browser_rows) * row_height),
        row_height=row_height,
        selection_mode="single-row",
        on_select="rerun",
        key="ri_inventory_browser_table",
        column_config=_table_column_config(browser_rows),
    )
    selected_rows = getattr(getattr(event, "selection", None), "rows", [])
    if selected_rows:
        selected_index = int(selected_rows[0])
    selected_id = str(browser_rows[selected_index]["Risk ID"])
    st.session_state["ri_selected_risk_id"] = selected_id
    return selected_id


def _render_risk_command_center(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
    run: RiskInventoryRun,
) -> None:
    detail = selected_risk_detail(record, workspace)
    st.markdown(
        f"""
        <div class="ri-command-main">
            <div class="ri-command-kicker">{html.escape(detail["risk_id"])} · {html.escape(detail["level_1_category"])}</div>
            <h3>{html.escape(detail["level_2_category"])}</h3>
            <p>{html.escape(detail["risk_statement"])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_chip_group("Root causes", list(detail["root_causes"]))
    _render_chip_group("Affected stakeholders", record.risk_statement.affected_stakeholders)
    _render_inherent_risk_summary(record)
    _render_selected_risk_kri_cards(record, workspace)


def _render_risk_command_review_summary(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> None:
    gaps = build_control_gaps(record)
    kris = workspace.kris_for_taxonomy(record.taxonomy_node.id) if workspace else []
    _render_fact_block(
        {
            "Controls": str(len(record.control_mappings)),
            "Gaps": str(len(gaps)),
            "KRIs": str(len(kris)),
        }
    )
    st.markdown("**Management response**")
    st.write(record.residual_risk.management_response.recommended_action)


def _render_inherent_risk_summary(record: RiskInventoryRecord) -> None:
    tone = _rating_class(record.inherent_risk.inherent_rating.value)
    st.markdown('<div class="ri-section-title">Inherent Risk</div>', unsafe_allow_html=True)
    rationale_col, matrix_col = st.columns([1.08, 0.92], gap="large")
    with rationale_col:
        st.markdown(
            f"""
            <div class="ri-inherent-flow">
                <div class="ri-inherent-rating-row">
                    <div>
                        <span>Current inherent basis</span>
                        <b>Score {int(record.inherent_risk.inherent_score)}</b>
                    </div>
                    <strong class="ri-inherent-badge ri-{tone}">{html.escape(record.inherent_risk.inherent_rating.value)}</strong>
                </div>
                <div class="ri-inherent-metrics">
                    <div><span>Impact</span><b>{int(record.impact_assessment.overall_impact_score)}</b></div>
                    <div><span>Frequency</span><b>{int(record.likelihood_assessment.likelihood_score)}</b></div>
                </div>
                <div class="ri-inherent-rationale-grid">
                    <div>
                        <span>Impact Rationale</span>
                        <p>{html.escape(scoring_rationale_text(record, "impact"))}</p>
                    </div>
                    <div>
                        <span>Frequency Rationale</span>
                        <p>{html.escape(scoring_rationale_text(record, "frequency"))}</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with matrix_col:
        _render_impact_frequency_heatmap(record)


def scoring_rationale_text(record: RiskInventoryRecord, component: str) -> str:
    """Return a 2-3 sentence scoring rationale with a current-period metric."""
    component_key = "impact" if component.lower().startswith("impact") else "likelihood"
    if component_key == "impact":
        base = record.impact_assessment.overall_impact_rationale
    else:
        base = record.likelihood_assessment.rationale
    sentences = _split_sentences(base)[:2]
    if not sentences:
        label = "impact" if component_key == "impact" else "frequency"
        sentences = [
            f"The {label} score reflects the risk profile of this process and the available control evidence."
        ]
    sentences.append(_supporting_metric_sentence(record, component_key))
    return " ".join(sentences[:3])


def _split_sentences(text: str) -> list[str]:
    raw_sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]
    return [_ensure_sentence(sentence) for sentence in raw_sentences]


def _ensure_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


def _supporting_metric_sentence(record: RiskInventoryRecord, component_key: str) -> str:
    def _supports_component(item: Any) -> bool:
        supports = item.supports or []
        if isinstance(supports, str):
            support_values = [supports.lower()]
        else:
            support_values = [str(support).lower() for support in supports]
        return component_key in support_values

    metric = next(
        (
            item
            for item in record.exposure_metrics
            if _supports_component(item)
        ),
        record.exposure_metrics[0] if record.exposure_metrics else None,
    )
    if metric is None:
        return "Current-period indicator: process activity is recurring, measurable, and subject to owner review."
    value = str(metric.metric_value).strip()
    unit = str(metric.metric_unit).strip()
    value_text = f"{value} {unit}".strip() if value else "directional movement"
    return _ensure_sentence(
        f"Current-period indicator: {metric.metric_name} is {value_text} from {metric.source or 'the evidence pack'}"
    )


def selected_risk_kri_rows(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> list[dict[str, Any]]:
    """Richer KRI rows for the selected-risk monitoring section."""
    kris = workspace.kris_for_taxonomy(record.taxonomy_node.id) if workspace else []
    return [
        {
            "KRI ID": kri.kri_id,
            "KRI": kri.kri_name,
            "Definition": kri.metric_definition,
            "Owner": kri.owner,
            "Frequency": kri.measurement_frequency,
            "Source": kri.data_source,
            "Green": kri.thresholds.green,
            "Amber": kri.thresholds.amber,
            "Red": kri.thresholds.red,
            "Rationale": kri.rationale,
            "Escalation Path": kri.escalation_path,
        }
        for kri in kris
    ]


def _render_selected_risk_kri_cards(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> None:
    rows = selected_risk_kri_rows(record, workspace)
    st.markdown('<div class="ri-section-title">KRI Monitoring</div>', unsafe_allow_html=True)
    if not rows:
        _render_neutral_callout("No KRIs are linked to this risk subcategory.")
        return
    for start in range(0, len(rows), 2):
        columns = st.columns(2, gap="medium")
        for offset, row in enumerate(rows[start : start + 2]):
            with columns[offset]:
                st.markdown(_selected_risk_kri_card_html(row), unsafe_allow_html=True)


def _selected_risk_kri_card_html(row: dict[str, Any]) -> str:
    """Return one selected-risk KRI card without nested markdown indentation."""
    return (
        '<div class="ri-selected-kri-card">'
        '<div class="ri-selected-kri-header">'
        "<div>"
        f'<span>{html.escape(str(row["KRI ID"]))}</span>'
        f'<b>{html.escape(str(row["KRI"]))}</b>'
        "</div>"
        '<div class="ri-selected-kri-meta">'
        f'<div><span>Owner</span><b>{html.escape(str(row["Owner"]))}</b></div>'
        f'<div><span>Frequency</span><b>{html.escape(str(row["Frequency"]))}</b></div>'
        f'<div><span>Source</span><b>{html.escape(str(row["Source"]))}</b></div>'
        "</div>"
        "</div>"
        f'<p class="ri-selected-kri-definition"><b>Definition.</b> {html.escape(str(row["Definition"]))}</p>'
        '<div class="ri-selected-kri-threshold-line">'
        f'<span><b>Target</b>{html.escape(str(row["Green"]))}</span>'
        f'<span><b>Watch</b>{html.escape(str(row["Amber"]))}</span>'
        f'<span><b>Escalate</b>{html.escape(str(row["Red"]))}</span>'
        "</div>"
        f'<p class="ri-selected-kri-note"><b>CRO rationale.</b> {html.escape(str(row["Rationale"]))}</p>'
        f'<p class="ri-selected-kri-note"><b>Escalation path.</b> {html.escape(str(row["Escalation Path"]))}</p>'
        "</div>"
    )


def _risk_source_confidence_rows(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
    run: RiskInventoryRun,
) -> list[dict[str, Any]]:
    process = _process_for_record(record, workspace)
    return [
        {
            "Evidence Component": "Process source",
            "Available": "Yes" if run.input_context.source_documents else "No",
            "Detail": "; ".join(run.input_context.source_documents) or run.run_manifest.get("fixture", ""),
        },
        {
            "Evidence Component": "Mapped controls",
            "Available": str(len(record.control_mappings)),
            "Detail": "; ".join(mapping.control_id for mapping in record.control_mappings[:4]),
        },
        {
            "Evidence Component": "Evidence references",
            "Available": str(len(record.evidence_references)),
            "Detail": "; ".join(reference.evidence_id for reference in record.evidence_references[:4]),
        },
        {
            "Evidence Component": "Optional APQC crosswalk",
            "Available": "Yes" if process and process.apqc_crosswalk else "No",
            "Detail": (process.apqc_crosswalk.get("process_name", "") if process else ""),
        },
    ]


def _process_for_record(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> Any | None:
    if workspace is None:
        return None
    return next((process for process in workspace.processes if process.process_id == record.process_id), None)


def _business_unit_for_record(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> str:
    process = _process_for_record(record, workspace)
    if workspace is None or process is None:
        return ""
    return next((bu.bu_name for bu in workspace.business_units if bu.bu_id == process.bu_id), "")


def required_validation_level(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
) -> dict[str, str]:
    """Return the business validation ownership for a risk record."""
    process = _process_for_record(record, workspace)
    bu = (
        next((item for item in workspace.business_units if process and item.bu_id == process.bu_id), None)
        if workspace
        else None
    )
    residual = record.residual_risk.residual_rating.value
    l1 = record.taxonomy_node.level_1_category.lower()
    l2 = record.taxonomy_node.level_2_category.lower()
    gap_count = len(build_control_gaps(record))
    if residual == "Critical":
        level = "Executive Risk Committee"
        reviewer = "BU Head + 2LOD Risk Executive"
        basis = "Critical residual risk requires executive acceptance or remediation commitment."
    elif residual == "High":
        level = "BU Head and 2LOD Challenge"
        reviewer = f"{bu.head if bu else 'BU Head'} + 2LOD Operational Risk"
        basis = "High residual risk requires business ownership and independent challenge."
    elif any(term in f"{l1} {l2}" for term in ("cyber", "privacy", "data", "technology")):
        level = "Specialist Owner Validation"
        reviewer = "Technology/Data Owner + 2LOD Risk Partner"
        basis = "Specialist domain validation is needed for cyber, privacy, data, or technology exposure."
    elif gap_count:
        level = "Process Owner Challenge"
        reviewer = process.owner if process else "Business Process Owner"
        basis = "Mapped coverage gaps require process-owner challenge before approval."
    else:
        level = "1LOD Process Owner"
        reviewer = process.owner if process else "Business Process Owner"
        basis = "Residual exposure is within normal process-owner approval authority."
    return {
        "validation_level": level,
        "required_reviewer": reviewer,
        "business_level": bu.bu_name if bu else _business_unit_for_record(record, workspace),
        "validation_basis": basis,
        "escalation_path": "1LOD Process Owner -> BU Head -> 2LOD Risk -> Executive Risk Committee",
    }


def _render_selected_risk_profile(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
    run: RiskInventoryRun,
) -> None:
    detail = selected_risk_detail(record, workspace)
    st.markdown(
        f"""
        <div class="ri-profile-shell">
            <div class="ri-profile-title">
                <span>{html.escape(detail["risk_id"])}</span>
                <b>{html.escape(detail["level_2_category"])}</b>
            </div>
            <div class="ri-profile-subtitle">
                {html.escape(detail["level_1_category"])} · {html.escape(detail["process_name"])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_risk_profile_snapshot(record)
    body_left, body_right = st.columns([1.25, 0.9], gap="large")
    with body_left:
        st.markdown('<div class="ri-section-title">Risk Profile</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ri-statement">{html.escape(detail["risk_statement"])}</div>',
            unsafe_allow_html=True,
        )
        _render_chip_group("Root causes", list(detail["root_causes"]))
        _render_chip_group("Affected stakeholders", record.risk_statement.affected_stakeholders)
        st.markdown("**Mitigation plan**")
        st.write(detail["mitigation_plan"])
    with body_right:
        st.markdown('<div class="ri-section-title">Impact x Frequency Heatmap</div>', unsafe_allow_html=True)
        _render_impact_frequency_heatmap(record)
        st.caption("Scores use the configured inherent risk matrix. Frequency is the user-facing event-rate input.")


def _render_risk_profile_snapshot(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-profile-snapshot">', unsafe_allow_html=True)
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.markdown(_rating_html(record.inherent_risk.inherent_rating.value, "Inherent"), unsafe_allow_html=True)
    s2.markdown(_rating_html(str(int(record.likelihood_assessment.likelihood_score)), "Frequency"), unsafe_allow_html=True)
    s3.markdown(_rating_html(str(int(record.impact_assessment.overall_impact_score)), "Impact"), unsafe_allow_html=True)
    s4.markdown(_rating_html(record.residual_risk.residual_rating.value, "Residual"), unsafe_allow_html=True)
    s5.markdown(
        _rating_html(record.residual_risk.management_response.response_type.value.title(), "Response"),
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_scoring_rationale(record: RiskInventoryRecord) -> None:
    _render_table(
        [
            {
                "Scoring Component": "Impact",
                "Score": int(record.impact_assessment.overall_impact_score),
                "Rating": record.inherent_risk.inherent_rating.value,
                "Rationale": record.impact_assessment.overall_impact_rationale,
            },
            {
                "Scoring Component": "Frequency",
                "Score": int(record.likelihood_assessment.likelihood_score),
                "Rating": record.likelihood_assessment.likelihood_rating,
                "Rationale": record.likelihood_assessment.rationale,
            },
            {
                "Scoring Component": "Residual",
                "Score": record.residual_risk.residual_score,
                "Rating": record.residual_risk.residual_rating.value,
                "Rationale": record.residual_risk.rationale,
            },
        ]
    )
    st.markdown("**Impact dimensions**")
    _render_table(
        [
            {
                "Impact Dimension": item.dimension.value.replace("_", " ").title(),
                "Impact Score": int(item.score),
                "Assessment Rationale": item.rationale,
            }
            for item in record.impact_assessment.dimensions
        ]
    )


def _render_impact_frequency_heatmap(record: RiskInventoryRecord) -> None:
    rows = impact_frequency_heatmap_rows(record)
    by_frequency = {
        frequency: [row for row in rows if row["Frequency"] == frequency]
        for frequency in [4, 3, 2, 1]
    }
    label_by_frequency = {
        4: "High",
        3: "Medium High",
        2: "Medium Low",
        1: "Low",
    }
    cells = []
    for frequency in [4, 3, 2, 1]:
        cells.append(f"<div class='ri-heat-label'>{label_by_frequency[frequency]}</div>")
        for row in by_frequency[frequency]:
            rating = str(row["Rating"])
            selected = " ri-heat-selected" if row["Selected"] else ""
            cells.append(
                f"<div class='ri-heat-cell ri-{_rating_class(rating)}{selected}'>"
                f"<span>{html.escape(rating)}</span><b>{html.escape(str(row['Score']))}</b></div>"
            )
    impact_labels = "".join(
        f"<div class='ri-heat-axis'>{label}</div>"
        for label in ["", "1 Minimal", "2 Meaningful", "3 Significant", "4 Severe"]
    )
    st.markdown(
        f"""
        <div class="ri-heatmap-wrap">
            <div class="ri-heat-caption">Frequency</div>
            <div class="ri-heatmap">{''.join(cells)}</div>
            <div class="ri-heat-axis-row">{impact_labels}</div>
            <div class="ri-heat-impact-caption">Impact</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_evidence_source_trace(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
    run: RiskInventoryRun,
) -> None:
    evidence_rows = [_evidence_detail_dict(item) for item in record.evidence_references]
    if workspace:
        evidence_rows.extend(
            _evidence_detail_dict(item)
            for item in workspace.evidence_artifacts
            if item.process_id == record.process_id
            or any(item.control_id == mapping.control_id for mapping in record.control_mappings)
        )
    _render_table(evidence_rows)
    trace_rows = [
        {"Trace Type": "Source Document", "Reference": source, "Detail": run.input_context.process_name}
        for source in run.input_context.source_documents
    ]
    process = (
        next((p for p in workspace.processes if p.process_id == record.process_id), None)
        if workspace
        else None
    )
    if process and process.apqc_crosswalk:
        trace_rows.append(
            {
                "Trace Type": "Optional APQC Crosswalk",
                "Reference": process.apqc_crosswalk.get("process_name", process.apqc_crosswalk.get("process_id", "")),
                "Detail": process.apqc_crosswalk.get("rationale", ""),
            }
        )
    if trace_rows:
        st.markdown("**Source trace**")
        _render_table(trace_rows)


def _render_open_findings(record: RiskInventoryRecord, workspace: RiskInventoryWorkspace | None) -> None:
    issues = [
        issue
        for issue in (workspace.issues if workspace else [])
        if issue.risk_id == record.risk_id or issue.process_id == record.process_id
    ]
    mapping_issues = [
        {
            "Issue ID": issue.issue_id,
            "Issue": issue.description,
            "Severity": issue.severity,
            "Status": issue.status,
            "Owner": issue.owner,
            "Source": mapping.control_name,
            "Age (days)": issue.age_days,
        }
        for mapping in record.control_mappings
        for issue in mapping.open_issues
    ]
    rows = [
        {
            "Issue ID": issue.issue_id,
            "Issue": issue.title,
            "Severity": issue.severity,
            "Status": issue.status,
            "Owner": issue.owner,
            "Source": issue.source,
            "Age (days)": issue.age_days,
        }
        for issue in issues
    ] + mapping_issues
    if rows:
        _render_table(rows)
    else:
        st.success("No open findings are mapped to this risk.")


def _render_mitigation_plan(record: RiskInventoryRecord) -> None:
    st.markdown(f"**Management response:** {record.residual_risk.management_response.response_type.value.title()}")
    st.write(record.residual_risk.management_response.recommended_action)
    if record.action_plan:
        _render_table([item.model_dump() for item in record.action_plan])
    else:
        st.info("No discrete action items are recorded for this risk.")


def _evidence_detail_dict(item: Any) -> dict[str, Any]:
    return {
        "Evidence ID": getattr(item, "evidence_id", ""),
        "Evidence": getattr(item, "name", getattr(item, "description", "")),
        "Type": getattr(item, "artifact_type", getattr(item, "evidence_type", "")),
        "Source": getattr(item, "source", getattr(item, "source_system", "")),
        "Owner": getattr(item, "owner", ""),
        "Description": getattr(item, "description", ""),
    }


def _portfolio_heat_value(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "None"
    high_plus = _high_plus_count(rows)
    if high_plus >= 2:
        return "High"
    if high_plus == 1:
        return "Medium"
    if len(rows) >= 3:
        return "Elevated"
    return "Low"


def _render_root_cause_detail(
    record: RiskInventoryRecord, workspace: RiskInventoryWorkspace | None
) -> None:
    causes = record.risk_statement.causes or record.taxonomy_node.typical_root_causes
    if not causes:
        return
    st.markdown('<div class="ri-section-title">Root Cause Lens</div>', unsafe_allow_html=True)
    taxonomy = workspace.root_cause_taxonomy if workspace else []
    rows: list[dict[str, Any]] = []
    for cause in causes:
        match = next(
            (
                item
                for item in taxonomy
                if item.name.lower() in cause.lower()
                or cause.lower() in item.name.lower()
                or any(example.lower() in cause.lower() for example in item.examples)
            ),
            None,
        )
        rows.append(
            {
                "Root Cause": cause,
                "Taxonomy Category": match.category if match else "Inferred",
                "Taxonomy Code": match.code if match else "",
                "Definition": match.description if match else "Generated from the risk taxonomy node and process context.",
            }
        )
    _render_table(rows)


# ---------------------------------------------------------------------------
# Control Mapping tab
# ---------------------------------------------------------------------------


def _render_workspace_control_mapping(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None,
) -> None:
    rows = _workspace_control_mapping_rows(workspace, selected_bu_id)
    if not rows:
        st.info("No control mappings are available for the selected scope.")
        return

    selected_bu = next(
        (bu for bu in workspace.business_units if bu.bu_id == selected_bu_id),
        None,
    )
    scope_label = selected_bu.bu_name if selected_bu else "All Business Units"
    mapped_controls = sum(int(row["Mapped Controls"]) for row in rows)
    coverage_gaps = sum(_coverage_status_has_gap(str(row["Coverage Status"])) for row in rows)

    st.markdown('<div class="ri-section-title">Control Mapping</div>', unsafe_allow_html=True)
    st.caption(
        f"{scope_label} is loaded. Select a process focus above to inspect risk-to-control coverage and control score support."
    )
    m1, m2, m3 = st.columns(3)
    m1.markdown(_metric_card("Scoped Risks", str(len(rows)), "neutral"), unsafe_allow_html=True)
    m2.markdown(_metric_card("Mapped Controls", str(mapped_controls), "teal"), unsafe_allow_html=True)
    m3.markdown(_metric_card("Coverage Gaps", str(coverage_gaps), "red" if coverage_gaps else "green"), unsafe_allow_html=True)
    _render_neutral_callout(
        "Workspace-level control mapping is intentionally summarized here. Choose a process in the Scope Selector for the demo-ready control coverage view."
    )


def _render_control_mapping(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None = None,
) -> None:
    record = _risk_selector(run, "ri_mapping_select")
    _render_risk_header(record)

    st.markdown('<div class="ri-section-title">Selected Risk Control Score</div>', unsafe_allow_html=True)
    _render_control_score_panel(record)

    st.markdown('<div class="ri-section-title">Selected Risk Control Coverage</div>', unsafe_allow_html=True)
    if not record.control_mappings:
        st.warning("No controls are mapped to this risk. This is a coverage gap.")
    else:
        for mapping in record.control_mappings:
            statement_detail = control_statement_detail(record, mapping, workspace)
            design_rating = (
                mapping.design_effectiveness.rating.value if mapping.design_effectiveness else "Not Rated"
            )
            operating_rating = (
                mapping.operating_effectiveness.rating.value
                if mapping.operating_effectiveness
                else "Not Rated"
            )
            assessment_html = "".join(
                _control_assessment_tile(label, value, rationale, tone)
                for label, value, rationale, tone in (
                    (
                        "Coverage",
                        mapping.coverage_assessment.title(),
                        _coverage_rationale(record, mapping),
                        _coverage_class(mapping.coverage_assessment),
                    ),
                    (
                        "Design",
                        design_rating,
                        mapping.design_effectiveness.rationale if mapping.design_effectiveness else "Design effectiveness has not been rated.",
                        _rating_class(design_rating),
                    ),
                    (
                        "Operating",
                        operating_rating,
                        mapping.operating_effectiveness.rationale if mapping.operating_effectiveness else "Operating effectiveness has not been rated.",
                        _rating_class(operating_rating),
                    ),
                )
            )
            badge_html = "".join(
                _badge(label, value, "neutral")
                for label, value in (
                    ("Owner", statement_detail["owner"]),
                    ("Frequency", statement_detail["frequency"]),
                    ("Type", statement_detail["control_type"]),
                )
                if value
            )
            root_causes = mapping.mapped_root_causes or record.risk_statement.causes or record.taxonomy_node.typical_root_causes
            root_cause_html = "".join(
                f'<span class="ri-chip">{html.escape(root_cause)}</span>'
                for root_cause in root_causes[:5]
            )
            st.markdown(
                f"""
                <div class="ri-control-coverage-panel">
                    <div class="ri-control-head">
                        <div>
                            <span class="ri-control-id">{html.escape(mapping.control_id)}</span>
                            <b>{html.escape(mapping.control_name)}</b>
                        </div>
                        <span class="ri-control-type">{html.escape(statement_detail["coverage_label"])}</span>
                    </div>
                    <div class="ri-control-context ri-control-statement-wrap">
                        <b>Optimal full-coverage control statement</b>
                        <p class="ri-control-statement">{html.escape(statement_detail["control_statement"])}</p>
                        <p class="ri-evidence-line"><b>Evidence to prove full coverage.</b> {html.escape(statement_detail["expected_evidence"])}</p>
                    </div>
                    <div class="ri-control-badge-row">{badge_html}</div>
                    <div class="ri-control-assessment-grid">{assessment_html}</div>
                    <div class="ri-control-context">
                        <b>Risk coverage rationale</b>
                        <p>{html.escape(mapping.mitigation_rationale)}</p>
                    </div>
                    <div class="ri-control-context">
                        <b>Mapped root causes</b>
                        <div>{root_cause_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    _render_process_linked_controls_table(run)


def _render_process_linked_controls_table(run: RiskInventoryRun) -> None:
    rows = _run_control_mapping_rows(run)
    st.markdown('<div class="ri-section-title">All Mapped Controls In This Process</div>', unsafe_allow_html=True)
    if not rows:
        _render_neutral_callout("No controls are linked to this process.")
        return
    st.caption(
        f"{run.input_context.process_name}: {len(rows)} mapped control(s) across {len(run.records)} selected process risk record(s)."
    )
    _render_table(rows)


def control_statement_detail(
    record: RiskInventoryRecord,
    mapping: ControlMapping,
    workspace: RiskInventoryWorkspace | None = None,
) -> dict[str, str]:
    """Return display-ready statement metadata for optimal full risk coverage."""
    recommendation = next(iter(build_synthetic_control_recommendations(record, workspace)), None)
    if recommendation:
        return {
            "control_statement": recommendation.control_statement,
            "owner": recommendation.suggested_owner,
            "frequency": recommendation.frequency,
            "control_type": recommendation.control_type,
            "expected_evidence": recommendation.expected_evidence,
            "coverage_label": "Full coverage target",
        }

    inventory = _control_inventory_entry(mapping.control_id, workspace)
    owner = inventory.owner if inventory and inventory.owner else _statement_owner_fallback(mapping)
    frequency = inventory.frequency if inventory and inventory.frequency else "Defined by control design"
    control_type = mapping.control_type or (inventory.control_type if inventory else "") or "Risk coverage"
    return {
        "control_statement": _mapped_control_statement(record, owner, frequency, control_type),
        "owner": owner,
        "frequency": frequency,
        "control_type": control_type,
        "expected_evidence": _mapped_control_expected_evidence(mapping, workspace),
        "coverage_label": "Full coverage target",
    }


def _control_assessment_tile(
    label: str,
    value: str,
    rationale: str,
    tone: str,
) -> str:
    return (
        f'<div class="ri-control-assessment ri-assessment-{html.escape(tone)}">'
        f"<span>{html.escape(label)}</span>"
        f"<b>{html.escape(value or 'Not Rated')}</b>"
        f"<p>{html.escape(rationale or 'No rationale is recorded for this score.')}</p>"
        "</div>"
    )


def _coverage_rationale(record: RiskInventoryRecord, mapping: ControlMapping) -> str:
    root_causes = mapping.mapped_root_causes or record.risk_statement.causes or record.taxonomy_node.typical_root_causes
    if mapping.mitigation_rationale:
        return mapping.mitigation_rationale
    if root_causes:
        return (
            f"{mapping.coverage_assessment.title()} coverage is assigned because the control maps to "
            f"{', '.join(root_causes[:3])}."
        )
    return f"{mapping.coverage_assessment.title()} coverage is assigned from the selected risk-to-control mapping."


def _control_inventory_entry(
    control_id: str,
    workspace: RiskInventoryWorkspace | None,
) -> ControlInventoryEntry | None:
    if not workspace:
        return None
    return next(
        (control for control in workspace.control_inventory if control.control_id == control_id),
        None,
    )


def _statement_owner_fallback(mapping: ControlMapping) -> str:
    issue_owner = next((issue.owner for issue in mapping.open_issues if issue.owner), "")
    return issue_owner or "Control Owner"


def _mapped_control_statement(
    record: RiskInventoryRecord,
    owner: str,
    frequency: str,
    control_type: str,
) -> str:
    frequency_phrase = ""
    if frequency and frequency != "Defined by control design":
        frequency_phrase = f"{frequency.lower()} "
    control_type_phrase = control_type.lower() if control_type else "risk coverage"
    return (
        f"{owner} performs a {frequency_phrase}{control_type_phrase} control for "
        f"{record.process_name} to validate that {record.taxonomy_node.level_2_category.lower()} "
        "drivers are identified, escalated, remediated, and evidenced before residual exposure exceeds appetite."
    )


def _mapped_control_expected_evidence(
    mapping: ControlMapping,
    workspace: RiskInventoryWorkspace | None,
) -> str:
    if workspace:
        artifacts = [
            artifact
            for artifact in workspace.evidence_artifacts
            if artifact.control_id == mapping.control_id
        ]
        if artifacts:
            artifact_summary = ", ".join(
                f"{artifact.name} ({artifact.artifact_type})"
                for artifact in artifacts[:3]
            )
            retention = next((artifact.retention for artifact in artifacts if artifact.retention), "")
            retention_note = f"; retained for {retention}" if retention else ""
            return f"{artifact_summary}{retention_note}."

    return "Control execution evidence, owner sign-off, exception tracking, and remediation support retained with the risk record."


def control_score_row(record: RiskInventoryRecord) -> dict[str, Any]:
    """Return the selected-risk control score summary for Control Mapping."""
    control_strength = record.control_environment.control_environment_rating.value
    configured_scores = MatrixConfigLoader().residual_matrix().get("control_environment_scores", {})
    score = int(configured_scores.get(control_strength, record.residual_risk.control_environment_score))
    return {
        "Control Score": score,
        "Control Strength": control_strength,
        "Mapped Controls": len(record.control_mappings),
        "Coverage Status": _record_coverage_status(record),
        "Rationale": record.control_environment.rationale,
    }


def _render_control_score_panel(record: RiskInventoryRecord) -> None:
    row = control_score_row(record)
    tone = _rating_class(str(row["Control Strength"]))
    supporting_cells = "".join(
        f"<div><span>{html.escape(label)}</span><b>{html.escape(str(value))}</b></div>"
        for label, value in row.items()
        if label not in {"Control Score", "Rationale"}
    )
    st.markdown(
        f"""
        <div class="ri-control-score-panel ri-score-{tone}">
            <div class="ri-control-score-main">
                <span>Control Score</span>
                <b class="ri-control-score-value ri-score-{tone}">{html.escape(str(row["Control Score"]))}</b>
                <p>{html.escape(str(row["Control Strength"]))} control strength</p>
            </div>
            <div class="ri-control-score-rationale">
                <b>Rationale</b>
                <p>{html.escape(str(row["Rationale"]))}</p>
            </div>
            <div class="ri-control-score-grid">{supporting_cells}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Control gap lab
# ---------------------------------------------------------------------------


def _render_control_gap_lab(
    selected_run: RiskInventoryRun | None,
    workspace: RiskInventoryWorkspace | None,
    selected_bu_id: str | None,
) -> None:
    st.markdown('<div class="ri-section-title">Gap Analysis</div>', unsafe_allow_html=True)
    records = _scoped_records(workspace, selected_bu_id, selected_run)
    if not records:
        st.info("No risks are available for the selected scope.")
        _render_gap_analysis_export(selected_run, workspace)
        return

    if selected_run is None:
        _render_neutral_callout(
            "Gap analysis is most useful once a process is selected. Choose a process in the Scope Selector to review individual gaps, proposed controls, evidence expectations, and remediation rationale."
        )
        _render_gap_analysis_export(selected_run, workspace)
        return

    gap_rows = []
    recommendation_rows = []
    for record in records:
        gaps = build_control_gaps(record)
        recommendations = build_synthetic_control_recommendations(record, workspace)
        gap_rows.extend(
            {
                "Risk Record ID": record.risk_id,
                "Process": record.process_name,
                "Risk Subcategory": record.taxonomy_node.level_2_category,
                "Gap Type": gap.gap_type,
                "Severity": gap.severity,
                "Description": gap.description,
                "Existing Controls": "; ".join(gap.existing_control_ids),
            }
            for gap in gaps
        )
        recommendation_rows.extend(
            {
                "Risk Record ID": record.risk_id,
                "Recommendation ID": rec.recommendation_id,
                "Control": rec.control_name,
                "Control Type": rec.control_type,
                "Owner": rec.suggested_owner,
                "Frequency": rec.frequency,
                "Priority": rec.priority,
                "Expected Evidence": rec.expected_evidence,
                "Control Statement": rec.control_statement,
            }
            for rec in recommendations
        )

    if selected_run:
        record = _risk_selector(selected_run, "ri_gap_lab_select")
        _render_risk_header(record)
        selected_recommendations = build_synthetic_control_recommendations(record, workspace)
        st.markdown('<div class="ri-section-title">Residual Risk Calculation</div>', unsafe_allow_html=True)
        _render_residual_calculation_strip(record)
        st.markdown('<div class="ri-section-title">Selected Control Statement</div>', unsafe_allow_html=True)
        if selected_recommendations:
            for recommendation in selected_recommendations:
                root_cause_html = "".join(
                    f'<span class="ri-chip">{html.escape(root_cause)}</span>'
                    for root_cause in recommendation.addressed_root_causes[:5]
                )
                st.markdown(
                    f"""
                    <div class="ri-gap-card">
                        <div class="ri-control-head">
                            <div>
                                <span class="ri-control-id">{html.escape(recommendation.recommendation_id)}</span>
                                <b>{html.escape(recommendation.control_name)}</b>
                            </div>
                            <span class="ri-control-type">{html.escape(recommendation.priority)} priority</span>
                        </div>
                        <p class="ri-control-statement">{html.escape(recommendation.control_statement)}</p>
                        <div class="ri-control-badge-row">
                            {_badge("Owner", recommendation.suggested_owner, "neutral")}
                            {_badge("Frequency", recommendation.frequency, "neutral")}
                            {_badge("Type", recommendation.control_type, "neutral")}
                        </div>
                        <p class="ri-evidence-line"><b>Expected evidence.</b> {html.escape(recommendation.expected_evidence)}</p>
                        <div class="ri-control-context">
                            <b>Why this control exists</b>
                            <p>{html.escape(recommendation.rationale)}</p>
                        </div>
                        <div class="ri-control-context">
                            <b>Root causes addressed</b>
                            <div>{root_cause_html}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("No synthetic control statement is required for the selected risk.")

    st.markdown('<div class="ri-section-title">Gap Summary</div>', unsafe_allow_html=True)
    if gap_rows:
        _render_table(gap_rows)
    else:
        st.success("No material control coverage gaps are identified in the selected scope.")
    st.markdown('<div class="ri-section-title">Synthetic Control Recommendations</div>', unsafe_allow_html=True)
    if recommendation_rows:
        _render_table(recommendation_rows)
    else:
        st.success("No synthetic control recommendations are required for the selected scope.")
    _render_gap_analysis_export(selected_run, workspace)


def _render_gap_analysis_export(
    selected_run: RiskInventoryRun | None,
    workspace: RiskInventoryWorkspace | None,
) -> None:
    export_run = selected_run or (workspace.runs[0] if workspace and workspace.runs else None)
    if export_run is None:
        return
    _download_export(export_run, "gap_analysis", workspace)


def residual_calculation_row(record: RiskInventoryRecord) -> dict[str, Any]:
    """Return the selected-risk residual calculation summary for Gap Analysis."""
    return {
        "Inherent Risk": record.inherent_risk.inherent_rating.value,
        "Control Score": int(record.residual_risk.control_environment_score),
        "Residual Risk Score": risk_rating_scale_score(record.residual_risk.residual_rating.value),
        "Rationale": residual_risk_rationale_text(record),
    }


def risk_rating_scale_score(rating: str) -> int:
    """Return the front-end 1-4 score basis for risk ratings."""
    return {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}.get(rating, 0)


def residual_risk_rationale_text(record: RiskInventoryRecord) -> str:
    """Return a plain-language residual-risk rationale without rating-score labels."""
    residual_rating = record.residual_risk.residual_rating.value
    inherent_rating = record.inherent_risk.inherent_rating.value
    control_score = int(record.residual_risk.control_environment_score)
    control_strength = record.control_environment.control_environment_rating.value
    gap_count = len(build_control_gaps(record))
    recommendation_count = len(build_synthetic_control_recommendations(record, None))
    base = _score_label_to_rating_text(record.residual_risk.rationale)
    base = base.replace("matrix-calculated", "calculated").replace("deterministic", "configured")
    base_sentences = _split_sentences(base)
    opening = (
        f"Residual risk is rated {residual_rating} on the 1-4 basis because the inherent risk is {inherent_rating} "
        f"and the current control score is {control_score}, reflecting a {control_strength} control environment."
    )
    control_sentence = _ensure_sentence(
        f"{record.control_environment.rationale} The selected risk has {len(record.control_mappings)} mapped control(s), "
        f"{gap_count} identified gap(s), and {recommendation_count} suggested control enhancement(s)"
    )
    action_sentence = _ensure_sentence(
        f"Management response is {record.residual_risk.management_response.response_type.value.title()}: "
        f"{record.residual_risk.management_response.recommended_action}"
    )
    sentences = [opening]
    if base_sentences:
        sentences.append(base_sentences[0])
    sentences.extend([control_sentence, action_sentence])
    return " ".join(sentences[:4])


def _score_label_to_rating_text(text: str) -> str:
    return re.sub(r"\b(Low|Medium|High|Critical)-\d+\b", r"\1", text)


def _render_residual_calculation_strip(record: RiskInventoryRecord) -> None:
    row = residual_calculation_row(record)
    cells = "".join(
        f"<div><span>{html.escape(label)}</span><b>{html.escape(str(value))}</b></div>"
        for label, value in row.items()
        if label != "Rationale"
    )
    st.markdown(f'<div class="ri-residual-calc-strip">{cells}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ri-neutral-callout"><b>Rationale.</b> {html.escape(str(row["Rationale"]))}</div>',
        unsafe_allow_html=True,
    )


def _scoped_records(
    workspace: RiskInventoryWorkspace | None,
    selected_bu_id: str | None,
    selected_run: RiskInventoryRun | None,
) -> list[RiskInventoryRecord]:
    if selected_run:
        return list(selected_run.records)
    if workspace is None:
        return []
    processes = workspace.processes_for_bu(selected_bu_id) if selected_bu_id else workspace.processes
    records: list[RiskInventoryRecord] = []
    for process in processes:
        run = workspace.run_for_process(process.process_id)
        if run:
            records.extend(run.records)
    return records


def _render_control_coverage(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">Control Coverage</div>', unsafe_allow_html=True)
    mappings = record.control_mappings
    if not mappings:
        st.warning("No controls are mapped to this risk. This is a coverage gap requiring management response.")
        return

    type_coverage = Counter(m.control_type or "Unspecified" for m in mappings)
    strong_or_satisfactory = sum(
        1
        for mapping in mappings
        if mapping.design_effectiveness
        and mapping.operating_effectiveness
        and mapping.design_effectiveness.rating.value in {"Strong", "Satisfactory"}
        and mapping.operating_effectiveness.rating.value in {"Strong", "Satisfactory"}
    )

    summary_cols = st.columns(3)
    summary_cols[0].metric("Mapped Controls", len(mappings))
    summary_cols[1].metric("Strong/Satisfactory", strong_or_satisfactory)
    summary_cols[2].metric("Control Types", len(type_coverage))

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("**Mapped controls**")
        _render_table(
            [
                {
                    "Control": m.control_name,
                    "Control Type": m.control_type,
                    "Coverage Assessment": m.coverage_assessment.title(),
                }
                for m in mappings
            ],
        )
    with right:
        st.markdown("**Coverage by control type**")
        _render_table(
            [
                {"Control Type": ctype, "Mapped Control Count": count}
                for ctype, count in type_coverage.most_common()
            ],
        )

    st.markdown("**Coverage gaps**")
    gaps: list[str] = [gap for gap in record.coverage_gaps if "root cause" not in gap.lower()]
    if gaps:
        for gap in gaps:
            st.markdown(f"- {html.escape(gap)}")
    else:
        st.success("No material control coverage gaps identified for this risk.")


def _render_effectiveness_detail(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">Effectiveness Detail</div>', unsafe_allow_html=True)
    mappings = record.control_mappings
    if not mappings:
        st.info("No control effectiveness to report.")
        return

    open_issue_total = sum(len(m.open_issues) for m in mappings)
    high_sev_open = sum(
        1 for m in mappings for i in m.open_issues if i.severity.lower() in {"high", "critical"}
    )
    strong_design = sum(
        1 for m in mappings if m.design_effectiveness and m.design_effectiveness.rating.value == "Strong"
    )
    needs_improvement = sum(
        1
        for m in mappings
        if m.operating_effectiveness and m.operating_effectiveness.rating.value == "Improvement Needed"
    )

    a, b, c, d = st.columns(4)
    a.metric("Strong Design", strong_design)
    b.metric("Operating Improvement Needed", needs_improvement)
    c.metric("Open Issues", open_issue_total)
    d.metric("High/Critical Issues", high_sev_open)

    st.markdown("**Effectiveness by control**")
    _render_table(
        [
            {
                "Control": m.control_name,
                "Design Effectiveness": m.design_effectiveness.rating.value if m.design_effectiveness else "Not Rated",
                "Operating Effectiveness": m.operating_effectiveness.rating.value if m.operating_effectiveness else "Not Rated",
                "Open Issues": len(m.open_issues),
                "Evidence Quality": m.evidence_quality.rating if m.evidence_quality else "Not Assessed",
                "Last Tested": m.evidence_quality.last_tested if m.evidence_quality else "",
            }
            for m in mappings
        ],
    )

    if open_issue_total:
        st.markdown("**Open issues**")
        _render_table(
            [
                {
                    "Issue ID": issue.issue_id,
                    "Control": m.control_name,
                    "Severity": issue.severity,
                    "Age (days)": issue.age_days,
                    "Owner": issue.owner,
                    "Status": issue.status,
                    "Description": issue.description,
                }
                for m in mappings
                for issue in m.open_issues
            ],
        )


# ---------------------------------------------------------------------------
# KRI Recommendations (replaces Appetite & Decisioning)
# ---------------------------------------------------------------------------


def _render_kri_recommendations(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None,
    *,
    include_program_design: bool = True,
) -> None:
    st.markdown(
        '<div class="ri-section-title">Recommended Key Risk Indicators (KRIs)</div>',
        unsafe_allow_html=True,
    )

    candidates: list[KRIDefinition] = []
    if workspace:
        candidates = workspace.kris_for_taxonomy(record.taxonomy_node.id)

    if not candidates:
        st.info(
            "No KRIs are pre-defined in the workspace for this risk taxonomy node. "
            "Use the executive guidance below to design a KRI for this risk."
        )
        _render_kri_design_guidance(record)
        return

    st.markdown(
        f"<div class='ri-kri-intro'>The KRI library contains "
        f"<b>{len(candidates)}</b> indicator(s) mapped to "
        f"<b>{html.escape(record.taxonomy_node.level_2_category)}</b>. The recommendation "
        "below is written from a CRO perspective and follows traditional KRI assessment "
        "guidelines: the metric must be measurable, owned, time-bounded, and have green / "
        "amber / red thresholds that drive decisions before loss events materialize.</div>",
        unsafe_allow_html=True,
    )

    for kri in candidates:
        st.markdown(
            f"""
            <div class="ri-kri-card">
                <div class="ri-kri-header">
                    <div>
                        <span class="ri-kri-id">{html.escape(kri.kri_id)}</span>
                        <span class="ri-kri-name">{html.escape(kri.kri_name)}</span>
                    </div>
                    <div class="ri-kri-meta">
                        <span>Owner</span><b>{html.escape(kri.owner)}</b>
                        <span>Frequency</span><b>{html.escape(kri.measurement_frequency)}</b>
                        <span>Source</span><b>{html.escape(kri.data_source)}</b>
                    </div>
                </div>
                <div class="ri-kri-definition"><b>Definition.</b> {html.escape(kri.metric_definition)}</div>
                <div class="ri-kri-thresholds">
                    <div class="ri-kri-threshold ri-low"><span>Green</span><b>{html.escape(kri.thresholds.green)}</b></div>
                    <div class="ri-kri-threshold ri-medium"><span>Amber</span><b>{html.escape(kri.thresholds.amber)}</b></div>
                    <div class="ri-kri-threshold ri-high"><span>Red</span><b>{html.escape(kri.thresholds.red)}</b></div>
                </div>
                <div class="ri-kri-narrative"><b>CRO rationale.</b> {html.escape(kri.rationale)}</div>
                <div class="ri-kri-narrative"><b>Escalation path.</b> {html.escape(kri.escalation_path)}</div>
                <div class="ri-kri-narrative"><b>Where and how to use this KRI.</b> {html.escape(kri.placement_guidance)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if include_program_design:
        _render_kri_program_design(record)


def _render_kri_program_design(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">KRI Program Design Notes</div>', unsafe_allow_html=True)
    residual = record.residual_risk.residual_rating.value
    inherent = record.inherent_risk.inherent_rating.value
    plan_lines: list[str] = []
    if residual in {"High", "Critical"}:
        plan_lines.append(
            f"**Executive monitoring.** Because residual is {residual}, all KRIs above should be reviewed "
            "weekly by the business unit head and monthly by the Operational Risk Committee until residual is "
            "sustained at Medium or below for two consecutive quarters."
        )
    elif residual == "Medium":
        plan_lines.append(
            "**Executive monitoring.** Residual is Medium — review KRIs monthly with the business unit head and "
            "quarterly to the Operational Risk Committee. Promote any sustained amber to monthly committee review."
        )
    else:
        plan_lines.append(
            "**Executive monitoring.** Residual is Low — KRIs should still be measured at the documented "
            "frequency above, but executive reporting can be quarterly with a trend chart in the annual ERMC pack."
        )
    plan_lines.append(
        "**Threshold calibration.** Green/amber/red thresholds must be reviewed annually (or after any "
        "material change in process volume, technology, or organizational structure). The CRO should challenge "
        "any KRI that has not breached amber for four consecutive quarters — either the threshold is too "
        "loose or the KRI is no longer the leading indicator it was designed to be."
    )
    plan_lines.append(
        f"**Indicator family.** The KRI(s) above measure inherent drivers ({inherent}) and control performance. "
        "A complete program should pair these leading indicators with at least one lagging indicator "
        "(loss events, customer complaints, audit findings) so the committee sees both early warnings and realized outcomes."
    )
    plan_lines.append(
        "**Ownership and independence.** Production of each KRI should be independent from execution of "
        "the underlying control where possible (e.g., 2LOD or Internal Audit produces, 1LOD acts). "
        "Document the producer, the consumer, and the escalation owner for each KRI in the bank's KRI catalog."
    )
    plan_lines.append(
        "**Avoid KRI proliferation.** A focused set of 3–5 indicators per risk taxonomy node is more "
        "actionable than a long list. The KRIs surfaced above were curated against this discipline."
    )
    for line in plan_lines:
        st.markdown(line)


def _render_kri_design_guidance(record: RiskInventoryRecord) -> None:
    metrics = ", ".join(m.metric_name for m in record.exposure_metrics) or "see exposure section"
    st.markdown(
        f"""
        <div class="ri-kri-card">
            <div class="ri-kri-narrative">
                <b>How to design a KRI for {html.escape(record.taxonomy_node.level_2_category)}.</b>
                Start from the risk category, the risk statement, and the process evidence already collected
                ({html.escape(metrics)}).
                A defensible KRI is: (1) measurable from a system-of-record, (2) owned by a named role,
                (3) reported on a documented cadence, (4) has green/amber/red thresholds that drive
                decisions, and (5) is paired with a lagging outcome metric. Avoid creating KRIs that
                require manual aggregation — they will not survive a change of personnel.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_residual_review_summary(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">Reviewer Summary</div>', unsafe_allow_html=True)
    if not record.review_challenges:
        st.info("No reviewer activity is recorded yet.")
        return
    review = record.review_challenges[0]
    a, b, c = st.columns(3)
    a.markdown(_rating_html(review.review_status.value, "Review Status"), unsafe_allow_html=True)
    b.markdown(_rating_html(review.approval_status.value, "Approval"), unsafe_allow_html=True)
    c.markdown(
        f'<div class="ri-fact-grid"><div><span>Reviewer</span><b>{html.escape(review.reviewer or "Unassigned")}</b></div></div>',
        unsafe_allow_html=True,
    )

    if review.challenge_comments:
        st.markdown("**Reviewer comments**")
        st.write(review.challenge_comments)

    if review.challenged_fields:
        _render_chip_group("Fields requiring review", review.challenged_fields)

    st.caption("Reviewer workflow details are retained in the reviewer-ready export.")


def _render_review(run: RiskInventoryRun, workspace: RiskInventoryWorkspace | None = None) -> None:
    rows = review_validation_rows(run, workspace)
    selected_id = st.session_state.get("ri_review_selected_risk_id") or (rows[0]["Risk ID"] if rows else "")
    if selected_id not in {row["Risk ID"] for row in rows} and rows:
        selected_id = rows[0]["Risk ID"]
    st.session_state["ri_review_selected_risk_id"] = selected_id

    st.markdown('<div class="ri-section-title">Reviewer Workbench</div>', unsafe_allow_html=True)
    st.caption(
        "Analyst view for validating the agent output against bank context, deterministic scoring, controls, evidence, KRIs, gaps, and approval authority."
    )
    _download_review_workbook(run, workspace)
    _render_review_summary_strip(rows)
    left, right = st.columns([1.05, 1.55], gap="large")
    with left:
        st.markdown("**Validation Queue**")
        for row in rows:
            selected = " ri-queue-selected" if row["Risk ID"] == selected_id else ""
            st.markdown(
                f"""
                <div class="ri-review-queue{selected}">
                    <div><span>{html.escape(str(row["Risk ID"]))}</span><b>{html.escape(str(row["Risk Subcategory"]))}</b></div>
                    <p>{html.escape(str(row["Business Unit"]))} · {html.escape(str(row["Process"]))}</p>
                    <div>
                        {_badge("Residual", str(row["Residual Risk"]), _rating_class(str(row["Residual Risk"])))}
                        {_badge("Validation", str(row["Validation Level"]), "neutral")}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Review {row['Risk ID']}", key=f"ri_review_queue_{row['Risk ID']}", width="stretch"):
                selected_id = str(row["Risk ID"])
                st.session_state["ri_review_selected_risk_id"] = selected_id
        with st.expander("Queue table", expanded=False):
            _render_table(rows)

    record = next(record for record in run.records if record.risk_id == selected_id)
    dossier = selected_review_dossier(record, workspace)
    with right:
        _render_review_dossier(dossier)

    review = record.review_challenges[0] if record.review_challenges else None
    existing_decision = _review_decision_for_risk(record.risk_id)
    status_options = ["Not Started", "Pending Review", "Challenged", "Approved"]
    approval_options = ["Draft", "Approved", "Rejected"]
    current_status = (
        existing_decision.review_status.value
        if existing_decision
        else review.review_status.value
        if review
        else "Pending Review"
    )
    current_approval = (
        existing_decision.approval_status.value
        if existing_decision
        else review.approval_status.value
        if review
        else "Draft"
    )
    st.markdown('<div class="ri-section-title">Reviewer Decision Capture</div>', unsafe_allow_html=True)
    form_left, form_right = st.columns([1, 1], gap="large")
    with form_left:
        reviewer = st.text_input(
            "Reviewer / Accountable Validator",
            value=(
                existing_decision.reviewer
                if existing_decision
                else review.reviewer
                if review
                else dossier["validation"]["required_reviewer"]
            ),
            key=f"ri_review_reviewer_{record.risk_id}",
        )
        selected_status = st.selectbox(
            "Review Status",
            status_options,
            index=status_options.index(current_status) if current_status in status_options else 1,
            key=f"ri_review_status_{record.risk_id}",
        )
        selected_approval = st.selectbox(
            "Approval Status",
            approval_options,
            index=approval_options.index(current_approval) if current_approval in approval_options else 0,
            key=f"ri_review_approval_{record.risk_id}",
        )
        final_value = st.text_input(
            "Final Approved Value",
            value=(
                existing_decision.final_approved_value
                if existing_decision
                else review.final_approved_value
                if review
                else record.residual_risk.residual_rating.value
            ),
            key=f"ri_review_final_{record.risk_id}",
        )
    with form_right:
        comments = st.text_area(
            "Challenge Comments",
            value=(
                existing_decision.challenge_comments
                if existing_decision
                else review.challenge_comments
                if review
                else ""
            ),
            height=100,
            key=f"ri_review_comments_{record.risk_id}",
            help="Capture business challenge comments before final approval.",
        )
        adjusted = st.text_area(
            "Reviewer Adjusted Value",
            value=(
                existing_decision.reviewer_adjusted_value
                if existing_decision
                else review.reviewer_adjusted_value
                if review
                else ""
            ),
            height=80,
            key=f"ri_review_adjusted_{record.risk_id}",
        )
        rationale = st.text_area(
            "Reviewer Rationale",
            value=(
                existing_decision.reviewer_rationale
                if existing_decision
                else review.reviewer_rationale
                if review
                else dossier["validation"]["validation_basis"]
            ),
            height=80,
            key=f"ri_review_rationale_{record.risk_id}",
        )
    decision = ReviewDecision(
        risk_id=record.risk_id,
        reviewer=reviewer,
        review_status=ReviewStatus(selected_status),
        approval_status=ApprovalStatus(selected_approval),
        challenge_comments=comments,
        reviewer_adjusted_value=adjusted,
        reviewer_rationale=rationale,
        final_approved_value=final_value,
    )
    _store_review_decision(decision)
    if review:
        _render_chip_group("Fields requiring review", review.challenged_fields)
    st.caption("Review decisions are stored in session state and included in the Excel workbook artifact.")
    st.markdown('<div class="ri-section-title">Validation Findings</div>', unsafe_allow_html=True)
    findings = [finding for finding in run.validation_findings if finding.record_id == record.risk_id]
    if findings:
        _render_table([finding.model_dump() for finding in findings])
    else:
        st.success("No validation findings for this record.")


def _download_review_workbook(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None = None,
) -> None:
    data = risk_inventory_review_excel_bytes(run, workspace, _session_review_decisions())
    st.markdown(
        '<div class="ri-review-asset"><b>HITL review workbook</b>'
        '<p>Download the reviewer-ready asset with validation queue, checklist, scoring rationale, control suggestions, evidence/KRI trace, and decision log.</p></div>',
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download HITL Review Workbook",
        data=data,
        file_name=f"{run.run_id}_hitl_review_workbook.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"ri_review_xlsx_{run.run_id}",
        width="stretch",
    )


def _render_review_summary_strip(rows: list[dict[str, Any]]) -> None:
    status_counts = Counter(str(row["Review Status"]) for row in rows)
    summary = {
        "Risks": str(len(rows)),
        "Pending": str(status_counts.get("Pending Review", 0) + status_counts.get("Not Started", 0)),
        "Challenged": str(status_counts.get("Challenged", 0)),
        "Approved": str(status_counts.get("Approved", 0)),
        "High+ Residual": str(sum(row["Residual Risk"] in {"High", "Critical"} for row in rows)),
        "Evidence Refs": str(sum(int(row["Evidence References"]) for row in rows)),
    }
    cells = "".join(
        f"<div><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>"
        for label, value in summary.items()
    )
    st.markdown(f'<div class="ri-neutral-summary ri-review-summary">{cells}</div>', unsafe_allow_html=True)


def review_validation_rows(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None = None,
) -> list[dict[str, Any]]:
    """Rows for the analyst review queue."""
    rows: list[dict[str, Any]] = []
    for record in run.records:
        validation = required_validation_level(record, workspace)
        review = record.review_challenges[0] if record.review_challenges else None
        decision = _review_decision_for_risk(record.risk_id)
        rows.append(
            {
                "Risk ID": record.risk_id,
                "Business Unit": _business_unit_for_record(record, workspace) or run.input_context.business_unit,
                "Process": record.process_name,
                "Risk Subcategory": record.taxonomy_node.level_2_category,
                "Residual Risk": record.residual_risk.residual_rating.value,
                "Validation Level": validation["validation_level"],
                "Required Reviewer": validation["required_reviewer"],
                "Review Status": (
                    decision.review_status.value
                    if decision
                    else review.review_status.value
                    if review
                    else "Pending Review"
                ),
                "Approval Status": (
                    decision.approval_status.value
                    if decision
                    else review.approval_status.value
                    if review
                    else "Draft"
                ),
                "Control Gaps": len(build_control_gaps(record)),
                "Evidence References": len(record.evidence_references),
            }
        )
    return rows


def selected_review_dossier(
    record: RiskInventoryRecord,
    workspace: RiskInventoryWorkspace | None = None,
) -> dict[str, Any]:
    """Build an analyst-facing dossier for the selected risk output."""
    validation = required_validation_level(record, workspace)
    kris = workspace.kris_for_taxonomy(record.taxonomy_node.id) if workspace else []
    process = _process_for_record(record, workspace)
    gaps = build_control_gaps(record)
    synthetic_controls = build_synthetic_control_recommendations(record, workspace)
    checklist = [
        {
            "Review Area": "Risk Statement",
            "Reviewer Prompt": "Confirm the event, causes, consequences, and business unit scope are accurate.",
            "Suggested Focus": record.risk_statement.risk_description,
        },
        {
            "Review Area": "Scoring",
            "Reviewer Prompt": "Challenge whether impact and frequency are supported by the supplied metrics and rationale.",
            "Suggested Focus": f"Impact {int(record.impact_assessment.overall_impact_score)}; frequency {int(record.likelihood_assessment.likelihood_score)}; residual {record.residual_risk.residual_rating.value}.",
        },
        {
            "Review Area": "Controls",
            "Reviewer Prompt": "Confirm mapped controls address root causes, evidence expectations, and residual exposure.",
            "Suggested Focus": f"{len(record.control_mappings)} controls; {len(gaps)} control gaps; {len(synthetic_controls)} suggested controls.",
        },
        {
            "Review Area": "Evidence and KRIs",
            "Reviewer Prompt": "Confirm evidence is current and KRIs are measurable with useful thresholds.",
            "Suggested Focus": f"{len(record.evidence_references)} evidence references; {len(kris)} linked KRIs.",
        },
        {
            "Review Area": "Approval Authority",
            "Reviewer Prompt": "Confirm the risk is routed to the required reviewer before approval.",
            "Suggested Focus": f"{validation['validation_level']} · {validation['required_reviewer']}",
        },
    ]
    scoring_rationale = [
        {
            "Scoring Component": "Impact",
            "Value": str(int(record.impact_assessment.overall_impact_score)),
            "Rationale": record.impact_assessment.overall_impact_rationale,
        },
        {
            "Scoring Component": "Frequency",
            "Value": str(int(record.likelihood_assessment.likelihood_score)),
            "Rationale": record.likelihood_assessment.rationale,
        },
        {
            "Scoring Component": "Inherent Risk",
            "Value": record.inherent_risk.inherent_rating.value,
            "Rationale": record.inherent_risk.rationale,
        },
        {
            "Scoring Component": "Residual Risk",
            "Value": record.residual_risk.residual_rating.value,
            "Rationale": record.residual_risk.rationale,
        },
    ]
    source_trace = [
        {
            "Trace Component": "Process Context",
            "Detail": process.process_name if process else record.process_name,
            "Reviewer Use": "Confirm process scope and owner match bank operating model.",
        },
        {
            "Trace Component": "Risk Taxonomy",
            "Detail": f"{record.taxonomy_node.level_1_category} / {record.taxonomy_node.level_2_category}",
            "Reviewer Use": "Confirm taxonomy category is appropriate for the process and event.",
        },
        {
            "Trace Component": "Controls",
            "Detail": f"{len(record.control_mappings)} mapped controls",
            "Reviewer Use": "Challenge whether controls fully address root causes and evidence expectations.",
        },
        {
            "Trace Component": "KRIs",
            "Detail": f"{len(kris)} suggested indicators",
            "Reviewer Use": "Confirm thresholds are measurable and aligned to escalation paths.",
        },
    ]
    if process and process.apqc_crosswalk:
        source_trace.append(
            {
                "Trace Component": "Optional APQC Crosswalk",
                "Detail": process.apqc_crosswalk.get("process_name", ""),
                "Reviewer Use": "Use only as process-normalization context, not scoring evidence.",
            }
        )
    return {
        "risk_id": record.risk_id,
        "business_unit": _business_unit_for_record(record, workspace),
        "process": record.process_name,
        "level_1_category": record.taxonomy_node.level_1_category,
        "level_2_category": record.taxonomy_node.level_2_category,
        "residual_risk": record.residual_risk.residual_rating.value,
        "agent_output": record.risk_statement.risk_description,
        "bank_context_alignment": (
            f"Generated against {record.process_name}, {record.taxonomy_node.level_2_category}, "
            f"{len(record.control_mappings)} controls, {len(record.evidence_references)} evidence references, "
            f"and configured impact/frequency/residual matrices."
        ),
        "scoring": {
            "Impact": int(record.impact_assessment.overall_impact_score),
            "Frequency": int(record.likelihood_assessment.likelihood_score),
            "Inherent": record.inherent_risk.inherent_rating.value,
            "Residual": record.residual_risk.residual_rating.value,
        },
        "validation": validation,
        "checklist": checklist,
        "scoring_rationale": scoring_rationale,
        "controls": [mapping.model_dump() for mapping in record.control_mappings],
        "gaps": [gap.model_dump() for gap in gaps],
        "synthetic_controls": [recommendation.model_dump() for recommendation in synthetic_controls],
        "kris": [kri.model_dump() for kri in kris],
        "evidence": [_evidence_detail_dict(item) for item in record.evidence_references],
        "source_trace": source_trace,
    }


def _render_review_dossier(dossier: dict[str, Any]) -> None:
    validation = dossier["validation"]
    st.markdown(
        '<div class="ri-dossier ri-dossier-strong">'
        '<span>Selected Risk Dossier</span>'
        f'<h3>{html.escape(str(dossier["risk_id"]))} · {html.escape(str(dossier["level_2_category"]))}</h3>'
        f'<p>{html.escape(str(dossier["agent_output"]))}</p>'
        '<div class="ri-dossier-meta">'
        f'<div><span>Residual</span><b>{html.escape(str(dossier["residual_risk"]))}</b></div>'
        f'<div><span>Validation</span><b>{html.escape(str(validation["validation_level"]))}</b></div>'
        f'<div><span>Reviewer</span><b>{html.escape(str(validation["required_reviewer"]))}</b></div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    detail_tabs = st.tabs(["Review Brief", "Scoring", "Controls & Gaps", "Evidence & KRIs", "Trace"])
    with detail_tabs[0]:
        _render_neutral_callout(str(dossier["bank_context_alignment"]))
        _render_table_or_neutral(
            [
                {
                    "Validation Level": validation["validation_level"],
                    "Required Reviewer": validation["required_reviewer"],
                    "Business Level": validation["business_level"],
                    "Validation Basis": validation["validation_basis"],
                    "Escalation Path": validation["escalation_path"],
                }
            ],
            "No validation basis is configured for this record.",
        )
        st.markdown("**Reviewer checklist**")
        _render_table_or_neutral(dossier["checklist"], "No checklist prompts are available.")
    with detail_tabs[1]:
        _render_table_or_neutral([dossier["scoring"]], "No configured scoring values are available.")
        _render_table_or_neutral(dossier["scoring_rationale"], "No scoring rationale is available.")
    with detail_tabs[2]:
        st.markdown("**Mapped controls**")
        _render_table_or_neutral(dossier["controls"], "No controls are mapped to this risk.")
        st.markdown("**Coverage gaps**")
        _render_table_or_neutral(dossier["gaps"], "No material control gaps are currently identified.")
        st.markdown("**Suggested controls**")
        _render_table_or_neutral(dossier["synthetic_controls"], "No synthetic control suggestions are required.")
    with detail_tabs[3]:
        st.markdown("**Evidence references**")
        _render_table_or_neutral(dossier["evidence"], "No evidence references are attached to this risk.")
        st.markdown("**Linked KRIs**")
        _render_table_or_neutral(dossier["kris"], "No KRIs are linked to this risk category.")
    with detail_tabs[4]:
        _render_table_or_neutral(dossier["source_trace"], "No source trace is available.")


def _render_executive(run: RiskInventoryRun, workspace: RiskInventoryWorkspace | None = None) -> None:
    _render_summary_metrics(run)
    st.markdown('<div class="ri-section-title">Executive Summary</div>', unsafe_allow_html=True)
    st.write(run.executive_summary.headline)
    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("**Key Messages**")
        for message in run.executive_summary.key_messages:
            st.markdown(f"- {message}")
    with e2:
        st.markdown("**Top Residual Risks**")
        for risk in run.executive_summary.top_residual_risks or ["No Medium+ residual risks identified."]:
            st.markdown(f"- {risk}")
    with e3:
        st.markdown("**Recommended Actions**")
        for action in run.executive_summary.recommended_actions:
            st.markdown(f"- {action}")
    st.markdown('<div class="ri-section-title">Executive Risk Table</div>', unsafe_allow_html=True)
    _render_table(_risk_rows(run))


# ---------------------------------------------------------------------------
# User Knowledge Base tab
# ---------------------------------------------------------------------------


def _render_user_knowledge_base_intro() -> None:
    input_items = [
        ("Operating context", "Business units, process owners, products, systems, and material obligations."),
        ("Process evidence", "Policy, procedure, PDF, Markdown, or TXT files used to extract control and risk cues."),
        ("Control baseline", "Existing controls with owners, frequency, expected evidence, and test results."),
        ("Risk framework", "Risk taxonomy, control taxonomy, KRI library, appetite, and scoring rules."),
    ]
    output_items = [
        ("Risk inventory", "Risk records with executive-quality statements, taxonomy placement, root causes, and impact drivers."),
        ("Scoring record", "Impact, frequency, inherent risk, control score, residual rating, and rationale."),
        ("Control coverage", "Risk-to-control mapping with coverage strength, evidence needs, and open gaps."),
        ("Reviewer package", "KRI monitoring, synthetic control statements, validation prompts, and Excel-ready export."),
    ]
    benefit_items = [
        ("Faster review", "Starts from evidence already on file instead of blank risk forms."),
        ("Cleaner challenge", "Keeps rationale, evidence, KRIs, and reviewer questions tied to each risk."),
        ("Executive-ready output", "Produces workbench views and exports that support management review."),
    ]
    flow_steps = [
        ("01", "Load Knowledge", "Review source tables and add new evidence."),
        ("02", "Extract Context", "Confirm process facts before scoring."),
        ("03", "Run Workflow", "Classify, score, map controls, and identify gaps."),
        ("04", "Use Outputs", "Review workbenches and export the risk inventory."),
    ]
    input_html = "".join(_knowledge_base_io_item_html(title, description) for title, description in input_items)
    output_html = "".join(_knowledge_base_io_item_html(title, description) for title, description in output_items)
    benefit_html = "".join(
        (
            '<div class="ri-kb-benefit">'
            f"<b>{html.escape(title)}</b>"
            f"<p>{html.escape(description)}</p>"
            "</div>"
        )
        for title, description in benefit_items
    )
    flow_html = "".join(
        (
            '<div class="ri-kb-flow-step">'
            f"<span>{html.escape(number)}</span>"
            f"<b>{html.escape(title)}</b>"
            f"<p>{html.escape(description)}</p>"
            "</div>"
        )
        for number, title, description in flow_steps
    )
    st.markdown(
        f"""
        <div class="ri-kb-page-heading">
            <span>Knowledge Base</span>
            <div class="ri-kb-page-title">Start with source evidence. Finish with a reviewer-ready risk inventory.</div>
            <p>
                Review the institution data already on file, add process evidence, and run the workflow to produce
                risk records, control mapping, KRIs, gap analysis, and exportable reviewer materials.
            </p>
        </div>
        <div class="ri-kb-io-grid">
            <div class="ri-kb-io-card ri-kb-input-card">
                <div class="ri-kb-card-head">
                    <span>Input data</span>
                    <b>What the workflow consumes</b>
                </div>
                <div class="ri-kb-item-list">{input_html}</div>
            </div>
            <div class="ri-kb-io-card ri-kb-output-card">
                <div class="ri-kb-card-head">
                    <span>Deliverables</span>
                    <b>What the workflow produces</b>
                </div>
                <div class="ri-kb-item-list">{output_html}</div>
            </div>
        </div>
        <div class="ri-kb-benefit-band">
            <span>Why it helps</span>
            <div>{benefit_html}</div>
        </div>
        <div class="ri-kb-flow">{flow_html}</div>
        """,
        unsafe_allow_html=True,
    )


def _knowledge_base_io_item_html(title: str, description: str) -> str:
    return (
        '<div class="ri-kb-io-item">'
        f"<b>{html.escape(title)}</b>"
        f"<p>{html.escape(description)}</p>"
        "</div>"
    )


def _render_input_and_maybe_run() -> RiskInventoryRun | None:
    _render_user_knowledge_base_intro()

    st.markdown(
        '<div class="ri-section-title">Knowledge Base On File</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Review the source tables that can inform the run. Empty tables are placeholders for your institution's "
        "business units, processes, controls, taxonomies, and KRIs."
    )
    _render_user_existing_knowledge_tables()

    st.markdown(
        '<div class="ri-section-title">Add Process Evidence</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Upload a PDF, TXT, or Markdown procedure. The builder extracts process context, obligations, risk cues, "
        "control cues, systems, and stakeholders before the run."
    )

    analysis = _document_upload()
    structured_context = _structured_context_upload()
    controls = _control_upload()
    defaults = _context_defaults(analysis, structured_context)

    st.markdown('<div class="ri-section-title">Review Extracted Context</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.1, 1, 1])
    with c1:
        process_name = st.text_input("Process Name", value=str(defaults["process_name"]), key="ri_process_name")
        process_id = st.text_input("Process ID", value=str(defaults["process_id"]), key="ri_process_id")
    with c2:
        product = st.text_input("Product / Service", value=str(defaults["product"]), key="ri_product")
        business_unit = st.text_input("Business Unit", value=str(defaults["business_unit"]), key="ri_bu")
    with c3:
        max_risks = st.slider("Risk categories to evaluate", min_value=3, max_value=12, value=8, step=1)

    systems_default = (
        "\n".join(defaults["systems"]) if isinstance(defaults["systems"], list) else str(defaults["systems"])
    )
    stakeholders_default = (
        "\n".join(defaults["stakeholders"])
        if isinstance(defaults["stakeholders"], list)
        else str(defaults["stakeholders"])
    )
    s1, s2 = st.columns(2)
    with s1:
        systems = st.text_area("Systems / Applications", value=systems_default, height=110, key="ri_systems")
    with s2:
        stakeholders = st.text_area(
            "Stakeholders / Reviewers", value=stakeholders_default, height=110, key="ri_stakeholders"
        )

    description = st.text_area(
        "Process Narrative Used For Analysis",
        value=str(defaults["description"]),
        height=180,
        key="ri_description",
    )

    if analysis:
        _render_document_analysis(analysis)
    _render_control_preview(controls)

    st.markdown('<div class="ri-section-title">Run Risk Inventory Workflow</div>', unsafe_allow_html=True)
    run_cols = st.columns([2, 1])
    with run_cols[0]:
        st.write(
            "The graph applies two-tier taxonomy matching, drafts risk records, maps controls, scores inherent and residual risk, and prepares the downstream workbenches."
        )
    with run_cols[1]:
        run_clicked = st.button("Run Risk Inventory Workflow", type="primary", width="stretch", key="ri_run")

    if run_clicked:
        process_context = {
            "process_id": process_id,
            "process_name": process_name,
            "product": product,
            "business_unit": business_unit,
            "description": description,
            "systems": [line.strip() for line in systems.splitlines() if line.strip()],
            "stakeholders": [line.strip() for line in stakeholders.splitlines() if line.strip()],
            "source_documents": [analysis.filename] if analysis else [],
        }
        with st.status("Building risk inventory...", expanded=True) as status:
            status.write("Loaded process context and control inventory.")
            graph = build_risk_inventory_graph().compile()
            result = graph.invoke(
                {
                    "run_id": f"RI-USER-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    "tenant_id": "user-workspace",
                    "process_context": process_context,
                    "control_inventory": controls,
                    "max_risks": max_risks,
                },
                config={"recursion_limit": 200},
            )
            status.write("Calculated inherent risk, control environment, and residual risk.")
            st.session_state["risk_inventory_user_run"] = result["final_report"]
            status.update(label="Risk inventory workflow complete.", state="complete")
        st.rerun()

    data = st.session_state.get("risk_inventory_user_run")
    return RiskInventoryRun.model_validate(data) if data else None


def _render_user_existing_knowledge_tables() -> None:
    sub_tabs = st.tabs(
        [
            "Business Units",
            "Processes",
            "Risk Taxonomy",
            "Control Taxonomy",
            "Controls Register",
            "KRI Library",
        ]
    )
    placeholder_columns = {
        "Business Units": [
            "Business Unit ID",
            "Business Unit",
            "Executive Owner",
            "2LOD Risk Partner",
            "Products / Services",
            "Core Systems",
            "Material Obligations",
        ],
        "Processes": [
            "Process ID",
            "Process",
            "Business Unit",
            "Process Owner",
            "Trigger",
            "SLA",
            "Upstream Dependencies",
            "Downstream Dependencies",
            "Systems",
            "Data Objects",
        ],
        "Risk Taxonomy": [
            "Level 1 Code",
            "Enterprise Risk Category",
            "Level 2 Code",
            "Risk Subcategory",
            "Definition",
        ],
        "Control Taxonomy": ["Code", "Family", "Control Family", "Description"],
        "Controls Register": [
            "Control ID",
            "Control Objective",
            "Control Activity",
            "Control Type",
            "Frequency",
            "Owner",
            "Expected Evidence",
            "Last Test Date",
            "Design Effectiveness",
            "Operating Effectiveness",
        ],
        "KRI Library": [
            "KRI ID",
            "KRI",
            "Definition",
            "Source",
            "Frequency",
            "Owner",
            "Green",
            "Amber",
            "Red",
            "Escalation Path",
        ],
    }
    table_keys = {
        "Business Units": "ri_user_bus",
        "Processes": "ri_user_procs",
        "Risk Taxonomy": "ri_user_risk_taxonomy",
        "Control Taxonomy": "ri_user_control_taxonomy",
        "Controls Register": "ri_user_controls",
        "KRI Library": "ri_user_kris",
    }
    for tab, label in zip(sub_tabs, list(placeholder_columns.keys())):
        with tab:
            data = st.session_state.get(table_keys[label], [])
            if data:
                _render_table(list(data))
            else:
                _render_table([{col: "" for col in placeholder_columns[label]}])
                st.caption(
                    f"No {label.lower()} on file. Use the uploads below to populate this table, "
                    "or load Demo Mode to see the populated payment exception example."
                )


def _render_source_pack_cards(profile: dict[str, Any]) -> None:
    packs = [
        ("Business units", "Owners, 1LOD/2LOD roles, products, systems, material obligations."),
        ("Processes", "Triggers, SLAs, dependencies, systems, data objects, owners."),
        ("Policy/process documents", "Narrative evidence used to extract context, obligations, controls, and risk cues."),
        ("Controls", "Objectives, activities, evidence, frequency, owner, design and operating results."),
        ("KRIs", "Definitions, formulas, thresholds, sources, escalation owners, historical examples."),
        ("Obligations", "Regulatory, policy, and supervisory expectations mapped to risks and controls."),
        ("Issues/events", "Audit findings, incidents, losses, complaints, exceptions, SLA breaches."),
        ("Evidence", "Artifacts that support mappings, ratings, operating effectiveness, and review decisions."),
        ("Taxonomies", "Two-tier risk taxonomy, control taxonomy, root causes, and appetite/scoring rules."),
        ("Scoring/appetite", "Impact, frequency, inherent, residual, and management response thresholds."),
    ]
    cards = []
    for name, description in packs:
        cards.append(
            (
                '<div class="ri-source-card">'
                f"<span>{html.escape(name)}</span>"
                f"<p>{html.escape(description)}</p>"
                "</div>"
            )
        )
    st.markdown(
        (
            f'<div class="ri-source-grid">{"".join(cards)}</div>'
            '<div class="ri-intake-note">'
            f'Reference process: {html.escape(profile["sample_business_unit"])} · '
            f'{html.escape(profile["sample_process"])}. '
            "In production, each organization replaces any pack with its own YAML, Excel, PDF, or Markdown source."
            "</div>"
        ),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Upload helpers (preserved from prior implementation)
# ---------------------------------------------------------------------------


def _document_upload() -> DocumentAnalysis | None:
    upload_col, sample_col = st.columns([2, 1])
    with upload_col:
        uploaded = st.file_uploader(
            "Upload process document",
            type=["pdf", "txt", "md", "markdown"],
            key="ri_process_document_upload",
            help="PDF, TXT, or Markdown files are parsed locally and used to prefill process context.",
        )
    with sample_col:
        st.write("")
        st.write("")
        use_sample = st.button("Load payment exception document", width="stretch", key="ri_load_sample_doc")

    if use_sample:
        sample_path = default_demo_fixture_path().with_name("payment_exception_policy.md")
        analysis = analyze_process_document(sample_path.name, sample_path.read_bytes())
        st.session_state["risk_inventory_document_analysis"] = analysis.model_dump()
        st.session_state["ri_loaded_doc_name"] = analysis.filename
        _apply_analysis_to_widgets(analysis)

    if uploaded is not None:
        try:
            analysis = analyze_process_document(uploaded.name, uploaded.getvalue())
        except Exception as exc:  # noqa: BLE001 - user-facing upload parse error
            st.error(f"Could not parse document: {exc}")
            return None
        st.session_state["risk_inventory_document_analysis"] = analysis.model_dump()
        if st.session_state.get("ri_loaded_doc_name") != analysis.filename:
            st.session_state["ri_loaded_doc_name"] = analysis.filename
            _apply_analysis_to_widgets(analysis)

    raw = st.session_state.get("risk_inventory_document_analysis")
    return DocumentAnalysis.model_validate(raw) if raw else None


def _apply_analysis_to_widgets(analysis: DocumentAnalysis) -> None:
    context = analysis.process_context()
    st.session_state["ri_process_name"] = context["process_name"]
    st.session_state["ri_process_id"] = context["process_id"]
    st.session_state["ri_product"] = context["product"]
    st.session_state["ri_bu"] = context["business_unit"]
    st.session_state["ri_systems"] = "\n".join(context["systems"])
    st.session_state["ri_stakeholders"] = "\n".join(context["stakeholders"])
    st.session_state["ri_description"] = context["description"]


def _structured_context_upload() -> dict[str, Any]:
    with st.expander("Optional structured context upload (JSON/YAML)", expanded=False):
        uploaded = st.file_uploader(
            "Upload structured process context",
            type=["json", "yaml", "yml"],
            key="ri_process_context_upload",
        )
    if uploaded is None:
        return {}
    suffix = Path(uploaded.name).suffix.lower()
    raw_text = uploaded.getvalue().decode("utf-8")
    payload = json.loads(raw_text) if suffix == ".json" else yaml.safe_load(raw_text)
    return payload if isinstance(payload, dict) else {}


def _context_defaults(analysis: DocumentAnalysis | None, structured_context: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "process_id": "PROC-PAY-EXCEPTION",
        "process_name": "Payment Exception Handling",
        "product": "High-value payment processing",
        "business_unit": "Payment Operations",
        "description": (
            "Daily high-value payment exception workflow for investigation, approval, resolution, "
            "reconciliation, escalation, and incident reporting."
        ),
        "systems": ["Payment Exception Workflow", "Wire Transfer Platform"],
        "stakeholders": ["Payment Operations Manager", "Compliance Officer"],
    }
    if analysis:
        defaults.update(analysis.process_context())
    defaults.update({key: value for key, value in structured_context.items() if value})
    return defaults


def _control_upload() -> list[dict[str, Any]]:
    st.markdown('<div class="ri-section-title">Control Data</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    with c1:
        uploaded = st.file_uploader(
            "Upload existing controls",
            type=["xlsx", "xls", "json", "yaml", "yml"],
            key="ri_control_upload",
            help="Control register uploads can be Excel, JSON, or YAML.",
        )
    with c2:
        use_starter_controls = st.checkbox(
            "Use starter payment controls",
            value=uploaded is None,
            help="Use payment operations reference controls when no control register is available.",
        )

    if uploaded is None:
        return _starter_controls() if use_starter_controls else []

    suffix = Path(uploaded.name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)
        try:
            return [
                {
                    "control_id": record.control_id,
                    "control_name": record.leaf_name or record.control_id,
                    "control_type": record.selected_level_2 or record.control_type,
                    "description": record.full_description,
                    "design_rating": "Satisfactory",
                    "operating_rating": "Satisfactory",
                }
                for record in ingest_excel(tmp_path)
            ]
        finally:
            tmp_path.unlink(missing_ok=True)

    raw_text = uploaded.getvalue().decode("utf-8")
    payload = json.loads(raw_text) if suffix == ".json" else yaml.safe_load(raw_text)
    if isinstance(payload, dict):
        payload = payload.get("controls", [])
    return list(payload or [])


def _starter_controls() -> list[dict[str, Any]]:
    payload = yaml.safe_load(default_demo_fixture_path().read_text(encoding="utf-8")) or {}
    return list(payload.get("controls", []))


def _render_empty_panel(message: str) -> None:
    st.markdown(f'<div class="ri-empty-small">{html.escape(message)}</div>', unsafe_allow_html=True)


def _render_neutral_callout(message: str) -> None:
    st.markdown(f'<div class="ri-neutral-callout">{html.escape(message)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _render_document_analysis(analysis: DocumentAnalysis) -> None:
    st.markdown('<div class="ri-section-title">Document Analysis</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Words", analysis.document_stats.get("words", 0))
    m2.metric("Risk Cues", len(analysis.detected_risk_categories))
    m3.metric("Control Cues", len(analysis.detected_controls))
    m4.metric("Obligations", len(analysis.obligations))
    _render_chip_group("Detected risk categories", analysis.detected_risk_categories)
    _render_chip_group("Detected control cues", analysis.detected_controls)
    _render_chip_group("Exposure cues", analysis.exposure_cues)
    with st.expander("Detected obligations and extracted text", expanded=False):
        for obligation in analysis.obligations:
            st.markdown(f"- {obligation}")
        st.text_area("Extracted text preview", value=analysis.text[:5000], height=220, disabled=True)


def _render_control_preview(controls: list[dict[str, Any]]) -> None:
    st.caption(f"{len(controls)} controls will be available for mapping.")
    if controls:
        _render_table(
            [
                {
                    "Control ID": control.get("control_id", ""),
                    "Control Name": control.get("control_name", control.get("name", "")),
                    "Control Type": control.get("control_type", ""),
                    "Design Effectiveness": control.get("design_rating", "Satisfactory"),
                    "Operating Effectiveness": control.get("operating_rating", "Satisfactory"),
                }
                for control in controls
            ],
        )


def _render_summary_metrics(run: RiskInventoryRun) -> None:
    high_plus = sum(record.residual_risk.residual_rating.value in {"High", "Critical"} for record in run.records)
    controls = sum(len(record.control_mappings) for record in run.records)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(_metric_card("Risks", str(len(run.records)), "blue"), unsafe_allow_html=True)
    m2.markdown(_metric_card("Materialized", str(len(run.materialized_records)), "green"), unsafe_allow_html=True)
    m3.markdown(_metric_card("Controls Linked", str(controls), "teal"), unsafe_allow_html=True)
    m4.markdown(_metric_card("High+ Residual", str(high_plus), "red" if high_plus else "green"), unsafe_allow_html=True)
    m5.markdown(_metric_card("Validation Flags", str(len(run.validation_findings)), "yellow"), unsafe_allow_html=True)


def _risk_selector(run: RiskInventoryRun, key: str) -> RiskInventoryRecord:
    options = [
        f"{record.risk_id}  ·  {record.taxonomy_node.level_2_category}  ({record.taxonomy_node.level_1_category})"
        for record in run.records
    ]
    selected = st.selectbox("Select Risk Record", options, key=key)
    index = options.index(selected)
    return run.records[index]


def _render_risk_header(record: RiskInventoryRecord) -> None:
    st.markdown(
        f"""
        <div class="ri-risk-card">
            <div class="ri-risk-header">
                <div>
                    <div class="ri-risk-kicker">Risk Record</div>
                    <div class="ri-risk-title">{html.escape(record.risk_id)}</div>
                </div>
                <div class="ri-risk-category">{html.escape(record.taxonomy_node.level_2_category)}</div>
            </div>
            <p class="ri-risk-statement-focus">{html.escape(_risk_statement_display(record))}</p>
            <div class="ri-risk-meta-line">
                {html.escape(record.taxonomy_node.level_1_category)} · {html.escape(record.process_name)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chip_group(label: str, values: list[str]) -> None:
    if not values:
        return
    st.markdown(f"**{label}**")
    chips = " ".join(f'<span class="ri-chip">{html.escape(value)}</span>' for value in values[:12])
    st.markdown(chips, unsafe_allow_html=True)


def _render_table(rows: list[dict[str, Any]]) -> None:
    """Render a readable, monitor-friendly table with wrapped text and tuned columns."""
    normalized_rows = [
        {_display_column_label(str(column)): _normalize_table_value(value) for column, value in row.items()}
        for row in rows
    ]
    if not normalized_rows:
        _render_neutral_callout("No table records available.")
        return

    row_height = _table_row_height(normalized_rows)
    st.dataframe(
        normalized_rows,
        hide_index=True,
        width="stretch",
        height=_table_height(normalized_rows, row_height),
        row_height=row_height,
        column_config=_table_column_config(normalized_rows),
    )


def _render_prominent_table(rows: list[dict[str, Any]]) -> None:
    """Render a larger table for first-screen workspace inventory scanning."""
    normalized_rows = [
        {_display_column_label(str(column)): _normalize_table_value(value) for column, value in row.items()}
        for row in rows
    ]
    if not normalized_rows:
        _render_neutral_callout("No table records available.")
        return
    row_height = _table_row_height(normalized_rows)
    st.dataframe(
        normalized_rows,
        hide_index=True,
        width="stretch",
        height=min(640, max(500, 76 + len(normalized_rows) * row_height)),
        row_height=row_height,
        column_config=_table_column_config(normalized_rows),
    )


def _render_table_or_neutral(rows: list[dict[str, Any]], empty_message: str) -> None:
    if rows:
        _render_table(rows)
    else:
        _render_neutral_callout(empty_message)


def _normalize_table_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return str(value)


def _display_column_label(column: str) -> str:
    """Normalize model/dict keys into demo-ready table headers."""
    cleaned = column.strip()
    if "_" not in cleaned and cleaned[:1].isupper():
        return cleaned
    words = [part for part in cleaned.replace("-", "_").split("_") if part]
    acronyms = {
        "id": "ID",
        "ids": "IDs",
        "bu": "BU",
        "kri": "KRI",
        "kris": "KRIs",
        "apqc": "APQC",
        "sla": "SLA",
        "ofac": "OFAC",
        "rto": "RTO",
        "rpo": "RPO",
        "1lod": "1LOD",
        "2lod": "2LOD",
    }
    return " ".join(acronyms.get(word.lower(), word.capitalize()) for word in words)


def _table_column_config(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first_row = rows[0]
    config: dict[str, Any] = {}
    for index, column in enumerate(first_row):
        values = [row.get(column, "") for row in rows]
        width = _table_column_width(column, values)
        if _is_numeric_column(values):
            config[column] = st.column_config.NumberColumn(column, width=width)
        else:
            config[column] = st.column_config.TextColumn(
                column,
                width=width,
                pinned=index == 0 and _is_identifier_column(column),
            )
    return config


def _table_column_width(column: str, values: list[Any]) -> int:
    name = column.lower()
    if "risk statement" in name or name.endswith(" statement"):
        return 520
    if any(term in name for term in ("description", "rationale", "summary", "message", "action", "definition")):
        return 420
    if any(term in name for term in ("risk profile", "regulatory relevance", "systems", "comments", "findings")):
        return 360
    if any(term in name for term in ("process", "control", "subcategory", "category", "stakeholder")):
        return 240
    if any(term in name for term in ("rating", "response", "status", "frequency", "cadence", "reviewed", "severity")):
        return 160
    if _is_identifier_column(column) or any(term in name for term in ("score", "count", "age", "green", "amber", "red")):
        return 130

    longest = max((len(str(value)) for value in values), default=0)
    if longest <= 10:
        return 120
    if longest <= 22:
        return 160
    if longest <= 42:
        return 220
    return 300


def _is_identifier_column(column: str) -> bool:
    name = column.lower()
    return " id" in f" {name}" or name.endswith("code") or name == "code"


def _is_numeric_column(values: list[Any]) -> bool:
    non_empty = [value for value in values if value not in ("", None)]
    return bool(non_empty) and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_empty
    )


def _table_row_height(rows: list[dict[str, Any]]) -> int:
    longest = max((len(str(value)) for row in rows for value in row.values()), default=0)
    if longest > 220:
        return 108
    if longest > 110:
        return 84
    if longest > 64:
        return 68
    return 48


def _table_height(rows: list[dict[str, Any]], row_height: int) -> int:
    header_height = 44
    body_height = max(1, len(rows)) * row_height
    return min(max(header_height + body_height, 132), 560)


def _render_fact_block(values: dict[str, str]) -> None:
    facts = "".join(
        f"<div><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>"
        for label, value in values.items()
    )
    st.markdown(f'<div class="ri-fact-grid">{facts}</div>', unsafe_allow_html=True)


def _workspace_control_mapping_rows(
    workspace: RiskInventoryWorkspace,
    selected_bu_id: str | None = None,
) -> list[dict[str, Any]]:
    """Flatten workspace runs into rows for the Control Mapping roll-up."""
    bu_lookup = {bu.bu_id: bu.bu_name for bu in workspace.business_units}
    procedures = workspace.procedures_for_bu(selected_bu_id) if selected_bu_id else workspace.procedures
    rows: list[dict[str, Any]] = []

    for proc in procedures:
        run = workspace.run_for_procedure(proc.procedure_id)
        if not run:
            continue
        for record in run.records:
            rows.append(
                {
                    "Business Unit ID": proc.bu_id,
                    "Business Unit": bu_lookup.get(proc.bu_id, proc.bu_id),
                    "Process ID": proc.procedure_id,
                    "Process": proc.procedure_name,
                    "Risk Record ID": record.risk_id,
                    "Enterprise Risk Category": record.taxonomy_node.level_1_category,
                    "Risk Subcategory": record.taxonomy_node.level_2_category,
                    "Residual Risk Rating": record.residual_risk.residual_rating.value,
                    "Mapped Controls": len(record.control_mappings),
                    "Coverage Status": _record_coverage_status(record),
                }
            )
    return rows


def _workspace_control_mapping_matrix_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a wide BU x L1 matrix for workspace risk spread."""
    business_units = sorted({str(row["Business Unit"]) for row in rows})
    categories = sorted({str(row["Enterprise Risk Category"]) for row in rows})
    matrix_rows: list[dict[str, Any]] = []

    for bu_name in business_units:
        bu_rows = [row for row in rows if row["Business Unit"] == bu_name]
        matrix_row: dict[str, Any] = {
            "Business Unit": bu_name,
            "Risk Records": len(bu_rows),
            "High+ Residual": _high_plus_count(bu_rows),
            "Mapped Controls": sum(int(row["Mapped Controls"]) for row in bu_rows),
        }
        for category in categories:
            category_rows = [row for row in bu_rows if row["Enterprise Risk Category"] == category]
            matrix_row[category] = _risk_spread_cell(category_rows)
        matrix_rows.append(matrix_row)

    return matrix_rows


def _workspace_control_mapping_category_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build long-form BU x L1 rows with L2 subcategory detail."""
    grouped_keys = sorted(
        {
            (str(row["Business Unit"]), str(row["Enterprise Risk Category"]))
            for row in rows
        }
    )
    category_rows: list[dict[str, Any]] = []

    for bu_name, category in grouped_keys:
        grouped = [
            row
            for row in rows
            if row["Business Unit"] == bu_name and row["Enterprise Risk Category"] == category
        ]
        l2_counts = Counter(str(row["Risk Subcategory"]) for row in grouped)
        category_rows.append(
            {
                "Business Unit": bu_name,
                "Enterprise Risk Category": category,
                "Risk Records": len(grouped),
                "High+ Residual": _high_plus_count(grouped),
                "Mapped Controls": sum(int(row["Mapped Controls"]) for row in grouped),
                "Risk Subcategories": ", ".join(
                    f"{subcategory} ({count})" for subcategory, count in l2_counts.most_common()
                ),
            }
        )

    return category_rows


def _workspace_control_mapping_coverage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage_counts = Counter(str(row["Coverage Status"]) for row in rows)
    return [
        {
            "Coverage Status": status,
            "Risk Records": count,
            "Mapped Controls": sum(
                int(row["Mapped Controls"]) for row in rows if row["Coverage Status"] == status
            ),
        }
        for status, count in coverage_counts.most_common()
    ]


def _run_control_mapping_rows(
    run: RiskInventoryRun,
    workspace: RiskInventoryWorkspace | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in run.records:
        score_row = control_score_row(record)
        for mapping in record.control_mappings:
            rows.append(
                {
                    "Risk Record ID": record.risk_id,
                    "Enterprise Risk Category": record.taxonomy_node.level_1_category,
                    "Risk Subcategory": record.taxonomy_node.level_2_category,
                    "Control Score": score_row["Control Score"],
                    "Control Strength": score_row["Control Strength"],
                    "Coverage Status": score_row["Coverage Status"],
                    "Control ID": mapping.control_id,
                    "Control": mapping.control_name,
                    "Control Type": mapping.control_type,
                    "Control Objective": mapping.control_description,
                    "Risk Coverage Rationale": mapping.mitigation_rationale,
                    "Mapped Root Causes": "; ".join(mapping.mapped_root_causes),
                    "Coverage Assessment": mapping.coverage_assessment.title(),
                    "Design Effectiveness": (
                        mapping.design_effectiveness.rating.value
                        if mapping.design_effectiveness
                        else "Not Rated"
                    ),
                    "Operating Effectiveness": (
                        mapping.operating_effectiveness.rating.value
                        if mapping.operating_effectiveness
                        else "Not Rated"
                    ),
                }
            )
    return rows


def _record_coverage_status(record: RiskInventoryRecord) -> str:
    if not record.control_mappings:
        return "Coverage Gap"
    material_gaps = [gap for gap in record.coverage_gaps if "root cause" not in gap.lower()]
    if material_gaps:
        return "Gaps Noted"
    coverage_values = {mapping.coverage_assessment.lower() for mapping in record.control_mappings}
    if coverage_values <= {"strong", "full"}:
        return "Strong Coverage"
    if "strong" in coverage_values or "full" in coverage_values:
        return "Mixed Coverage"
    return "Partial Coverage"


def _coverage_status_has_gap(status: str) -> bool:
    return status in {"Coverage Gap", "Gaps Noted", "Partial Coverage"}


def _risk_spread_cell(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "0 risks | 0 high+ | 0 controls"
    risk_count = len(rows)
    high_plus = _high_plus_count(rows)
    control_count = sum(int(row["Mapped Controls"]) for row in rows)
    risk_label = "risk" if risk_count == 1 else "risks"
    return f"{risk_count} {risk_label} | {high_plus} high+ | {control_count} controls"


def _high_plus_count(rows: list[dict[str, Any]]) -> int:
    return sum(row["Residual Risk Rating"] in {"High", "Critical"} for row in rows)


def _download_export(
    run: RiskInventoryRun,
    location: str,
    workspace: RiskInventoryWorkspace | None = None,
) -> None:
    export_run = _run_with_review_decisions(run)
    data = (
        risk_inventory_workspace_excel_bytes(workspace, _session_review_decisions())
        if workspace
        else risk_inventory_excel_bytes(export_run)
    )
    filename = (
        f"{workspace.workspace_id}_risk_inventory_demo_artifact.xlsx"
        if workspace
        else f"{run.run_id}_risk_inventory.xlsx"
    )
    st.download_button(
        "Download Executive Excel Workbook",
        data=data,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"ri_xlsx_{location}_{run.run_id}",
        width="stretch",
    )


def _run_with_review_decisions(run: RiskInventoryRun) -> RiskInventoryRun:
    return apply_review_decisions(run, _session_review_decisions())


def _session_review_decisions() -> list[ReviewDecision]:
    raw = st.session_state.get("ri_review_decisions", {})
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = list(raw.values())
    else:
        values = []
    decisions: list[ReviewDecision] = []
    for item in values:
        try:
            decisions.append(item if isinstance(item, ReviewDecision) else ReviewDecision.model_validate(item))
        except Exception:
            continue
    return decisions


def _review_decision_for_risk(risk_id: str) -> ReviewDecision | None:
    for decision in _session_review_decisions():
        if decision.risk_id == risk_id:
            return decision
    return None


def _store_review_decision(decision: ReviewDecision) -> None:
    raw = st.session_state.get("ri_review_decisions", {})
    state = raw if isinstance(raw, dict) else {}
    state[decision.risk_id] = decision.model_dump()
    st.session_state["ri_review_decisions"] = state


def _risk_rows(run: RiskInventoryRun) -> list[dict[str, Any]]:
    return [
        {
            "Risk Record ID": record.risk_id,
            "Process": record.process_name,
            "Enterprise Risk Category": record.taxonomy_node.level_1_category,
            "Risk Subcategory": record.taxonomy_node.level_2_category,
            "Inherent Risk Rating": record.inherent_risk.inherent_rating.value,
            "Control Environment Rating": record.control_environment.control_environment_rating.value,
            "Residual Risk Rating": record.residual_risk.residual_rating.value,
            "Recommended Management Response": record.residual_risk.management_response.response_type.value.title(),
            "Mapped Controls": len(record.control_mappings),
        }
        for record in run.records
    ]


def _metric_card(label: str, value: str, tone: str) -> str:
    return (
        f'<div class="ri-metric ri-tone-{tone}"><span>{html.escape(label)}</span>'
        f"<b>{html.escape(value)}</b></div>"
    )


def _rating_html(label: str, title: str = "Rating") -> str:
    tone = _rating_class(label)
    return (
        f'<div class="ri-rating-tile ri-{tone}">'
        f"<span>{html.escape(title)}</span><b>{html.escape(label)}</b></div>"
    )


def _badge(label: str, value: str, tone: str) -> str:
    return f'<span class="ri-badge ri-{tone}">{html.escape(label)}: {html.escape(value)}</span>'


def _coverage_class(value: str) -> str:
    lowered = value.lower()
    if "strong" in lowered or "full" in lowered:
        return "low"
    if "partial" in lowered:
        return "medium"
    if "gap" in lowered or "none" in lowered:
        return "high"
    return "neutral"


def _rating_class(value: str) -> str:
    lowered = value.lower()
    if "critical" in lowered or "inadequate" in lowered or "escalate" in lowered:
        return "critical"
    if "high" in lowered or "improvement" in lowered or "mitigate" in lowered:
        return "high"
    if "medium" in lowered or "satisfactory" in lowered or "monitor" in lowered:
        return "medium"
    if "low" in lowered or "strong" in lowered or "accept" in lowered:
        return "low"
    return "neutral"


def _inject_risk_inventory_css() -> None:
    st.markdown(
        """
        <style>
        .ri-kb-page-heading {
            border-left: 4px solid #0f62fe; padding: 0.15rem 0 0.25rem 1rem;
            margin: 0.35rem 0 1rem 0; max-width: 1180px;
        }
        .ri-kb-page-heading span, .ri-kb-card-head span, .ri-kb-benefit-band > span, .ri-kb-flow-step span {
            display: block; color: #0f62fe; font-size: 0.78rem; font-weight: 800;
            text-transform: uppercase; margin-bottom: 0.35rem;
        }
        .ri-kb-page-title {
            color: #161616; font-size: 1.8rem; line-height: 1.18; margin: 0 0 0.45rem 0;
            max-width: 920px; font-weight: 800;
        }
        .ri-kb-page-heading p {
            color: #525252; line-height: 1.48; margin: 0; max-width: 980px; font-size: 1rem;
        }
        .ri-kb-io-grid {
            display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem;
            margin: 0 0 0.75rem 0;
        }
        .ri-kb-io-card {
            background: #ffffff; border: 1px solid #c6c6c6; padding: 0.95rem;
            min-height: 260px; border-top: 4px solid #0f62fe;
        }
        .ri-kb-output-card { border-top-color: #24a148; }
        .ri-kb-output-card .ri-kb-card-head span { color: #198038; }
        .ri-kb-card-head {
            border-bottom: 1px solid #e0e0e0; padding-bottom: 0.55rem; margin-bottom: 0.65rem;
        }
        .ri-kb-card-head b {
            display: block; color: #161616; font-size: 1.12rem; line-height: 1.25;
        }
        .ri-kb-item-list { display: grid; gap: 0.55rem; }
        .ri-kb-io-item {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.62rem 0.7rem;
            border-left: 3px solid #0f62fe;
        }
        .ri-kb-output-card .ri-kb-io-item { border-left-color: #24a148; }
        .ri-kb-io-item b {
            display: block; color: #161616; font-size: 0.94rem; margin-bottom: 0.2rem;
        }
        .ri-kb-io-item p {
            color: #393939; line-height: 1.38; margin: 0 !important; font-size: 0.9rem;
        }
        .ri-kb-benefit-band {
            background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.85rem;
            margin: 0 0 0.75rem 0;
        }
        .ri-kb-benefit-band > span { color: #525252; margin-bottom: 0.5rem; }
        .ri-kb-benefit-band > div {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.55rem;
        }
        .ri-kb-benefit {
            background: #ffffff; border: 1px solid #e0e0e0; padding: 0.65rem;
        }
        .ri-kb-benefit b {
            display: block; color: #161616; font-size: 0.95rem; margin-bottom: 0.2rem;
        }
        .ri-kb-benefit p {
            color: #525252; margin: 0 !important; line-height: 1.36; font-size: 0.88rem;
        }
        .ri-kb-flow {
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.5rem;
            margin: 0 0 1rem 0;
        }
        .ri-kb-flow-step {
            background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.75rem; min-height: 126px;
        }
        .ri-kb-flow-step span {
            color: #0f62fe; margin-bottom: 0.28rem;
        }
        .ri-kb-flow-step b {
            display: block; color: #161616; font-size: 0.98rem; margin-bottom: 0.25rem;
        }
        .ri-kb-flow-step p {
            color: #525252; line-height: 1.36; margin: 0; font-size: 0.86rem;
        }
        .ri-hero { background: #f4f4f4; border-left: 4px solid #0f62fe; padding: 1rem 1.25rem; margin-bottom: 1rem; }
        .ri-hero h1 { font-size: 1.85rem; margin: 0.15rem 0 0.35rem 0; line-height: 1.2; }
        .ri-hero p { color: #525252; margin: 0; max-width: 920px; }
        .ri-eyebrow, .ri-section-title { color: #0f62fe; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; margin: 1rem 0 0.35rem 0; }
        .ri-toggle-panel { background: #ffffff; border: 1px solid #c6c6c6; padding: 0.85rem; min-height: 112px; }
        .ri-scope-lens {
            display: grid; grid-template-columns: 1.5fr 1.5fr 0.75fr 0.75fr; gap: 0.5rem;
            background: #ffffff; border: 1px solid #c6c6c6; border-left: 4px solid #0f62fe;
            padding: 0.7rem 0.85rem; margin: 0.2rem 0 0.8rem 0;
        }
        .ri-scope-lens div { min-width: 0; }
        .ri-scope-lens span {
            display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-scope-lens b {
            display: block; color: #161616; font-size: 0.94rem; margin-top: 0.15rem;
            overflow-wrap: anywhere;
        }
        .ri-empty, .ri-empty-small { background: #f4f4f4; border: 1px solid #c6c6c6; padding: 1.1rem; margin-top: 0.75rem; }
        .ri-neutral-callout, .ri-review-asset {
            background: #f4f4f4; border: 1px solid #c6c6c6; color: #161616;
            padding: 0.85rem 1rem; margin: 0.7rem 0; line-height: 1.45;
        }
        .ri-review-asset b { display: block; margin-bottom: 0.25rem; }
        .ri-review-asset p { color: #393939; margin: 0; }
        .ri-neutral-summary {
            display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0.5rem;
            margin: 0.3rem 0 0.75rem 0;
        }
        .ri-neutral-summary div {
            background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.65rem;
        }
        .ri-neutral-summary span {
            display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-neutral-summary b { display: block; color: #161616; font-size: 1.18rem; margin-top: 0.15rem; }
        .ri-residual-calc-strip {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem;
            margin: 0.3rem 0 0.75rem 0;
        }
        .ri-residual-calc-strip div {
            background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.75rem;
        }
        .ri-residual-calc-strip span {
            display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-residual-calc-strip b {
            display: block; color: #161616; font-size: 1.35rem; margin-top: 0.15rem;
        }
        .ri-flow { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.7rem 0 1rem 0; }
        .ri-flow span { background: #edf5ff; border: 1px solid #78a9ff; color: #001d6c; padding: 0.45rem 0.65rem; font-size: 0.82rem; }
        .ri-metric { border: 1px solid #c6c6c6; background: #ffffff; padding: 0.85rem; min-height: 92px; border-top: 4px solid #0f62fe; }
        .ri-metric span, .ri-rating-tile span, .ri-fact-grid span { display: block; color: #525252; font-size: 0.75rem; text-transform: uppercase; font-weight: 600; }
        .ri-metric b { display: block; font-size: 1.8rem; margin-top: 0.2rem; }
        .ri-tone-green { border-top-color: #24a148; }
        .ri-tone-teal { border-top-color: #009d9a; }
        .ri-tone-red { border-top-color: #da1e28; }
        .ri-tone-yellow { border-top-color: #f1c21b; }
        .ri-tone-neutral { border-top-color: #8d8d8d; }
        .ri-risk-card, .ri-gap-card, .ri-detail-panel, .ri-compact-risk, .ri-bu-card, .ri-kri-card {
            background: #ffffff; border: 1px solid #c6c6c6; padding: 0.9rem; margin: 0.55rem 0;
        }
        .ri-risk-card { border-left: 4px solid #8d8d8d; }
        .ri-risk-header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; margin-bottom: 0.35rem; }
        .ri-risk-kicker { color: #525252; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; }
        .ri-risk-title { font-weight: 700; margin-bottom: 0.25rem; font-size: 1.05rem; }
        .ri-risk-category { color: #161616; font-weight: 700; text-align: right; max-width: 48%; }
        .ri-risk-tax { margin-bottom: 0.4rem; }
        .ri-risk-statement-focus { color: #161616; font-size: 1.02rem; line-height: 1.48; margin: 0.45rem 0 0.55rem 0; }
        .ri-risk-meta-line { color: #525252; font-size: 0.84rem; font-weight: 600; }
        .ri-inherent-panel {
            background: #ffffff; border: 1px solid #c6c6c6; border-left: 4px solid #8d8d8d;
            padding: 0.9rem; margin: 0.7rem 0 0.9rem 0;
        }
        .ri-inherent-flow {
            background: #ffffff; border: 1px solid #c6c6c6; border-left: 4px solid #8d8d8d;
            padding: 0.85rem; margin-bottom: 0.8rem;
        }
        .ri-inherent-rating-row {
            display: flex; justify-content: space-between; gap: 1rem; align-items: center;
            padding-bottom: 0.65rem; margin-bottom: 0.65rem; border-bottom: 1px solid #e0e0e0;
        }
        .ri-inherent-rating-row span {
            display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-inherent-rating-row b {
            display: block; color: #161616; font-size: 1.05rem; margin-top: 0.15rem;
        }
        .ri-inherent-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
        .ri-inherent-head span {
            color: #525252; font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-inherent-badge {
            display: inline-flex; align-items: center; min-height: 34px; padding: 0.25rem 0.7rem;
            font-size: 1.1rem; font-weight: 800;
        }
        .ri-inherent-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.45rem; }
        .ri-inherent-metrics div { background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.55rem; }
        .ri-inherent-metrics span {
            display: block; color: #525252; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-inherent-metrics b { display: block; margin-top: 0.15rem; color: #161616; font-size: 1rem; }
        .ri-inherent-rationale-grid {
            display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.55rem;
            margin-top: 0.65rem;
        }
        .ri-inherent-rationale-grid div {
            background: #ffffff; border: 1px solid #e0e0e0; border-top: 3px solid #8d8d8d;
            padding: 0.7rem;
        }
        .ri-inherent-rationale-grid span {
            display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
            margin-bottom: 0.3rem;
        }
        .ri-inherent-rationale-grid p {
            color: #393939; line-height: 1.45; margin: 0;
        }
        .ri-matrix-title {
            color: #525252; font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
            margin: 0.1rem 0 0.45rem 0;
        }
        .ri-control-coverage-panel {
            background: #ffffff; border-bottom: 1px solid #e0e0e0; padding: 0.55rem 0 0.9rem 0;
            margin: 0.45rem 0 1rem 0;
        }
        .ri-control-coverage-panel:last-child { border-bottom: 0; }
        .ri-gap-card { border-left: 4px solid #f1c21b; }
        .ri-control-coverage-panel p, .ri-gap-card p { color: #393939; margin: 0.5rem 0 0.65rem 0; line-height: 1.45; }
        .ri-control-statement {
            color: #161616 !important; font-size: 1rem; line-height: 1.52 !important;
            margin: 0.65rem 0 0.55rem 0 !important;
        }
        .ri-control-statement-wrap {
            background: #f4f4f4; border: 1px solid #c6c6c6;
            padding: 0.75rem; margin-top: 0.75rem;
        }
        .ri-control-badge-row { margin: 0.15rem 0 0.45rem 0; }
        .ri-evidence-line { margin-top: 0.55rem !important; }
        .ri-control-score-panel {
            background: #ffffff; border: 1px solid #c6c6c6; border-left: 4px solid #009d9a;
            padding: 0.9rem; margin: 0.55rem 0 0.8rem 0;
        }
        .ri-control-score-panel.ri-score-low { border-left-color: #24a148; }
        .ri-control-score-panel.ri-score-medium { border-left-color: #f1c21b; }
        .ri-control-score-panel.ri-score-high { border-left-color: #ff832b; }
        .ri-control-score-panel.ri-score-critical { border-left-color: #da1e28; }
        .ri-control-score-panel.ri-score-neutral { border-left-color: #8d8d8d; }
        .ri-control-score-main span, .ri-control-score-grid span {
            display: block; color: #525252; font-size: 0.72rem; text-transform: uppercase; font-weight: 700;
        }
        .ri-control-score-main b {
            display: inline-block; color: #161616; font-size: 2.35rem; line-height: 1; margin-top: 0.2rem;
            min-width: 3.35rem; text-align: center; padding: 0.38rem 0.55rem;
        }
        .ri-control-score-value.ri-score-low { background: #defbe6; color: #044317; }
        .ri-control-score-value.ri-score-medium { background: #fff1c7; color: #684e00; }
        .ri-control-score-value.ri-score-high { background: #ffd7c2; color: #8a3800; }
        .ri-control-score-value.ri-score-critical { background: #da1e28; color: #ffffff; }
        .ri-control-score-value.ri-score-neutral { background: #e0e0e0; color: #161616; }
        .ri-control-score-main p {
            color: #393939; margin: 0.35rem 0 0.65rem 0; font-weight: 600;
        }
        .ri-control-score-rationale {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.65rem; margin-bottom: 0.6rem;
        }
        .ri-control-score-rationale b { display: block; margin-bottom: 0.25rem; }
        .ri-control-score-rationale p { margin: 0; color: #393939; line-height: 1.45; }
        .ri-control-score-grid {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.45rem;
        }
        .ri-control-score-grid div {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.55rem;
        }
        .ri-control-score-grid b { display: block; margin-top: 0.15rem; overflow-wrap: anywhere; }
        .ri-control-assessment-grid {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.45rem;
            margin: 0.75rem 0;
        }
        .ri-control-assessment {
            background: #ffffff; border: 1px solid #e0e0e0; border-top: 4px solid #8d8d8d;
            padding: 0.65rem; min-height: 136px;
        }
        .ri-control-assessment.ri-assessment-low { border-top-color: #24a148; }
        .ri-control-assessment.ri-assessment-medium { border-top-color: #f1c21b; }
        .ri-control-assessment.ri-assessment-high { border-top-color: #ff832b; }
        .ri-control-assessment.ri-assessment-critical { border-top-color: #da1e28; }
        .ri-control-assessment span {
            display: block; color: #525252; font-size: 0.72rem; text-transform: uppercase; font-weight: 700;
        }
        .ri-control-assessment b {
            display: block; color: #161616; font-size: 1rem; margin-top: 0.18rem; overflow-wrap: anywhere;
        }
        .ri-control-assessment p {
            margin: 0.45rem 0 0 0 !important; color: #393939; font-size: 0.88rem; line-height: 1.38 !important;
        }
        .ri-control-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
        .ri-control-id {
            display: inline-block; background: #e0e0e0; color: #161616; padding: 0.12rem 0.35rem;
            margin-right: 0.35rem; font-size: 0.74rem; font-weight: 700;
        }
        .ri-control-type {
            color: #525252; font-size: 0.78rem; font-weight: 700; text-align: right; max-width: 36%;
            overflow-wrap: anywhere;
        }
        .ri-control-detail-grid {
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.45rem;
            margin: 0.75rem 0;
        }
        .ri-control-detail-grid div {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.55rem;
        }
        .ri-control-detail-grid span, .ri-control-context span {
            color: #525252; font-size: 0.72rem; text-transform: uppercase; font-weight: 700;
        }
        .ri-control-detail-grid b { display: block; margin-top: 0.15rem; overflow-wrap: anywhere; }
        .ri-control-context {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.65rem; margin-top: 0.55rem;
        }
        .ri-control-context b { display: block; margin-bottom: 0.25rem; }
        .ri-control-context p { margin: 0.25rem 0; }
        .ri-control-context ul { margin: 0.3rem 0 0 1rem; padding: 0; }
        .ri-exec-strip { margin-bottom: 0.75rem; }
        .ri-statement { font-size: 1.02rem; color: #161616; padding: 0.9rem; background: #f4f4f4; border-left: 4px solid #0f62fe; margin-bottom: 0.5rem; line-height: 1.48; }
        .ri-profile-shell {
            border: 1px solid #c6c6c6; background: #ffffff; padding: 0.85rem 1rem;
            border-left: 4px solid #0f62fe; margin-bottom: 0.75rem;
        }
        .ri-profile-title { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
        .ri-profile-title span { color: #525252; font-size: 0.8rem; font-weight: 700; }
        .ri-profile-title b { font-size: 1.15rem; text-align: right; }
        .ri-profile-subtitle { color: #525252; margin-top: 0.25rem; }
        .ri-profile-snapshot { margin-bottom: 0.8rem; }
        .ri-command-header, .ri-command-main, .ri-validation-card, .ri-dossier, .ri-intake-profile, .ri-intake-note {
            background: #ffffff; border: 1px solid #c6c6c6; padding: 0.9rem 1rem; margin-bottom: 0.75rem;
        }
        .ri-command-header { border-left: 4px solid #0f62fe; }
        .ri-command-header span, .ri-command-kicker, .ri-validation-card span, .ri-dossier span, .ri-source-card span {
            color: #525252; font-size: 0.74rem; text-transform: uppercase; font-weight: 700;
        }
        .ri-command-header b, .ri-validation-card b { display: block; font-size: 1.08rem; margin-top: 0.2rem; }
        .ri-command-header p, .ri-command-main p, .ri-validation-card p, .ri-dossier p, .ri-source-card p {
            color: #393939; margin: 0.35rem 0 0 0; line-height: 1.42;
        }
        .ri-command-main { border-left: 4px solid #0f62fe; min-height: 184px; }
        .ri-command-main h3 { margin: 0.2rem 0 0.45rem 0; font-size: 1.32rem; }
        .ri-queue-summary, .ri-why-grid, .ri-source-grid, .ri-bu-diff-grid {
            display: grid; gap: 0.5rem; margin-bottom: 0.7rem;
        }
        .ri-queue-summary { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .ri-queue-summary div, .ri-why-grid div {
            background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.6rem;
        }
        .ri-queue-summary span, .ri-why-grid span { display: block; color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; }
        .ri-queue-summary b, .ri-why-grid b { display: block; font-size: 1.1rem; margin-top: 0.15rem; }
        .ri-queue-card, .ri-review-queue {
            border: 1px solid #c6c6c6; background: #ffffff; padding: 0.65rem; margin: 0.45rem 0;
        }
        .ri-queue-selected { outline: 3px solid #0f62fe; outline-offset: -3px; }
        .ri-queue-card span, .ri-review-queue span { color: #525252; font-size: 0.72rem; font-weight: 700; }
        .ri-queue-card b, .ri-review-queue b { display: block; font-size: 0.92rem; line-height: 1.22; }
        .ri-queue-card p, .ri-review-queue p { color: #525252; margin: 0.25rem 0 0.35rem 0; font-size: 0.8rem; }
        .ri-risk-drawer {
            display: flex; justify-content: space-between; gap: 1.25rem; align-items: flex-start;
            background: #ffffff; border-left: 4px solid #0f62fe; padding: 0.75rem 0.9rem; margin-bottom: 0.6rem;
        }
        .ri-risk-drawer span { color: #525252; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; }
        .ri-risk-drawer b { display: block; font-size: 1rem; margin-top: 0.15rem; }
        .ri-risk-drawer p { color: #393939; line-height: 1.42; margin: 0.35rem 0 0 0; }
        .ri-why-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .ri-why-grid p { margin: 0.25rem 0 0 0; color: #393939; font-size: 0.82rem; }
        .ri-decision-stack { display: grid; gap: 0.45rem; }
        .ri-validation-card { border-left: 4px solid #f1c21b; }
        .ri-dossier { border-left: 4px solid #009d9a; }
        .ri-dossier-strong { background: #f4f4f4; border-left-color: #8d8d8d; }
        .ri-dossier h3 { margin: 0.2rem 0 0.45rem 0; }
        .ri-dossier-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem; margin-top: 0.75rem; }
        .ri-dossier-meta div { background: #ffffff; border: 1px solid #e0e0e0; padding: 0.6rem; }
        .ri-dossier-meta span { display: block; }
        .ri-dossier-meta b { display: block; font-size: 0.95rem; margin-top: 0.15rem; overflow-wrap: anywhere; }
        .ri-source-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
        .ri-source-card { min-height: 122px; background: #ffffff; border: 1px solid #c6c6c6; padding: 0.7rem; border-top: 4px solid #0f62fe; }
        .ri-source-card b { display: block; font-size: 1.25rem; margin-top: 0.25rem; color: #161616; }
        .ri-source-card p { font-size: 0.82rem; }
        .ri-profile-grid { grid-template-columns: repeat(7, minmax(0, 1fr)); }
        .ri-intake-profile { border-left: 4px solid #009d9a; }
        .ri-intake-profile b { display: block; font-size: 1rem; margin-bottom: 0.25rem; }
        .ri-intake-profile span, .ri-intake-note { color: #525252; }
        .ri-bu-diff-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
        .ri-bu-diff-card { background: #ffffff; border: 1px solid #c6c6c6; border-top: 4px solid #8d8d8d; padding: 0.75rem; }
        .ri-bu-diff-card span { color: #525252; font-size: 0.76rem; font-weight: 700; }
        .ri-bu-diff-card b { display: block; margin-top: 0.18rem; }
        .ri-bu-diff-card p { font-size: 0.82rem; color: #393939; line-height: 1.36; min-height: 84px; }
        .ri-heatmap-wrap {
            border: 1px solid #c6c6c6; background: #ffffff; padding: 0.75rem; margin-bottom: 0.5rem;
        }
        .ri-heat-caption, .ri-heat-impact-caption {
            color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; text-align: center;
        }
        .ri-heatmap { display: grid; grid-template-columns: 92px repeat(4, minmax(52px, 1fr)); gap: 0.25rem; margin-top: 0.4rem; }
        .ri-heat-label, .ri-heat-axis, .ri-port-head, .ri-port-corner {
            color: #525252; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
            display: flex; align-items: center; justify-content: center; text-align: center;
        }
        .ri-heat-cell {
            min-height: 58px; border: 1px solid #c6c6c6; display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 0.1rem;
        }
        .ri-heat-cell span { font-size: 0.72rem; font-weight: 700; }
        .ri-heat-cell b { font-size: 1.02rem; }
        .ri-heat-selected { outline: 3px solid #161616; outline-offset: -4px; box-shadow: inset 0 0 0 2px #ffffff; }
        .ri-heat-axis-row { display: grid; grid-template-columns: 92px repeat(4, minmax(52px, 1fr)); gap: 0.25rem; margin-top: 0.25rem; }
        .ri-port-grid { display: grid; gap: 0.25rem; margin: 0.5rem 0 1rem 0; }
        .ri-port-corner, .ri-port-head, .ri-port-bu {
            min-height: 44px; background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.45rem;
        }
        .ri-port-bu { color: #161616; font-weight: 700; display: flex; align-items: center; }
        .ri-port-cell {
            min-height: 58px; border: 1px solid #c6c6c6; padding: 0.45rem; display: flex;
            flex-direction: column; align-items: center; justify-content: center;
        }
        .ri-port-cell b { font-size: 1.1rem; }
        .ri-port-cell span { font-size: 0.75rem; color: #393939; }
        .ri-port-low, .ri-port-none { background: #defbe6; }
        .ri-port-medium { background: #fff1c7; }
        .ri-port-high { background: #ffd7d9; }
        .ri-badge, .ri-chip { display: inline-block; padding: 0.22rem 0.48rem; margin: 0.12rem 0.18rem 0.12rem 0; font-size: 0.76rem; font-weight: 700; border-radius: 2px; }
        .ri-chip { background: #f4f4f4; border: 1px solid #c6c6c6; color: #393939; font-weight: 600; }
        .ri-low { background: #defbe6; color: #044317; }
        .ri-medium { background: #fff1c7; color: #684e00; }
        .ri-high { background: #ffd7d9; color: #750e13; }
        .ri-critical { background: #da1e28; color: #ffffff; }
        .ri-neutral { background: #e0e0e0; color: #161616; }
        .ri-blue { background: #d0e2ff; color: #001d6c; }
        .ri-teal { background: #9ef0f0; color: #003a3a; }
        .ri-muted { color: #6f6f6f; }
        .ri-rating-tile { border: 1px solid #c6c6c6; padding: 0.8rem; min-height: 92px; }
        .ri-rating-tile b { display: block; font-size: 1.25rem; margin-top: 0.35rem; }
        .ri-fact-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem; margin-bottom: 0.75rem; }
        .ri-fact-grid div { background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.65rem; }
        div[data-testid="stDataFrame"] { border: 1px solid #c6c6c6; }
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"] {
            white-space: normal !important;
            line-height: 1.28 !important;
            align-items: center !important;
        }

        .ri-bu-card { border-left: 4px solid #0f62fe; padding: 1rem; }
        .ri-bu-header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
        .ri-bu-name { font-size: 1.1rem; font-weight: 700; }
        .ri-bu-meta { display: grid; grid-template-columns: auto auto; gap: 0.15rem 0.85rem; font-size: 0.85rem; min-width: 240px; text-align: right; }
        .ri-bu-meta span { color: #525252; }
        .ri-bu-summary { margin-top: 0.5rem; color: #393939; }

        .ri-kri-intro { background: #f4f4f4; border-left: 4px solid #0f62fe; padding: 0.75rem 1rem; margin-bottom: 0.75rem; color: #393939; }
        .ri-kri-card { border-left: 4px solid #0f62fe; padding: 1rem; }
        .ri-kri-header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; margin-bottom: 0.5rem; }
        .ri-kri-id { display: inline-block; background: #d0e2ff; color: #001d6c; padding: 0.15rem 0.4rem; font-weight: 700; font-size: 0.78rem; margin-right: 0.4rem; }
        .ri-kri-name { font-size: 1.05rem; font-weight: 700; }
        .ri-kri-meta { display: grid; grid-template-columns: auto auto; gap: 0.15rem 0.85rem; font-size: 0.82rem; text-align: right; min-width: 280px; }
        .ri-kri-meta span { color: #525252; }
        .ri-kri-definition { margin-bottom: 0.45rem; color: #161616; }
        .ri-kri-thresholds { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; margin-bottom: 0.65rem; }
        .ri-kri-threshold { padding: 0.55rem 0.7rem; border: 1px solid #e0e0e0; }
        .ri-kri-threshold span { display: block; font-size: 0.74rem; text-transform: uppercase; font-weight: 700; }
        .ri-kri-threshold b { display: block; font-size: 0.92rem; margin-top: 0.2rem; }
        .ri-kri-narrative { margin: 0.4rem 0; color: #393939; }
        .ri-kri-selected-head {
            background: #f4f4f4; border: 1px solid #c6c6c6; padding: 0.75rem 0.85rem;
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.55rem;
        }
        .ri-kri-selected-head span {
            color: #525252; font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-kri-selected-head b { font-size: 1.18rem; color: #161616; }
        .ri-selected-kri-card {
            background: #ffffff; border: 1px solid #c6c6c6; border-top: 3px solid #8d8d8d;
            padding: 0.85rem; margin: 0.35rem 0 0.75rem 0; min-height: 100%;
        }
        .ri-selected-kri-header {
            display: block; margin-bottom: 0.65rem;
        }
        .ri-selected-kri-header > div:first-child span {
            display: inline-block; background: #e0e0e0; color: #161616; padding: 0.14rem 0.4rem;
            font-size: 0.72rem; font-weight: 700; margin-bottom: 0.35rem;
        }
        .ri-selected-kri-header > div:first-child b {
            display: block; font-size: 1.02rem; line-height: 1.25;
        }
        .ri-selected-kri-meta {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.35rem;
            min-width: 0; margin-top: 0.55rem;
        }
        .ri-selected-kri-meta div { background: #f4f4f4; border: 1px solid #e0e0e0; padding: 0.48rem; }
        .ri-selected-kri-meta span {
            display: block; color: #525252; font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
        }
        .ri-selected-kri-meta b { display: block; margin-top: 0.12rem; font-size: 0.82rem; overflow-wrap: anywhere; }
        .ri-selected-kri-definition {
            color: #393939; line-height: 1.45; margin: 0.45rem 0 !important;
        }
        .ri-selected-kri-threshold-line {
            display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.55rem 0;
        }
        .ri-selected-kri-threshold-line span {
            background: #f4f4f4; border: 1px solid #e0e0e0; color: #393939;
            padding: 0.3rem 0.45rem; font-size: 0.78rem; overflow-wrap: anywhere;
        }
        .ri-selected-kri-threshold-line b {
            color: #525252; text-transform: uppercase; font-size: 0.66rem; margin-right: 0.35rem;
        }
        .ri-selected-kri-note { margin: 0.38rem 0 0 0 !important; color: #393939; line-height: 1.42; }
        @media (max-width: 900px) {
            .ri-kb-io-grid, .ri-kb-benefit-band > div, .ri-kb-flow { grid-template-columns: 1fr; }
            .ri-scope-lens { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .ri-source-grid, .ri-bu-diff-grid, .ri-why-grid, .ri-neutral-summary, .ri-residual-calc-strip, .ri-dossier-meta, .ri-control-detail-grid, .ri-control-score-grid, .ri-control-assessment-grid, .ri-inherent-metrics, .ri-inherent-rationale-grid, .ri-selected-kri-meta { grid-template-columns: 1fr; }
            .ri-risk-header, .ri-control-head, .ri-kri-header, .ri-bu-header, .ri-selected-kri-header, .ri-inherent-rating-row {
                display: block;
            }
            .ri-risk-category, .ri-control-type, .ri-kri-meta, .ri-bu-meta, .ri-selected-kri-meta {
                max-width: none; text-align: left; margin-top: 0.35rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
