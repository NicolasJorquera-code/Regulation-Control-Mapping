"""Excel export for generated control records."""

from __future__ import annotations

import logging
from pathlib import Path

import openpyxl

from controlnexus.core.state import FinalControlRecord

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "control_id",
    "hierarchy_id",
    "leaf_name",
    "selected_level_1",
    "selected_level_2",
    "business_unit_id",
    "business_unit_name",
    "who",
    "what",
    "when",
    "frequency",
    "where",
    "why",
    "full_description",
    "quality_rating",
    "validator_passed",
    "validator_retries",
    "validator_failures",
    "evidence",
]


def export_to_excel(
    records: list[FinalControlRecord],
    output_path: Path | str,
    sheet_name: str = "generated_controls",
) -> Path:
    """Write FinalControlRecord list to an Excel file.

    Args:
        records: Controls to export.
        output_path: Path for the output .xlsx file.
        sheet_name: Name of the worksheet.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name

    # Header row
    ws.append(EXPORT_COLUMNS)

    # Data rows
    for record in records:
        export = record.to_export_dict()
        row = []
        for col in EXPORT_COLUMNS:
            val = export.get(col, "")
            if isinstance(val, list):
                val = str(val)
            row.append(val)
        ws.append(row)

    wb.save(output_path)
    logger.info("Exported %d controls to %s", len(records), output_path)
    return output_path
