"""
Excel export and review import/export utilities.

Produces multi-sheet Excel workbooks for gap reports, compliance matrices,
and intermediate review files with approve/reject columns.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def export_gap_report(
    gap_report: dict[str, Any],
    classified: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    path: str,
) -> str:
    """Export a multi-sheet Excel workbook with full pipeline results.

    Sheets: Summary, Classified Obligations, APQC Mappings,
    Coverage Assessment, Gaps, Risk Register
    """
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Sheet 1: Summary
        summary_data = {
            "Metric": [
                "Regulation",
                "Total Obligations",
                "Mapped Obligations",
            ],
            "Value": [
                gap_report.get("regulation_name", ""),
                gap_report.get("total_obligations", 0),
                gap_report.get("mapped_obligation_count", 0),
            ],
        }
        # Add classified counts
        for cat, count in gap_report.get("classified_counts", {}).items():
            summary_data["Metric"].append(f"Category: {cat}")
            summary_data["Value"].append(count)
        # Add coverage summary
        for status, count in gap_report.get("coverage_summary", {}).items():
            summary_data["Metric"].append(f"Coverage: {status}")
            summary_data["Value"].append(count)

        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

        # Sheet 2: Classified Obligations
        if classified:
            df_classified = pd.DataFrame(classified)
            cols_order = [
                "citation", "obligation_category", "relationship_type",
                "criticality_tier", "section_citation", "section_title",
                "subpart", "abstract", "classification_rationale",
            ]
            cols_present = [c for c in cols_order if c in df_classified.columns]
            df_classified[cols_present].to_excel(
                writer, sheet_name="Classified Obligations", index=False,
            )

        # Sheet 3: APQC Mappings
        if mappings:
            df_mappings = pd.DataFrame(mappings)
            cols_order = [
                "citation", "apqc_hierarchy_id", "apqc_process_name",
                "relationship_type", "relationship_detail", "confidence",
            ]
            cols_present = [c for c in cols_order if c in df_mappings.columns]
            df_mappings[cols_present].to_excel(
                writer, sheet_name="APQC Mappings", index=False,
            )

        # Sheet 4: Coverage Assessment
        if assessments:
            df_assess = pd.DataFrame(assessments)
            df_assess.to_excel(writer, sheet_name="Coverage Assessment", index=False)

        # Sheet 5: Gaps
        gaps = gap_report.get("gaps", [])
        if gaps:
            pd.DataFrame(gaps).to_excel(writer, sheet_name="Gaps", index=False)
        else:
            pd.DataFrame({"Note": ["No gaps found"]}).to_excel(
                writer, sheet_name="Gaps", index=False,
            )

        # Sheet 6: Risk Register
        if risks:
            df_risks = pd.DataFrame(risks)
            cols_order = [
                "risk_id", "source_citation", "source_apqc_id",
                "risk_description", "risk_category", "sub_risk_category",
                "impact_rating", "frequency_rating", "inherent_risk_rating",
                "coverage_status", "impact_rationale", "frequency_rationale",
            ]
            cols_present = [c for c in cols_order if c in df_risks.columns]
            df_risks[cols_present].to_excel(
                writer, sheet_name="Risk Register", index=False,
            )
        else:
            pd.DataFrame({"Note": ["No risks extracted"]}).to_excel(
                writer, sheet_name="Risk Register", index=False,
            )

    return path


def export_compliance_matrix(matrix: dict[str, Any], path: str) -> str:
    """Export the compliance matrix as a flat Excel table."""
    rows = matrix.get("rows", [])
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame({"Note": ["No matrix data"]})
    df.to_excel(path, index=False, engine="openpyxl")
    return path


def export_for_review(data: list[dict[str, Any]], stage: str, path: str) -> str:
    """Export intermediate results for human review.

    Adds an 'approved' column (default True) that the human can toggle.
    """
    if not data:
        pd.DataFrame({"Note": [f"No {stage} data to review"]}).to_excel(
            path, index=False, engine="openpyxl",
        )
        return path

    df = pd.DataFrame(data)
    df.insert(0, "approved", True)
    df.to_excel(path, sheet_name=stage, index=False, engine="openpyxl")
    return path


def import_reviewed(path: str, stage: str) -> list[dict[str, Any]]:
    """Import human-reviewed Excel back.

    Reads the 'approved' column, filters to approved=True.
    Returns the approved records as dicts.
    """
    try:
        df = pd.read_excel(path, sheet_name=stage, engine="openpyxl")
    except Exception:
        # Try first sheet if stage name doesn't match
        df = pd.read_excel(path, sheet_name=0, engine="openpyxl")

    if "approved" in df.columns:
        # Filter to approved rows (handle various truthy representations)
        df = df[df["approved"].astype(str).str.lower().isin(("true", "1", "yes"))]
        df = df.drop(columns=["approved"])

    records = df.to_dict(orient="records")
    # Clean NaN values
    for r in records:
        for k, v in r.items():
            if pd.isna(v):
                r[k] = ""
    return records
