"""Remediation runner — gap selection, control generation, and results table.

Appears as a sub-section at the bottom of the Analysis tab after gaps have
been accepted via the gap dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import streamlit as st

from controlnexus.core.state import GapReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gap-report → flat rows
# ---------------------------------------------------------------------------

def _gap_report_to_rows(gap_report: GapReport) -> list[dict[str, Any]]:
    """Flatten a GapReport into selectable rows with a ``gap_type`` column."""
    rows: list[dict[str, Any]] = []

    for gap in gap_report.regulatory_gaps:
        rows.append({
            "selected": True,
            "gap_type": "regulatory",
            "detail": f"{gap.framework} — {gap.required_theme}",
            "severity": gap.severity,
            "framework": gap.framework,
            "required_theme": gap.required_theme,
            "current_coverage": gap.current_coverage,
        })

    for gap in gap_report.balance_gaps:
        if gap.direction == "under":
            rows.append({
                "selected": True,
                "gap_type": "balance",
                "detail": (
                    f"{gap.control_type} under-represented "
                    f"({gap.actual_pct:.1f}% vs {gap.expected_pct:.1f}%)"
                ),
                "severity": "medium",
                "control_type": gap.control_type,
                "expected_pct": gap.expected_pct,
                "actual_pct": gap.actual_pct,
            })

    for issue in gap_report.frequency_issues:
        rows.append({
            "selected": True,
            "gap_type": "frequency",
            "detail": (
                f"{issue.control_id}: "
                f"{issue.actual_frequency} → {issue.expected_frequency}"
            ),
            "severity": "low",
            "control_id": issue.control_id,
            "hierarchy_id": issue.hierarchy_id,
            "expected_frequency": issue.expected_frequency,
            "actual_frequency": issue.actual_frequency,
        })

    for issue in gap_report.evidence_issues:
        rows.append({
            "selected": True,
            "gap_type": "evidence",
            "detail": (
                f"{issue.control_id}: "
                f"{issue.issue or 'Insufficient evidence'}"
            ),
            "severity": "low",
            "control_id": issue.control_id,
            "hierarchy_id": issue.hierarchy_id,
            "issue": issue.issue,
        })

    return rows


# ---------------------------------------------------------------------------
# Selected rows → planner-ready gap_report dict
# ---------------------------------------------------------------------------

def _rows_to_gap_dict(selected_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert selected flat rows back into the dict shape expected by ``plan_assignments``."""
    gap_dict: dict[str, Any] = {
        "regulatory_gaps": [],
        "balance_gaps": [],
        "frequency_issues": [],
        "evidence_issues": [],
    }

    for row in selected_rows:
        gt = row.get("gap_type", "")
        if gt == "regulatory":
            gap_dict["regulatory_gaps"].append({
                "framework": row.get("framework", ""),
                "required_theme": row.get("required_theme", ""),
                "current_coverage": row.get("current_coverage", 0),
                "severity": row.get("severity", "medium"),
            })
        elif gt == "balance":
            gap_dict["balance_gaps"].append({
                "control_type": row.get("control_type", ""),
                "expected_pct": row.get("expected_pct", 0),
                "actual_pct": row.get("actual_pct", 0),
                "direction": "under",
            })
        elif gt == "frequency":
            gap_dict["frequency_issues"].append({
                "control_id": row.get("control_id", ""),
                "hierarchy_id": row.get("hierarchy_id", ""),
                "expected_frequency": row.get("expected_frequency", ""),
                "actual_frequency": row.get("actual_frequency", ""),
            })
        elif gt == "evidence":
            gap_dict["evidence_issues"].append({
                "control_id": row.get("control_id", ""),
                "hierarchy_id": row.get("hierarchy_id", ""),
                "issue": row.get("issue", ""),
            })

    return gap_dict


# ---------------------------------------------------------------------------
# Build a single remediation record from one assignment
# ---------------------------------------------------------------------------

