"""Risk Inventory Builder Streamlit tab.

Front-end-only experience that supports two storylines:

1. **Workspace Dashboard (multi-BU):** in demo mode, the user can browse all
   business units, see the bank's knowledge base (BUs, procedures, taxonomies,
   controls, KRIs), and compare risk profiles across BUs.
2. **Procedure-specific drill-down:** the user picks a procedure (or BU) and
   sees the full risk inventory generated for that procedure, with the same
   Risk Inventory / Control Mapping / Residual / KRI / Review / Executive
   tabs as the user-driven workflow.

In non-demo mode, the user uploads procedure documents and runs the
deterministic graph as before — the Input / Upload tab now also exposes the
multi-table format for business units, controls, taxonomies, and procedures
the user already has on file.
"""

from __future__ import annotations

import html
import json
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
    load_demo_risk_inventory,
    load_demo_workspace,
)
from controlnexus.risk_inventory.document_ingest import DocumentAnalysis, analyze_process_document
from controlnexus.risk_inventory.export import risk_inventory_excel_bytes
from controlnexus.risk_inventory.graph import build_risk_inventory_graph
from controlnexus.risk_inventory.models import (
    KRIDefinition,
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskInventoryWorkspace,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_risk_inventory_tab() -> None:
    """Render the full Risk Inventory Builder experience."""
    _inject_risk_inventory_css()
    header_left, header_right = st.columns([5, 1.35])
    with header_left:
        st.markdown(
            """
            <section class="ri-hero">
                <div class="ri-eyebrow">Risk Inventory Builder</div>
                <h1>Convert process evidence into a risk inventory</h1>
                <p>
                    Browse the bank's knowledge base, drill into business unit risk profiles,
                    or ingest a procedure document to generate a fresh inventory aligned to
                    the bank's two-tier enterprise risk taxonomy.
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with header_right:
        st.markdown('<div class="ri-toggle-panel">', unsafe_allow_html=True)
        demo_enabled = st.toggle(
            "Demo Mode",
            value=bool(st.session_state.get("demo_mode", False)),
            key="demo_mode",
            help="Load the demo bank workspace with three business units, four procedures, and a CRO-authored KRI library.",
        )
        st.caption("No LLM credentials required.")
        st.markdown("</div>", unsafe_allow_html=True)

    if demo_enabled:
        _render_demo_workspace()
    else:
        _render_user_workflow()


# ---------------------------------------------------------------------------
# Demo workspace experience (Storylines 1 & 2)
# ---------------------------------------------------------------------------


def _render_demo_workspace() -> None:
    if "risk_inventory_workspace" not in st.session_state:
        st.session_state["risk_inventory_workspace"] = load_demo_workspace().model_dump()
    workspace = RiskInventoryWorkspace.model_validate(st.session_state["risk_inventory_workspace"])

    st.markdown(
        f'<div class="ri-notice"><b>Demo Mode</b> · {html.escape(workspace.bank_name)} workspace loaded '
        f"({len(workspace.business_units)} business units · {len(workspace.procedures)} procedures · "
        f"{len(workspace.kri_library)} KRIs).</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ri-section-title">Scope Selector</div>', unsafe_allow_html=True)
    scope_cols = st.columns([1.2, 1.6, 0.6])
    with scope_cols[0]:
        bu_options = ["All Business Units"] + [bu.bu_name for bu in workspace.business_units]
        bu_choice = st.selectbox("Business Unit", bu_options, key="ri_demo_bu_choice")
    with scope_cols[1]:
        if bu_choice == "All Business Units":
            procedure_pool = workspace.procedures
        else:
            selected_bu = next(bu for bu in workspace.business_units if bu.bu_name == bu_choice)
            procedure_pool = workspace.procedures_for_bu(selected_bu.bu_id)
        procedure_options = ["Workspace Dashboard (no procedure focus)"] + [
            p.procedure_name for p in procedure_pool
        ]
        procedure_choice = st.selectbox("Procedure Focus", procedure_options, key="ri_demo_proc_choice")
    with scope_cols[2]:
        st.write("")

    selected_bu_id: str | None = None
    if bu_choice != "All Business Units":
        selected_bu_id = next(bu.bu_id for bu in workspace.business_units if bu.bu_name == bu_choice)

    selected_run: RiskInventoryRun | None = None
    if procedure_choice != "Workspace Dashboard (no procedure focus)":
        selected_proc = next(p for p in procedure_pool if p.procedure_name == procedure_choice)
        selected_run = workspace.run_for_procedure(selected_proc.procedure_id)

    tabs = st.tabs(
        [
            "Knowledge Base",
            "Risk Inventory",
            "Control Mapping",
            "Residual & KRIs",
            "Review & Challenge",
            "Executive Report",
        ]
    )

    with tabs[0]:
        _render_knowledge_base(workspace)
    with tabs[1]:
        if selected_run:
            _render_risk_inventory_combined(selected_run, workspace)
        else:
            _render_workspace_aggregated_inventory(workspace, selected_bu_id)
    with tabs[2]:
        if selected_run:
            _render_control_mapping(selected_run)
        else:
            _render_empty_panel("Select a procedure focus above to view control mappings for a specific run.")
    with tabs[3]:
        if selected_run:
            _render_residual_and_kris(selected_run, workspace)
        else:
            _render_empty_panel("Select a procedure focus above to view residual ratings and recommended KRIs.")
    with tabs[4]:
        if selected_run:
            _render_review(selected_run)
        else:
            _render_empty_panel("Select a procedure focus above to view reviewer and challenge detail.")
    with tabs[5]:
        if selected_run:
            _render_executive(selected_run)
        else:
            _render_workspace_executive(workspace, selected_bu_id)


# ---------------------------------------------------------------------------
# User workflow (non-demo)
# ---------------------------------------------------------------------------


def _render_user_workflow() -> None:
    user_run_data = st.session_state.get("risk_inventory_user_run")
    run = RiskInventoryRun.model_validate(user_run_data) if user_run_data else None

    tabs = st.tabs(
        [
            "Overview",
            "Input / Upload",
            "Risk Inventory",
            "Control Mapping",
            "Residual & KRIs",
            "Review & Challenge",
            "Executive Report",
        ]
    )

    with tabs[0]:
        _render_overview_user(run)
    with tabs[1]:
        _render_input_and_maybe_run()
    with tabs[2]:
        _render_risk_inventory_combined(run, None) if run else _render_empty_panel(
            "Risk records will appear after you run the workflow."
        )
    with tabs[3]:
        _render_control_mapping(run) if run else _render_empty_panel(
            "Control mappings will appear after inventory creation."
        )
    with tabs[4]:
        _render_residual_and_kris(run, None) if run else _render_empty_panel(
            "Residual ratings and KRI recommendations will appear after inventory creation."
        )
    with tabs[5]:
        _render_review(run) if run else _render_empty_panel(
            "Review and challenge prompts will appear here."
        )
    with tabs[6]:
        _render_executive(run) if run else _render_empty_panel("Executive summary will appear here.")


# ---------------------------------------------------------------------------
# Overview tab (user mode only — empty-state guidance per requirements)
# ---------------------------------------------------------------------------


def _render_overview_user(run: RiskInventoryRun | None) -> None:
    if run is None:
        _render_empty_state()
        return

    _render_summary_metrics(run)
    st.markdown('<div class="ri-section-title">Pipeline</div>', unsafe_allow_html=True)
    st.markdown('<div class="ri-flow">', unsafe_allow_html=True)
    for stage in [
        "Understand Process",
        "Identify Applicable Risks",
        "Assess Inherent Risk",
        "Map Controls",
        "Evaluate Controls",
        "Determine Residual Risk",
    ]:
        st.markdown(f"<span>{html.escape(stage)}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="ri-section-title">Executive Takeaway</div>', unsafe_allow_html=True)
        st.write(run.executive_summary.headline)
        for message in run.executive_summary.key_messages:
            st.markdown(f"- {message}")
    with right:
        st.markdown('<div class="ri-section-title">Residual Risk Distribution</div>', unsafe_allow_html=True)
        distribution = Counter(record.residual_risk.residual_rating.value for record in run.records)
        st.dataframe(
            [
                {"Rating": rating, "Count": distribution.get(rating, 0)}
                for rating in ["Low", "Medium", "High", "Critical"]
            ],
            hide_index=True,
            width="stretch",
        )
        _download_export(run, "overview")


def _render_workspace_aggregated_inventory(
    workspace: RiskInventoryWorkspace, selected_bu_id: str | None
) -> None:
    st.markdown('<div class="ri-section-title">Aggregated Risk Inventory</div>', unsafe_allow_html=True)
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
                    "Risk ID": rec.risk_id,
                    "BU": next(
                        (bu.bu_name for bu in workspace.business_units if bu.bu_id == proc.bu_id),
                        proc.bu_id,
                    ),
                    "Procedure": proc.procedure_name,
                    "L1": rec.taxonomy_node.level_1_category,
                    "L2 Category": rec.taxonomy_node.level_2_category,
                    "Inherent": rec.inherent_risk.inherent_rating.value,
                    "Residual": rec.residual_risk.residual_rating.value,
                    "Controls": len(rec.control_mappings),
                    "Response": rec.residual_risk.management_response.response_type.value.title(),
                }
            )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No runs available for the selected scope.")


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
# Knowledge Base tab
# ---------------------------------------------------------------------------


def _render_knowledge_base(workspace: RiskInventoryWorkspace) -> None:
    st.markdown('<div class="ri-section-title">Bank Knowledge Base</div>', unsafe_allow_html=True)
    st.caption(
        "Read-only view of the data the bank has already supplied: business units, procedures, "
        "risk taxonomy (two-tier), control taxonomy, root-cause taxonomy, controls register, and KRI library."
    )

    sub_tabs = st.tabs(
        [
            "Business Units",
            "Procedures",
            "Risk Taxonomy (2-Tier)",
            "Control Taxonomy",
            "Root Cause Taxonomy",
            "Controls Register",
            "KRI Library",
        ]
    )

    with sub_tabs[0]:
        st.dataframe(
            [
                {
                    "BU ID": bu.bu_id,
                    "Business Unit": bu.bu_name,
                    "Head": bu.head,
                    "Employees": bu.employee_count,
                    "# Procedures": len(workspace.procedures_for_bu(bu.bu_id)),
                    "Description": bu.description,
                    "Risk Profile": bu.risk_profile_summary,
                }
                for bu in workspace.business_units
            ],
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[1]:
        bu_lookup = {bu.bu_id: bu.bu_name for bu in workspace.business_units}
        st.dataframe(
            [
                {
                    "Procedure ID": p.procedure_id,
                    "Procedure": p.procedure_name,
                    "Business Unit": bu_lookup.get(p.bu_id, p.bu_id),
                    "Owner": p.owner,
                    "Criticality": p.criticality,
                    "Cadence": p.cadence,
                    "Last Reviewed": p.last_reviewed,
                    "Systems": ", ".join(p.related_systems),
                }
                for p in workspace.procedures
            ],
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[2]:
        st.markdown("**Level 1 — Enterprise Risk Categories**")
        st.dataframe(
            [
                {
                    "L1 Code": l1.code,
                    "L1 Name": l1.name,
                    "Definition": l1.definition,
                    "# L2 Sub-Categories": len(l1.level_2_codes),
                }
                for l1 in workspace.risk_taxonomy_l1
            ],
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Level 2 — Risk Sub-Categories**")
        l2_to_l1: dict[str, str] = {}
        for l1 in workspace.risk_taxonomy_l1:
            for code in l1.level_2_codes:
                l2_to_l1[code] = f"{l1.code} · {l1.name}"
        st.dataframe(
            [
                {
                    "L2 Code": node.id,
                    "L1": l2_to_l1.get(node.id, node.level_1_category),
                    "L2 Sub-Category": node.level_2_category,
                    "Definition": node.definition,
                    "Typical Root Causes": ", ".join(node.typical_root_causes),
                    "Regulatory Relevance": ", ".join(node.regulatory_relevance),
                }
                for node in workspace.risk_taxonomy_l2
            ],
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[3]:
        st.dataframe(
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
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[4]:
        st.dataframe(
            [
                {
                    "Code": rc.code,
                    "Category": rc.category,
                    "Root Cause": rc.name,
                    "Description": rc.description,
                    "Examples": "; ".join(rc.examples),
                }
                for rc in workspace.root_cause_taxonomy
            ],
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[5]:
        st.dataframe(
            [
                {
                    "Control ID": c.get("control_id", ""),
                    "Control": c.get("control_name", ""),
                    "Type": c.get("control_type", ""),
                    "Owner": c.get("owner", ""),
                    "Frequency": c.get("frequency", ""),
                    "Design": c.get("design_rating", ""),
                    "Operating": c.get("operating_rating", ""),
                    "Description": c.get("description", ""),
                }
                for c in workspace.bank_controls
            ],
            hide_index=True,
            width="stretch",
        )

    with sub_tabs[6]:
        l2_lookup = {node.id: node.level_2_category for node in workspace.risk_taxonomy_l2}
        st.dataframe(
            [
                {
                    "KRI ID": k.kri_id,
                    "KRI": k.kri_name,
                    "Risk (L2)": l2_lookup.get(k.risk_taxonomy_id, k.risk_taxonomy_id),
                    "Owner": k.owner,
                    "Frequency": k.measurement_frequency,
                    "Green": k.thresholds.green,
                    "Amber": k.thresholds.amber,
                    "Red": k.thresholds.red,
                }
                for k in workspace.kri_library
            ],
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Risk Inventory tab (combined Inherent + Inventory)
# ---------------------------------------------------------------------------


def _render_risk_inventory_combined(
    run: RiskInventoryRun, workspace: RiskInventoryWorkspace | None
) -> None:
    record = _risk_selector(run, "ri_inventory_select")
    _render_risk_header(record)

    cols = st.columns([1, 1.6])
    with cols[0]:
        st.markdown('<div class="ri-section-title">Root Cause</div>', unsafe_allow_html=True)
        _render_root_cause_panel(record, workspace)
    with cols[1]:
        st.markdown('<div class="ri-section-title">Risk Statement</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ri-statement">{html.escape(record.risk_statement.risk_description)}</div>',
            unsafe_allow_html=True,
        )
        if record.risk_statement.risk_event:
            st.markdown(
                f"<small><b>Risk event:</b> {html.escape(record.risk_statement.risk_event)}</small>",
                unsafe_allow_html=True,
            )
        _render_chip_group("Consequences", record.risk_statement.consequences)
        _render_chip_group("Affected stakeholders", record.risk_statement.affected_stakeholders)

    st.markdown('<div class="ri-section-title">Inherent Risk Assessment</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Overall Impact", int(record.impact_assessment.overall_impact_score))
    m2.metric("Likelihood", int(record.likelihood_assessment.likelihood_score))
    m3.markdown(_rating_html(record.inherent_risk.inherent_rating.value, "Inherent Rating"), unsafe_allow_html=True)

    st.markdown("**Impact Dimensions**")
    st.dataframe(
        [
            {
                "Dimension": item.dimension.value.replace("_", " ").title(),
                "Score": int(item.score),
                "Rationale": item.rationale,
            }
            for item in record.impact_assessment.dimensions
        ],
        hide_index=True,
        width="stretch",
    )

    st.markdown("**Likelihood Rationale**")
    st.write(record.likelihood_assessment.rationale)

    with st.expander("Exposure metrics", expanded=True):
        st.dataframe(
            [
                {
                    "Metric": metric.metric_name,
                    "Value": metric.metric_value,
                    "Unit": metric.metric_unit,
                    "Source": metric.source,
                }
                for metric in record.exposure_metrics
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("All risk records (this run)", expanded=False):
        st.dataframe(_risk_rows(run), hide_index=True, width="stretch")


def _render_root_cause_panel(
    record: RiskInventoryRecord, workspace: RiskInventoryWorkspace | None
) -> None:
    causes = record.risk_statement.causes or record.taxonomy_node.typical_root_causes
    if not causes:
        st.write("No root causes recorded.")
        return

    rc_lookup: dict[str, Any] = {}
    if workspace:
        for rc in workspace.root_cause_taxonomy:
            rc_lookup[rc.name.lower()] = rc
            for ex in rc.examples:
                rc_lookup[ex.lower()] = rc

    for cause in causes:
        cause_lower = cause.lower()
        rc = None
        for key, candidate in rc_lookup.items():
            if key in cause_lower or cause_lower in key:
                rc = candidate
                break
        category = rc.category if rc else "Uncategorized"
        code = rc.code if rc else ""
        description = rc.description if rc else ""
        tone = {
            "People": "blue",
            "Process": "teal",
            "Technology": "medium",
            "External": "high",
        }.get(category, "neutral")
        code_chip = f'<span class="ri-chip">{html.escape(code)}</span>' if code else ""
        desc_html = (
            f'<div class="ri-rootcause-desc">{html.escape(description)}</div>' if description else ""
        )
        st.markdown(
            f"""
            <div class="ri-rootcause ri-{tone}">
                <div class="ri-rootcause-cause">{html.escape(cause)}</div>
                <div class="ri-rootcause-meta">
                    <span class="ri-chip">{html.escape(category)}</span>
                    {code_chip}
                </div>
                {desc_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if workspace:
        st.caption(
            "Root causes are mapped against the bank's Root Cause Taxonomy "
            "(People · Process · Technology · External) where a match exists."
        )


# ---------------------------------------------------------------------------
# Control Mapping tab
# ---------------------------------------------------------------------------


def _render_control_mapping(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_mapping_select")
    _render_risk_header(record)
    if not record.control_mappings:
        st.warning("No controls are mapped to this risk. This is a coverage gap.")
        return
    for mapping in record.control_mappings:
        design_rating = (
            mapping.design_effectiveness.rating.value if mapping.design_effectiveness else "Not Rated"
        )
        operating_rating = (
            mapping.operating_effectiveness.rating.value
            if mapping.operating_effectiveness
            else "Not Rated"
        )
        st.markdown(
            f"""
            <div class="ri-control-card">
                <div>
                    <b>{html.escape(mapping.control_name)}</b>
                    <span class="ri-muted"> · {html.escape(mapping.control_type)}</span>
                </div>
                <p>{html.escape(mapping.mitigation_rationale)}</p>
                <div>
                    {_badge("Coverage", mapping.coverage_assessment.title(), "neutral")}
                    {_badge("Design", design_rating, "blue")}
                    {_badge("Operating", operating_rating, "teal")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with st.expander("All mapped controls (this run)", expanded=False):
        rows = []
        for rec in run.records:
            for m in rec.control_mappings:
                rows.append(
                    {
                        "Risk ID": rec.risk_id,
                        "L2 Category": rec.taxonomy_node.level_2_category,
                        "Control": m.control_name,
                        "Type": m.control_type,
                        "Coverage": m.coverage_assessment,
                    }
                )
        st.dataframe(rows, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Residual & KRIs tab
# ---------------------------------------------------------------------------


def _render_residual_and_kris(
    run: RiskInventoryRun, workspace: RiskInventoryWorkspace | None
) -> None:
    record = _risk_selector(run, "ri_residual_select")
    _render_risk_header(record)

    _render_control_coverage(record)
    st.divider()
    _render_effectiveness_detail(record)
    st.divider()
    _render_kri_recommendations(record, workspace)
    st.divider()
    _render_residual_review_summary(record)


def _render_control_coverage(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">Control Coverage</div>', unsafe_allow_html=True)
    mappings = record.control_mappings
    if not mappings:
        st.warning("No controls are mapped to this risk. This is a coverage gap requiring management response.")
        return

    typical_causes = list(record.taxonomy_node.typical_root_causes)
    cause_coverage: Counter[str] = Counter()
    for mapping in mappings:
        for cause in mapping.mapped_root_causes:
            cause_coverage[cause] += 1
    type_coverage = Counter(m.control_type or "Unspecified" for m in mappings)

    summary_cols = st.columns(3)
    summary_cols[0].metric("Mapped Controls", len(mappings))
    summary_cols[1].metric(
        "Root Causes Covered",
        f"{len(cause_coverage)} / {len(typical_causes) or len(cause_coverage)}",
    )
    summary_cols[2].metric("Control Types", len(type_coverage))

    left, mid, right = st.columns([1.1, 1, 1.2])
    with left:
        st.markdown("**Mapped controls**")
        st.dataframe(
            [
                {
                    "Control": m.control_name,
                    "Type": m.control_type,
                    "Coverage": m.coverage_assessment.title(),
                }
                for m in mappings
            ],
            hide_index=True,
            width="stretch",
        )
    with mid:
        st.markdown("**Coverage by root cause**")
        rows = []
        seen = set()
        for cause in typical_causes:
            count = cause_coverage.get(cause, 0)
            rows.append(
                {"Root cause": cause, "# Controls": count, "Status": "Covered" if count else "Gap"}
            )
            seen.add(cause)
        for cause, count in cause_coverage.items():
            if cause not in seen:
                rows.append({"Root cause": cause, "# Controls": count, "Status": "Covered"})
        st.dataframe(rows, hide_index=True, width="stretch")
    with right:
        st.markdown("**Coverage by control type**")
        st.dataframe(
            [
                {"Control type": ctype, "# Controls": count}
                for ctype, count in type_coverage.most_common()
            ],
            hide_index=True,
            width="stretch",
        )

    st.markdown("**Coverage gaps**")
    gaps: list[str] = list(record.coverage_gaps)
    for cause in typical_causes:
        if not cause_coverage.get(cause):
            gaps.append(f"Root cause not covered by any mapped control: {cause}")
    if gaps:
        for gap in gaps:
            st.markdown(f"- {html.escape(gap)}")
    else:
        st.success("No coverage gaps identified for typical root causes.")


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
    st.dataframe(
        [
            {
                "Control": m.control_name,
                "Design": m.design_effectiveness.rating.value if m.design_effectiveness else "Not Rated",
                "Operating": m.operating_effectiveness.rating.value if m.operating_effectiveness else "Not Rated",
                "Open Issues": len(m.open_issues),
                "Evidence Quality": m.evidence_quality.rating if m.evidence_quality else "Not Assessed",
                "Last Tested": m.evidence_quality.last_tested if m.evidence_quality else "",
            }
            for m in mappings
        ],
        hide_index=True,
        width="stretch",
    )

    if open_issue_total:
        st.markdown("**Open issues**")
        st.dataframe(
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
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# KRI Recommendations (replaces Appetite & Decisioning)
# ---------------------------------------------------------------------------


def _render_kri_recommendations(
    record: RiskInventoryRecord, workspace: RiskInventoryWorkspace | None
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
        formula_block = (
            f'<div class="ri-kri-formula"><code>{html.escape(kri.formula)}</code> ({html.escape(kri.unit)})</div>'
            if kri.formula
            else ""
        )
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
                {formula_block}
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
        if kri.use_cases:
            with st.expander(f"Reporting cadence and use cases — {kri.kri_name}", expanded=False):
                for use_case in kri.use_cases:
                    st.markdown(f"- {html.escape(use_case)}")

    _render_kri_program_design(record)


def _render_kri_program_design(record: RiskInventoryRecord) -> None:
    st.markdown('<div class="ri-section-title">KRI Program Design Notes</div>', unsafe_allow_html=True)
    residual = record.residual_risk.residual_rating.value
    inherent = record.inherent_risk.inherent_rating.value
    plan_lines: list[str] = []
    if residual in {"High", "Critical"}:
        plan_lines.append(
            f"**Reporting cadence.** Because residual is {residual}, all KRIs above should be reported "
            "weekly to the BU head and monthly to the Operational Risk Committee until residual is "
            "sustained at Medium or below for two consecutive quarters."
        )
    elif residual == "Medium":
        plan_lines.append(
            "**Reporting cadence.** Residual is Medium — report KRIs monthly to the BU head and "
            "quarterly to the Operational Risk Committee. Promote any sustained amber to monthly committee review."
        )
    else:
        plan_lines.append(
            "**Reporting cadence.** Residual is Low — KRIs should still be measured at the documented "
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
    causes = ", ".join(record.taxonomy_node.typical_root_causes) or "see taxonomy"
    metrics = ", ".join(m.metric_name for m in record.exposure_metrics) or "see exposure section"
    st.markdown(
        f"""
        <div class="ri-kri-card">
            <div class="ri-kri-narrative">
                <b>How to design a KRI for {html.escape(record.taxonomy_node.level_2_category)}.</b>
                Start from the typical root causes ({html.escape(causes)}) and the
                process exposure metrics already collected ({html.escape(metrics)}).
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
    st.markdown('<div class="ri-section-title">Review & Challenge Summary</div>', unsafe_allow_html=True)
    if not record.review_challenges:
        st.info("No reviewer activity recorded yet. Use the Review & Challenge tab to capture comments and overrides.")
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

    st.caption("Open the Review & Challenge tab for full reviewer workflow and validation findings.")


def _render_review(run: RiskInventoryRun) -> None:
    record = _risk_selector(run, "ri_review_select")
    _render_risk_header(record)
    review = record.review_challenges[0] if record.review_challenges else None
    status_options = ["Not Started", "Pending Review", "Challenged", "Approved"]
    current_status = review.review_status.value if review else "Pending Review"
    st.selectbox(
        "Review Status",
        status_options,
        index=status_options.index(current_status) if current_status in status_options else 1,
        key=f"ri_review_status_{record.risk_id}",
    )
    st.text_area(
        "Challenge Comments",
        value=review.challenge_comments if review else "",
        height=120,
        key=f"ri_review_comments_{record.risk_id}",
        help="Capture business challenge comments before final approval.",
    )
    if review:
        _render_chip_group("Fields requiring review", review.challenged_fields)
    st.markdown('<div class="ri-section-title">Validation Findings</div>', unsafe_allow_html=True)
    findings = [finding for finding in run.validation_findings if finding.record_id == record.risk_id]
    if findings:
        st.dataframe([finding.model_dump() for finding in findings], hide_index=True, width="stretch")
    else:
        st.success("No validation findings for this record.")


def _render_executive(run: RiskInventoryRun) -> None:
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
    st.dataframe(_risk_rows(run), hide_index=True, width="stretch")
    _download_export(run, "executive")


# ---------------------------------------------------------------------------
# User Input / Upload tab
# ---------------------------------------------------------------------------


def _render_input_and_maybe_run() -> RiskInventoryRun | None:
    st.markdown(
        '<div class="ri-section-title">Existing Bank Knowledge Base</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Review the data already on file (business units, controls, risk taxonomy, control taxonomy, "
        "procedures, and KRIs). Use the upload area further down to add or replace any of it."
    )
    _render_user_existing_knowledge_tables()

    st.markdown(
        '<div class="ri-section-title">Add or Replace Data — Procedure Document</div>',
        unsafe_allow_html=True,
    )
    st.caption("Upload a PDF, TXT, or Markdown procedure. The builder extracts process context and analysis cues.")

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

    st.markdown('<div class="ri-section-title">Run Deterministic Workflow</div>', unsafe_allow_html=True)
    run_cols = st.columns([2, 1])
    with run_cols[0]:
        st.write(
            "The graph will apply two-tier taxonomy matching, draft risk records, map controls, and calculate scores."
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
            "Procedures",
            "Risk Taxonomy",
            "Control Taxonomy",
            "Controls Register",
            "KRI Library",
        ]
    )
    placeholder_columns = {
        "Business Units": ["BU ID", "Business Unit", "Head", "Employees", "Description"],
        "Procedures": ["Procedure ID", "Procedure", "BU", "Owner", "Cadence", "Last Reviewed"],
        "Risk Taxonomy": ["L1 Code", "L1", "L2 Code", "L2 Sub-Category", "Definition"],
        "Control Taxonomy": ["Code", "Family", "Control Family", "Description"],
        "Controls Register": [
            "Control ID",
            "Control",
            "Type",
            "Owner",
            "Frequency",
            "Design",
            "Operating",
        ],
        "KRI Library": ["KRI ID", "KRI", "Risk (L2)", "Owner", "Frequency", "Green", "Amber", "Red"],
    }
    table_keys = {
        "Business Units": "ri_user_bus",
        "Procedures": "ri_user_procs",
        "Risk Taxonomy": "ri_user_risk_taxonomy",
        "Control Taxonomy": "ri_user_control_taxonomy",
        "Controls Register": "ri_user_controls",
        "KRI Library": "ri_user_kris",
    }
    for tab, label in zip(sub_tabs, list(placeholder_columns.keys())):
        with tab:
            data = st.session_state.get(table_keys[label], [])
            if data:
                st.dataframe(data, hide_index=True, width="stretch")
            else:
                st.dataframe(
                    [{col: "" for col in placeholder_columns[label]}],
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    f"No {label.lower()} on file. Use the uploads below to populate this table, "
                    "or load Demo Mode to see a fully populated example."
                )


# ---------------------------------------------------------------------------
# Upload helpers (preserved from prior implementation)
# ---------------------------------------------------------------------------


def _document_upload() -> DocumentAnalysis | None:
    upload_col, sample_col = st.columns([2, 1])
    with upload_col:
        uploaded = st.file_uploader(
            "Upload process policy/procedure",
            type=["pdf", "txt", "md", "markdown"],
            key="ri_process_document_upload",
            help="PDF, TXT, or Markdown files are parsed locally and used to prefill process context.",
        )
    with sample_col:
        st.write("")
        st.write("")
        use_sample = st.button("Load sample procedure", width="stretch", key="ri_load_sample_doc")

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
            help="Use realistic sample controls when no control register is available.",
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


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="ri-empty">
            <h3>Start with evidence, not a blank form</h3>
            <p>
                Go to Input / Upload and add a policy or procedure PDF. The app will extract process context,
                likely risk categories, control cues, obligations, and exposure signals before it runs the graph.
            </p>
            <p>Or enable <b>Demo Mode</b> in the top-right corner to explore a complete multi-business-unit workspace.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_panel(message: str) -> None:
    st.markdown(f'<div class="ri-empty-small">{html.escape(message)}</div>', unsafe_allow_html=True)


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
        st.dataframe(
            [
                {
                    "Control ID": control.get("control_id", ""),
                    "Name": control.get("control_name", control.get("name", "")),
                    "Type": control.get("control_type", ""),
                    "Design": control.get("design_rating", "Satisfactory"),
                    "Operating": control.get("operating_rating", "Satisfactory"),
                }
                for control in controls
            ],
            hide_index=True,
            width="stretch",
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
    selected = st.selectbox("Select risk record", options, key=key)
    index = options.index(selected)
    return run.records[index]


def _render_risk_header(record: RiskInventoryRecord) -> None:
    st.markdown(
        f"""
        <div class="ri-risk-card">
            <div class="ri-risk-title">
                {html.escape(record.risk_id)} · {html.escape(record.taxonomy_node.level_2_category)}
            </div>
            <div class="ri-risk-tax">
                <span class="ri-chip ri-blue">L1: {html.escape(record.taxonomy_node.level_1_category)}</span>
                <span class="ri-chip">L2: {html.escape(record.taxonomy_node.level_2_category)}</span>
            </div>
            <div class="ri-risk-desc">{html.escape(record.risk_statement.risk_description)}</div>
            <div>
                {_badge("Inherent", record.inherent_risk.inherent_rating.value, _rating_class(record.inherent_risk.inherent_rating.value))}
                {_badge("Residual", record.residual_risk.residual_rating.value, _rating_class(record.residual_risk.residual_rating.value))}
                {_badge("Response", record.residual_risk.management_response.response_type.value.title(), "neutral")}
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


def _download_export(run: RiskInventoryRun, location: str) -> None:
    st.download_button(
        "Download Excel Workbook",
        data=risk_inventory_excel_bytes(run),
        file_name=f"{run.run_id}_risk_inventory.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"ri_xlsx_{location}_{run.run_id}",
        width="stretch",
    )


def _risk_rows(run: RiskInventoryRun) -> list[dict[str, Any]]:
    return [
        {
            "Risk ID": record.risk_id,
            "L1 Category": record.taxonomy_node.level_1_category,
            "L2 Category": record.taxonomy_node.level_2_category,
            "Risk Description": record.risk_statement.risk_description,
            "Inherent": record.inherent_risk.inherent_rating.value,
            "Control Environment": record.control_environment.control_environment_rating.value,
            "Residual": record.residual_risk.residual_rating.value,
            "Management Response": record.residual_risk.management_response.response_type.value,
            "Linked Controls": len(record.control_mappings),
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
        .ri-hero { background: #f4f4f4; border-left: 4px solid #0f62fe; padding: 1rem 1.25rem; margin-bottom: 1rem; }
        .ri-hero h1 { font-size: 1.85rem; margin: 0.15rem 0 0.35rem 0; line-height: 1.2; }
        .ri-hero p { color: #525252; margin: 0; max-width: 920px; }
        .ri-eyebrow, .ri-section-title { color: #0f62fe; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; margin: 1rem 0 0.35rem 0; }
        .ri-toggle-panel { background: #ffffff; border: 1px solid #c6c6c6; padding: 0.85rem; min-height: 112px; }
        .ri-notice { background: #e5f6ff; border-left: 4px solid #0072c3; padding: 0.7rem 0.9rem; margin-bottom: 0.8rem; }
        .ri-empty, .ri-empty-small { background: #f4f4f4; border: 1px solid #c6c6c6; padding: 1.1rem; margin-top: 0.75rem; }
        .ri-flow { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.7rem 0 1rem 0; }
        .ri-flow span { background: #edf5ff; border: 1px solid #78a9ff; color: #001d6c; padding: 0.45rem 0.65rem; font-size: 0.82rem; }
        .ri-metric { border: 1px solid #c6c6c6; background: #ffffff; padding: 0.85rem; min-height: 92px; border-top: 4px solid #0f62fe; }
        .ri-metric span, .ri-rating-tile span, .ri-fact-grid span { display: block; color: #525252; font-size: 0.75rem; text-transform: uppercase; font-weight: 600; }
        .ri-metric b { display: block; font-size: 1.8rem; margin-top: 0.2rem; }
        .ri-tone-green { border-top-color: #24a148; }
        .ri-tone-teal { border-top-color: #009d9a; }
        .ri-tone-red { border-top-color: #da1e28; }
        .ri-tone-yellow { border-top-color: #f1c21b; }
        .ri-risk-card, .ri-control-card, .ri-detail-panel, .ri-compact-risk, .ri-bu-card, .ri-kri-card, .ri-rootcause {
            background: #ffffff; border: 1px solid #c6c6c6; padding: 0.9rem; margin: 0.55rem 0;
        }
        .ri-risk-card { border-left: 4px solid #0f62fe; }
        .ri-risk-title { font-weight: 700; margin-bottom: 0.25rem; font-size: 1.05rem; }
        .ri-risk-tax { margin-bottom: 0.4rem; }
        .ri-risk-desc { color: #393939; margin-bottom: 0.65rem; }
        .ri-statement { font-size: 1.0rem; color: #161616; padding: 0.75rem; background: #f4f4f4; border-left: 4px solid #0f62fe; margin-bottom: 0.5rem; }
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

        .ri-bu-card { border-left: 4px solid #0f62fe; padding: 1rem; }
        .ri-bu-header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
        .ri-bu-name { font-size: 1.1rem; font-weight: 700; }
        .ri-bu-meta { display: grid; grid-template-columns: auto auto; gap: 0.15rem 0.85rem; font-size: 0.85rem; min-width: 240px; text-align: right; }
        .ri-bu-meta span { color: #525252; }
        .ri-bu-summary { margin-top: 0.5rem; color: #393939; }

        .ri-rootcause { padding: 0.6rem 0.75rem; }
        .ri-rootcause-cause { font-weight: 700; }
        .ri-rootcause-meta { margin: 0.25rem 0; }
        .ri-rootcause-desc { font-size: 0.85rem; color: #525252; }
        .ri-rootcause.ri-blue { border-left: 4px solid #0f62fe; }
        .ri-rootcause.ri-teal { border-left: 4px solid #009d9a; }
        .ri-rootcause.ri-medium { border-left: 4px solid #f1c21b; }
        .ri-rootcause.ri-high { border-left: 4px solid #ff832b; }
        .ri-rootcause.ri-neutral { border-left: 4px solid #8d8d8d; }

        .ri-kri-intro { background: #f4f4f4; border-left: 4px solid #0f62fe; padding: 0.75rem 1rem; margin-bottom: 0.75rem; color: #393939; }
        .ri-kri-card { border-left: 4px solid #0f62fe; padding: 1rem; }
        .ri-kri-header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; margin-bottom: 0.5rem; }
        .ri-kri-id { display: inline-block; background: #d0e2ff; color: #001d6c; padding: 0.15rem 0.4rem; font-weight: 700; font-size: 0.78rem; margin-right: 0.4rem; }
        .ri-kri-name { font-size: 1.05rem; font-weight: 700; }
        .ri-kri-meta { display: grid; grid-template-columns: auto auto; gap: 0.15rem 0.85rem; font-size: 0.82rem; text-align: right; min-width: 280px; }
        .ri-kri-meta span { color: #525252; }
        .ri-kri-definition { margin-bottom: 0.45rem; color: #161616; }
        .ri-kri-formula { font-family: 'IBM Plex Mono', monospace; background: #f4f4f4; padding: 0.4rem 0.6rem; margin-bottom: 0.55rem; font-size: 0.85rem; }
        .ri-kri-thresholds { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; margin-bottom: 0.65rem; }
        .ri-kri-threshold { padding: 0.55rem 0.7rem; border: 1px solid #e0e0e0; }
        .ri-kri-threshold span { display: block; font-size: 0.74rem; text-transform: uppercase; font-weight: 700; }
        .ri-kri-threshold b { display: block; font-size: 0.92rem; margin-top: 0.2rem; }
        .ri-kri-narrative { margin: 0.4rem 0; color: #393939; }
        </style>
        """,
        unsafe_allow_html=True,
    )
