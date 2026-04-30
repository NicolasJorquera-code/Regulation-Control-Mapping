"""Excel export for Risk Inventory Builder runs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from controlnexus.risk_inventory.models import RiskInventoryRecord, RiskInventoryRun

RATING_FILLS = {
    "Low": "C6EBD6",
    "Medium": "FDDC69",
    "High": "FFB3B8",
    "Critical": "DA1E28",
    "Strong": "C6EBD6",
    "Satisfactory": "D0E2FF",
    "Improvement Needed": "FDDC69",
    "Inadequate": "FFB3B8",
}

DROPDOWNS = {
    "Does Risk Materialize?": ["Yes", "No"],
    "Control Design Effectiveness": ["Strong", "Satisfactory", "Improvement Needed", "Inadequate"],
    "Control Operating Effectiveness": ["Strong", "Satisfactory", "Improvement Needed", "Inadequate"],
    "Control Environment Rating": ["Strong", "Satisfactory", "Improvement Needed", "Inadequate"],
    "Management Response": ["accept", "mitigate", "monitor", "escalate"],
    "Review Status": ["Not Started", "Pending Review", "Challenged", "Approved"],
    "Approval Status": ["Draft", "Approved", "Rejected"],
}


def export_risk_inventory_to_excel(run: RiskInventoryRun, output_path: Path | str) -> Path:
    """Write a multi-sheet risk inventory workbook to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_risk_inventory_workbook(run)
    workbook.save(output_path)
    return output_path


def risk_inventory_excel_bytes(run: RiskInventoryRun) -> bytes:
    """Return a workbook as XLSX bytes for Streamlit download buttons."""
    buffer = BytesIO()
    build_risk_inventory_workbook(run).save(buffer)
    return buffer.getvalue()