def _build_record(assignment: dict[str, Any], index: int) -> dict[str, Any]:
    """Convert a single planner assignment into a remediation control record.

    Each gap type produces a deterministic record.  Frequency and evidence
    fixes are fully deterministic; regulatory and balance produce reasonable
    stubs that can later be refined by LLM agents.
    """
    gap_source = assignment.get("gap_source", "")
    control_id = assignment.get("control_id", f"REM-{index + 1:04d}")
    hierarchy_id = assignment.get("hierarchy_id", "")

    if gap_source == "frequency":
        expected = assignment.get("expected_frequency", "Monthly")
        actual = assignment.get("actual_frequency", "")
        return {
            "control_id": control_id,
            "hierarchy_id": hierarchy_id,
            "gap_source": gap_source,
            "control_type": "Frequency Fix",
            "who": "Control Owner",
            "what": f"Updates control frequency from {actual} to {expected}",
            "when": f"{expected}, per updated policy requirements",
            "frequency": expected,
            "where": "Enterprise Control System",
            "why": (
                "To ensure the control operates at the appropriate frequency "
                "and provides adequate risk coverage for timely detection"
            ),
            "full_description": (
                f"The Control Owner updates the execution frequency of control "
                f"{control_id} from {actual} to {expected} in the Enterprise "
                f"Control System. This change aligns the control cadence with "
                f"policy requirements and ensures adequate risk coverage. The "
                f"updated frequency provides timely detection and prevention "
                f"of control gaps, supporting ongoing compliance and effective "
                f"risk mitigation across the control ecosystem."
            ),
            "quality_rating": "Satisfactory",
            "evidence": f"Updated control schedule showing {expected} frequency",
        }

    if gap_source == "evidence":
        issue = assignment.get("issue", "Insufficient evidence documentation")
        return {
            "control_id": control_id,
            "hierarchy_id": hierarchy_id,
            "gap_source": gap_source,
            "control_type": "Evidence Enhancement",
            "who": "Control Owner",
            "what": "Enhances evidence documentation with specific artifacts",
            "when": "During each control execution cycle",
            "frequency": "Per execution",
            "where": "Enterprise Document Management System",
            "why": (
                "To improve evidence sufficiency and maintain a complete "
                "audit trail for compliance review and assurance"
            ),
            "full_description": (
                f"The Control Owner enhances the evidence documentation for "
                f"control {control_id} in the Enterprise Document Management "
                f"System by specifying the artifact name, preparer sign-off, "
                f"and retention location. This addresses the identified issue: "
                f"{issue}. The improved evidence package ensures adequate "
                f"sufficiency for audit and compliance review, supporting "
                f"regulatory requirements and internal assurance processes."
            ),
            "quality_rating": "Satisfactory",
            "evidence": "Evidence package with artifact, sign-off, and retention details",
        }

    if gap_source == "regulatory":
        framework = assignment.get("framework", "Regulatory Framework")
        theme = assignment.get("required_theme", "compliance requirement")
        return {
            "control_id": f"REM-REG-{index + 1:04d}",
            "hierarchy_id": "",
            "gap_source": gap_source,
            "control_type": "Regulatory Compliance",
            "who": "Compliance Officer",
            "what": f"Monitors and validates compliance with {framework} requirements",
            "when": "Quarterly, within 10 business days of quarter-end",
            "frequency": "Quarterly",
            "where": "Governance Risk and Compliance Platform",
            "why": (
                f"To ensure adequate coverage of {framework} {theme} "
                f"requirements and prevent regulatory compliance gaps"
            ),
            "full_description": (
                f"The Compliance Officer monitors and validates compliance "
                f"with {framework} requirements related to {theme} in the "
                f"Governance Risk and Compliance Platform on a quarterly basis "
                f"within 10 business days of quarter-end. This control ensures "
                f"adequate regulatory coverage, prevents compliance gaps, and "
                f"supports the organization's risk management framework by "
                f"providing timely detection of regulatory exposure."
            ),
            "quality_rating": "Satisfactory",
            "evidence": f"Quarterly compliance assessment report for {framework}",
        }

    if gap_source == "balance":
        control_type = assignment.get("control_type", "Control")
        return {
            "control_id": f"REM-BAL-{index + 1:04d}",
            "hierarchy_id": "",
            "gap_source": gap_source,
            "control_type": control_type,
            "who": "Control Owner",
            "what": f"Performs {control_type} activities to improve ecosystem balance",
            "when": "Monthly, within 5 business days of month-end",
            "frequency": "Monthly",
            "where": "Enterprise Control System",
            "why": (
                f"To address under-representation of {control_type} controls "
                f"and improve ecosystem balance for effective risk mitigation"
            ),
            "full_description": (
                f"The Control Owner performs {control_type} activities in the "
                f"Enterprise Control System on a monthly basis within 5 "
                f"business days of month-end. This new control addresses the "
                f"under-representation of {control_type} controls in the "
                f"ecosystem, improving distribution balance and ensuring "
                f"comprehensive risk coverage across all control dimensions "
                f"for effective compliance and risk mitigation."
            ),
            "quality_rating": "Satisfactory",
            "evidence": f"Monthly {control_type} execution log with sign-off",
        }

    # Unknown gap source — return a minimal record
    return {
        "control_id": f"REM-{index + 1:04d}",
        "hierarchy_id": hierarchy_id,
        "gap_source": gap_source,
        "control_type": "Remediation",
        "who": "Control Owner",
        "what": "Addresses identified control gap",
        "when": "Monthly",
        "frequency": "Monthly",
        "where": "Enterprise System",
        "why": "To remediate the identified gap and reduce risk exposure",
        "full_description": (
            "The Control Owner addresses the identified control gap in the "
            "Enterprise System on a monthly basis to remediate the issue and "
            "reduce risk exposure. This control ensures adequate coverage and "
            "supports the organization's compliance and risk management "
            "objectives through systematic gap closure."
        ),
        "quality_rating": "Needs Improvement",
        "evidence": "Gap remediation report",
    }


# ---------------------------------------------------------------------------
# Run remediation — processes each assignment directly
# ---------------------------------------------------------------------------

def _run_remediation(
    selected_rows: list[dict[str, Any]],
    section_profiles: dict,
    status: Any = None,
) -> list[dict[str, Any]]:
    """Process selected gaps into remediation control records.

    Iterates over all planned assignments and builds a deterministic
    control record for each one.  This approach processes every
    assignment (not just the first) and always produces output.
    """
    from controlnexus.remediation.planner import plan_assignments

    gap_dict = _rows_to_gap_dict(selected_rows)
    assignments = plan_assignments(gap_dict)

    if not assignments:
        return []

    generated: list[dict[str, Any]] = []

    for i, assignment in enumerate(assignments):
        gap_source = assignment.get("gap_source", "unknown")
        detail = assignment.get("framework") or assignment.get("control_id") or f"#{i + 1}"
        if status:
            status.write(
                f"Processing assignment {i + 1}/{len(assignments)} "
                f"({gap_source}: {detail})…"
            )
        record = _build_record(assignment, i)
        generated.append(record)

    logger.info(
        "Remediation produced %d records from %d assignments",
        len(generated),
        len(assignments),
    )
    return generated


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------

def render_remediation_runner() -> None:
    """Render the remediation section: gap selection → generate → results table."""

    # -- Guard: need accepted gaps -----------------------------------------
    gap_report: GapReport | None = st.session_state.get("accepted_gaps")
    if gap_report is None:
        return  # nothing to show yet

    st.markdown(
        '<div class="report-title" style="font-size:1.75rem;">Remediation</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="report-subtitle">'
        "Select gaps to remediate, then generate controls"
        "</div>",
        unsafe_allow_html=True,
    )

    # -- Build selectable gap rows -----------------------------------------
    gap_rows = _gap_report_to_rows(gap_report)
    if not gap_rows:
        st.success("No actionable gaps to remediate.")
        return

    st.markdown("#### Select Gaps")
    st.caption(
        "Toggle the **Selected** checkbox to include or exclude individual "
        "gaps from remediation."
    )

    # Use st.data_editor for interactive selection
    edited_rows = st.data_editor(
        gap_rows,
        column_config={
            "selected": st.column_config.CheckboxColumn("Selected", default=True),
            "gap_type": st.column_config.TextColumn("Gap Type"),
            "detail": st.column_config.TextColumn("Detail", width="large"),
            "severity": st.column_config.TextColumn("Severity"),
            # Hide internal fields from display
            "framework": None,
            "required_theme": None,
            "current_coverage": None,
            "control_type": None,
            "expected_pct": None,
            "actual_pct": None,
            "control_id": None,
            "hierarchy_id": None,
            "expected_frequency": None,
            "actual_frequency": None,
            "issue": None,
        },
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        key="remediation_gap_editor",
    )

    selected = [r for r in edited_rows if r.get("selected", False)]
    total = len(gap_rows)
    st.markdown(f"**{len(selected)}** of **{total}** gaps selected for remediation.")

    # -- Generate button ---------------------------------------------------
    generate_disabled = len(selected) == 0
    if st.button(
        "Generate Remediation Controls",
        type="primary",
        disabled=generate_disabled,
        key="btn_generate_remediation",
    ):
        section_profiles = st.session_state.get("section_profiles", {})

        status = st.status("Running remediation pipeline…", expanded=True)
        try:
            status.write(f"Planning assignments for {len(selected)} gaps…")
            results = _run_remediation(selected, section_profiles, status=status)
            st.session_state["remediation_results"] = results
            status.write(f"Generated **{len(results)}** control record(s).")
            status.update(
                label=f"Remediation Complete — {len(results)} controls generated",
                state="complete",
                expanded=False,
            )
            st.rerun()
        except Exception as e:
            status.update(label="Remediation Failed", state="error")
            st.error(f"Error during remediation: {e}")
            logger.exception("Remediation pipeline error")

    # -- Results table -----------------------------------------------------
    results = st.session_state.get("remediation_results")
    if results:
        st.markdown("---")
        st.markdown("#### Generated Controls")

        # Summary cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Generated", len(results))
        quality_counts: dict[str, int] = {}
        for rec in results:
            q = rec.get("quality_rating", "Unknown")
            quality_counts[q] = quality_counts.get(q, 0) + 1
        col2.metric(
            "Satisfactory+",
            quality_counts.get("Satisfactory", 0) + quality_counts.get("Strong", 0),
        )
        col3.metric(
            "Needs Review",
            quality_counts.get("Weak", 0) + quality_counts.get("Needs Improvement", 0),
        )

        # Reusable data table
        from controlnexus.ui.components.data_table import render_data_table

        render_data_table(
            records=results,
            default_columns=[
                "control_id",
                "gap_source",
                "what",
                "when",
                "full_description",
                "quality_rating",
            ],
            key="remediation_results",
            title="REMEDIATION OUTPUT",
            export_filename="remediation_controls.csv",
        )

        # Excel download
        _render_excel_download(results)