def build_risk_inventory_workbook(run: RiskInventoryRun) -> openpyxl.Workbook:
    """Build the required multi-sheet workbook from a RiskInventoryRun."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Executive Summary"
    _write_rows(
        ws,
        [
            {"Field": "Run ID", "Value": run.run_id},
            {"Field": "Process", "Value": run.input_context.process_name},
            {"Field": "Product", "Value": run.input_context.product},
            {"Field": "Headline", "Value": run.executive_summary.headline},
            {"Field": "Key Messages", "Value": "\n".join(run.executive_summary.key_messages)},
            {"Field": "Recommended Actions", "Value": "\n".join(run.executive_summary.recommended_actions)},
        ],
    )

    _write_rows(wb.create_sheet("Risk Inventory"), [_inventory_row(record) for record in run.records])
    _write_rows(wb.create_sheet("Inherent Risk Assessment"), [_inherent_row(record) for record in run.records])
    _write_rows(wb.create_sheet("Control Mapping"), _control_mapping_rows(run.records))
    _write_rows(wb.create_sheet("Control Effectiveness"), _control_effectiveness_rows(run.records))
    _write_rows(wb.create_sheet("Residual Risk Assessment"), [_residual_row(record) for record in run.records])
    _write_rows(wb.create_sheet("Review and Challenge"), _review_rows(run.records))
    _write_rows(wb.create_sheet("Scoring Matrices"), _matrix_rows(run))
    _write_rows(wb.create_sheet("Configuration Snapshot"), _config_rows(run.config_snapshot))
    _write_rows(wb.create_sheet("Validation Findings"), [finding.model_dump() for finding in run.validation_findings])

    for sheet in wb.worksheets:
        _format_sheet(sheet)
    return wb


def _write_rows(ws: Worksheet, rows: list[dict[str, Any]]) -> None:
    if not rows:
        ws.append(["No records"])
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([_cell_value(row.get(header, "")) for header in headers])


def _inventory_row(record: RiskInventoryRecord) -> dict[str, Any]:
    impact_scores = {item.dimension.value: int(item.score) for item in record.impact_assessment.dimensions}
    return {
        "Risk ID": record.risk_id,
        "Process ID": record.process_id,
        "Process Name": record.process_name,
        "Product": record.product,
        "Level 1 Risk Category": record.taxonomy_node.level_1_category,
        "Level 2 Risk Category": record.taxonomy_node.level_2_category,
        "Risk Taxonomy Definition": record.taxonomy_node.definition,
        "Does Risk Materialize?": "Yes" if record.applicability.materializes else "No",
        "Materialization Type": record.applicability.materialization_type.value,
        "Applicability Rationale": record.applicability.rationale,
        "Risk Description": record.risk_statement.risk_description,
        "Exposure Metrics": "\n".join(f"{m.metric_name}: {m.metric_value}" for m in record.exposure_metrics),
        "Financial Impact": impact_scores.get("financial_impact", ""),
        "Customer Impact": impact_scores.get("customer_impact", ""),
        "Regulatory Impact": impact_scores.get("regulatory_impact", ""),
        "Reputation Impact": impact_scores.get("reputational_impact", ""),
        "U.S. Financial System / Liquidity Impact": impact_scores.get("liquidity_impact", ""),
        "Overall Impact Score": int(record.impact_assessment.overall_impact_score),
        "Overall Impact Rationale": record.impact_assessment.overall_impact_rationale,
        "Overall Likelihood Score": int(record.likelihood_assessment.likelihood_score),
        "Overall Likelihood Rating": record.likelihood_assessment.likelihood_rating,
        "Overall Likelihood Rationale": record.likelihood_assessment.rationale,
        "Overall Inherent Risk Score": record.inherent_risk.inherent_score,
        "Overall Inherent Risk Rating": record.inherent_risk.inherent_label,
        "Linked Controls": "\n".join(f"{m.control_id}: {m.control_name}" for m in record.control_mappings),
        "Control Design Effectiveness": record.control_environment.design_rating.value,
        "Control Operating Effectiveness": record.control_environment.operating_rating.value,
        "Control Environment Rating": record.control_environment.control_environment_rating.value,
        "Residual Risk Score": record.residual_risk.residual_score,
        "Residual Risk Rating": record.residual_risk.residual_label,
        "Residual Risk Rationale": record.residual_risk.rationale,
        "Management Response": record.residual_risk.management_response.response_type.value,
        "Recommended Action": record.residual_risk.management_response.recommended_action,
        "Review Status": record.review_challenges[0].review_status.value if record.review_challenges else "",
        "Reviewer Comments": record.review_challenges[0].challenge_comments if record.review_challenges else "",
        "Validation Flags": "\n".join(f.message for f in record.validation_findings),
        "Demo Record": "Yes" if record.demo_record else "No",
    }


def _inherent_row(record: RiskInventoryRecord) -> dict[str, Any]:
    return {
        "Risk ID": record.risk_id,
        "Level 2 Risk Category": record.taxonomy_node.level_2_category,
        "Impact Score": int(record.impact_assessment.overall_impact_score),
        "Likelihood Score": int(record.likelihood_assessment.likelihood_score),
        "Inherent Score": record.inherent_risk.inherent_score,
        "Inherent Rating": record.inherent_risk.inherent_label,
        "Impact Rationale": record.impact_assessment.overall_impact_rationale,
        "Likelihood Rationale": record.likelihood_assessment.rationale,
    }


def _residual_row(record: RiskInventoryRecord) -> dict[str, Any]:
    return {
        "Risk ID": record.risk_id,
        "Inherent Rating": record.inherent_risk.inherent_label,
        "Control Environment Rating": record.control_environment.control_environment_rating.value,
        "Residual Score": record.residual_risk.residual_score,
        "Residual Rating": record.residual_risk.residual_label,
        "Management Response": record.residual_risk.management_response.response_type.value,
        "Recommended Action": record.residual_risk.management_response.recommended_action,
        "Rationale": record.residual_risk.rationale,
    }


def _control_mapping_rows(records: list[RiskInventoryRecord]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        for mapping in record.control_mappings:
            rows.append(
                {
                    "Risk ID": record.risk_id,
                    "Level 2 Risk Category": record.taxonomy_node.level_2_category,
                    "Control ID": mapping.control_id,
                    "Control Name": mapping.control_name,
                    "Control Type": mapping.control_type,
                    "Coverage Assessment": mapping.coverage_assessment,
                    "Mapping Rationale": mapping.mitigation_rationale,
                }
            )
    return rows


def _control_effectiveness_rows(records: list[RiskInventoryRecord]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        for mapping in record.control_mappings:
            rows.append(
                {
                    "Risk ID": record.risk_id,
                    "Control ID": mapping.control_id,
                    "Control Name": mapping.control_name,
                    "Design Rating": mapping.design_effectiveness.rating.value if mapping.design_effectiveness else "",
                    "Design Rationale": mapping.design_effectiveness.rationale if mapping.design_effectiveness else "",
                    "Operating Rating": mapping.operating_effectiveness.rating.value if mapping.operating_effectiveness else "",
                    "Operating Rationale": mapping.operating_effectiveness.rationale if mapping.operating_effectiveness else "",
                    "Control Environment Rating": record.control_environment.control_environment_rating.value,
                }
            )
    return rows


def _review_rows(records: list[RiskInventoryRecord]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        for review in record.review_challenges:
            rows.append(
                {
                    "Risk ID": record.risk_id,
                    "Review Status": review.review_status.value,
                    "Reviewer": review.reviewer,
                    "Challenged Fields": ", ".join(review.challenged_fields),
                    "Challenge Comments": review.challenge_comments,
                    "Reviewer Rationale": review.reviewer_rationale,
                    "Approval Status": review.approval_status.value,
                }
            )
    return rows


def _matrix_rows(run: RiskInventoryRun) -> list[dict[str, Any]]:
    rows = []
    inherent = run.config_snapshot.get("inherent_risk_matrix", {}).get("matrix", {})
    for impact, likelihoods in inherent.items():
        for likelihood, result in likelihoods.items():
            rows.append({"Matrix": "Inherent", "Impact": impact, "Likelihood/Environment": likelihood, **result})
    residual = run.config_snapshot.get("residual_risk_matrix", {}).get("matrix", {})
    for inherent_label, environments in residual.items():
        for environment, result in environments.items():
            rows.append(
                {
                    "Matrix": "Residual",
                    "Impact": inherent_label,
                    "Likelihood/Environment": environment,
                    **result,
                }
            )
    return rows


def _config_rows(snapshot: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in snapshot.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            rows.extend(_config_rows(value, path))
        else:
            rows.append({"Config Path": path, "Value": _cell_value(value)})
    return rows


def _cell_value(value: Any) -> Any:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return str(value)
    return value


def _format_sheet(ws: Worksheet) -> None:
    ws.freeze_panes = "A2"
    if ws.max_column > 1:
        ws.auto_filter.ref = ws.dimensions
    header_fill = PatternFill("solid", fgColor="161616")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            fill = RATING_FILLS.get(str(cell.value), "")
            if fill:
                cell.fill = PatternFill("solid", fgColor=fill)
    for column_cells in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 14), 42)
    _add_dropdowns(ws)


def _add_dropdowns(ws: Worksheet) -> None:
    headers = {str(cell.value): cell.column_letter for cell in ws[1] if cell.value}
    for header, values in DROPDOWNS.items():
        column = headers.get(header)
        if not column:
            continue
        validation = DataValidation(type="list", formula1=f'"{",".join(values)}"', allow_blank=True)
        ws.add_data_validation(validation)
        validation.add(f"{column}2:{column}1048576")