def _render_excel_download(results: list[dict[str, Any]]) -> None:
    """Offer an Excel download of generated controls."""
    try:
        from controlnexus.core.state import FinalControlRecord
        from controlnexus.export.excel import export_to_excel

        records: list[FinalControlRecord] = []
        for i, rec in enumerate(results):
            try:
                records.append(FinalControlRecord(
                    control_id=rec.get("control_id", f"REM-{i + 1:04d}"),
                    hierarchy_id=rec.get("hierarchy_id", ""),
                    leaf_name=rec.get("leaf_name", ""),
                    control_type=rec.get("control_type", ""),
                    who=rec.get("who", ""),
                    what=rec.get("what", ""),
                    when=rec.get("when", ""),
                    frequency=rec.get("frequency", "Other"),
                    where=rec.get("where", ""),
                    why=rec.get("why", ""),
                    full_description=rec.get("full_description", ""),
                    quality_rating=rec.get("quality_rating", "Satisfactory"),
                    evidence=rec.get("evidence", ""),
                ))
            except Exception:
                continue

        if records:
            tmp = NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.close()
            export_to_excel(records, tmp.name, sheet_name="remediation")
            with open(tmp.name, "rb") as f:
                xlsx_bytes = f.read()
            Path(tmp.name).unlink(missing_ok=True)
            st.download_button(
                label="⬇ Download Excel",
                data=xlsx_bytes,
                file_name="remediation_controls.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="remediation_xlsx_dl",
            )
    except Exception as e:
        logger.warning("Excel export unavailable: %s", e)
