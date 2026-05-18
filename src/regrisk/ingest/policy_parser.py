"""
Policy / Procedure Excel parser — internal authoritative-source inventory.

Reads the generalized ``Source_Inventory`` sheet (Phase 2 of the hybrid
source-led design) and emits ``Obligation`` instances stamped with the
appropriate ``source_type`` (Policy_Requirement | Standard | Procedure_Step).

Deterministic (no LLM). Pure Python + pandas. Mirrors the shape of
:mod:`regrisk.ingest.regulation_parser` so downstream agents and graphs
do not need to know whether the source is regulation-led or policy-led.
"""

from __future__ import annotations

import re

import pandas as pd

from regrisk.core.constants import (
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_PROCEDURE_STEP,
    SOURCE_TYPE_STANDARD,
    SOURCE_TYPES,
)
from regrisk.core.models import Obligation, ObligationGroup
from regrisk.exceptions import IngestError
from regrisk.ingest.utils import clean_str as _clean_str


# Sheet name constants
SOURCE_INVENTORY_SHEET = "Source_Inventory"

# Required columns; missing any of these → IngestError
_REQUIRED_COLUMNS: tuple[str, ...] = (
    "Source_ID",
    "Source_Type",
    "Source_Title",
    "Source_Text",
)

# Optional columns the parser will read if present
_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "Source_Document_Name",
    "Source_Section",
    "Source_Owner",
    "Business_Unit",
    "Legal_Entity",
    "Jurisdiction",
    "Effective_Date",
    "Review_Date",
    "Version",
    "Parent_Source_ID",
    "Procedure_ID",
    "Procedure_Title",
    "Procedure_Step",
    "Requirement_Type",
    "Requirement_Intent",
    "Control_Objective",
    "Risk_Theme",
    "Evidence_Reference",
    "Source_Confidence",
    "Extraction_Rationale",
    "Regulation_Links",
)


def _normalize_source_type(raw: str) -> str:
    """Coerce the Source_Type cell into a canonical SOURCE_TYPES value."""
    s = (raw or "").strip().replace(" ", "_").replace("-", "_")
    if not s:
        return SOURCE_TYPE_POLICY_REQUIREMENT
    # Case-insensitive match against the canonical set
    lower = s.lower()
    for canonical in SOURCE_TYPES:
        if canonical.lower() == lower:
            return canonical
    # Heuristics for common synonyms
    if "procedure" in lower or "step" in lower:
        return SOURCE_TYPE_PROCEDURE_STEP
    if "standard" in lower:
        return SOURCE_TYPE_STANDARD
    return SOURCE_TYPE_POLICY_REQUIREMENT


def _split_regulation_links(raw: str) -> list[str]:
    if not raw:
        return []
    # Accept comma, semicolon, or pipe separators
    parts = re.split(r"[,;|]", raw)
    return [p.strip() for p in parts if p.strip()]


def parse_policy_excel(path: str, sheet_name: str = SOURCE_INVENTORY_SHEET) -> tuple[str, list[Obligation]]:
    """Parse a Policy / Procedure Source Inventory workbook.

    Returns ``(inventory_name, list_of_obligations)``. Each row becomes an
    ``Obligation`` instance with ``source_type`` set per the row's ``Source_Type``
    column (defaults to ``Policy_Requirement``).
    """
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        raise IngestError(
            f"Failed to read policy/procedure Excel at {path} (sheet '{sheet_name}'): {exc}"
        ) from exc

    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise IngestError(
            f"Missing required columns in {sheet_name} sheet: {missing}"
        )

    obligations: list[Obligation] = []
    inventory_name = ""

    for _, row in df.iterrows():
        source_id = _clean_str(row.get("Source_ID"))
        if not source_id:
            # Skip blank rows silently
            continue

        source_type = _normalize_source_type(_clean_str(row.get("Source_Type")))
        title = _clean_str(row.get("Source_Title"))
        text = _clean_str(row.get("Source_Text"))
        document_name = _clean_str(row.get("Source_Document_Name"))
        section = _clean_str(row.get("Source_Section"))
        parent_source_id = _clean_str(row.get("Parent_Source_ID")) or None
        procedure_id = _clean_str(row.get("Procedure_ID"))
        procedure_title = _clean_str(row.get("Procedure_Title"))
        procedure_step = _clean_str(row.get("Procedure_Step"))
        requirement_type = _clean_str(row.get("Requirement_Type")) or None

        # Capture inventory name from the first non-empty document name
        if not inventory_name and document_name:
            inventory_name = document_name

        # Source confidence (optional float)
        sc_raw = row.get("Source_Confidence")
        try:
            source_confidence = float(sc_raw) if sc_raw not in (None, "") and not pd.isna(sc_raw) else None
        except (TypeError, ValueError):
            source_confidence = None

        # Build source_metadata dict — carries all policy-specific fields that
        # don't have first-class slots on the Obligation model.
        source_metadata: dict[str, object] = {
            "source_owner": _clean_str(row.get("Source_Owner")),
            "business_unit": _clean_str(row.get("Business_Unit")),
            "legal_entity": _clean_str(row.get("Legal_Entity")),
            "jurisdiction": _clean_str(row.get("Jurisdiction")),
            "review_date": _clean_str(row.get("Review_Date")),
            "version": _clean_str(row.get("Version")),
            "procedure_id": procedure_id,
            "procedure_title": procedure_title,
            "procedure_step": procedure_step,
            "requirement_intent": _clean_str(row.get("Requirement_Intent")),
            "control_objective": _clean_str(row.get("Control_Objective")),
            "risk_theme": _clean_str(row.get("Risk_Theme")),
            "evidence_reference": _clean_str(row.get("Evidence_Reference")),
            "extraction_rationale": _clean_str(row.get("Extraction_Rationale")),
            "regulation_links": _split_regulation_links(_clean_str(row.get("Regulation_Links"))),
            "document_name": document_name,
        }

        # Map to the Obligation field schema. Keep the legacy field names so
        # downstream code (agents, validators, exports, UI) continues to work.
        # The "abstract" doubles as the LLM's primary input text.
        abstract = procedure_step if (source_type == SOURCE_TYPE_PROCEDURE_STEP and procedure_step) else text

        # Synthesize subpart / section labels that the existing grouper expects.
        # For a Procedure_Step we group by parent policy ID; otherwise by source ID.
        group_subpart = parent_source_id or source_id
        group_section = procedure_id or source_id

        obligations.append(Obligation(
            citation=source_id,
            mandate_title=title,
            abstract=abstract,
            text=text,
            link=_clean_str(row.get("Link")),
            status=_clean_str(row.get("Status")),
            title_level_2=document_name,
            title_level_3=title,
            title_level_4=procedure_title,
            title_level_5=section,
            citation_level_2=group_subpart,
            citation_level_3=group_section,
            effective_date=_clean_str(row.get("Effective_Date")),
            applicability=_clean_str(row.get("Business_Unit")),
            source_type=source_type,
            source_id=source_id,
            parent_source_id=parent_source_id,
            requirement_type=requirement_type,
            source_metadata=source_metadata,
            source_confidence=source_confidence,
        ))

    return inventory_name, obligations


def group_policy_obligations(obligations: list[Obligation]) -> list[ObligationGroup]:
    """Group policy/procedure obligations into ``ObligationGroup`` batches.

    Grouping strategy: bucket by ``parent_source_id`` so that a Policy and
    all its Procedures classify together (gives the classifier full context).
    Top-level Policies (no parent) bucket by their own ``source_id``.
    """
    groups_dict: dict[str, list[Obligation]] = {}
    for ob in obligations:
        key = ob.parent_source_id or ob.source_id or ob.citation
        groups_dict.setdefault(key, []).append(ob)

    groups: list[ObligationGroup] = []
    for key, obs in sorted(groups_dict.items()):
        # Sort within group: parent first, then procedures
        obs_sorted = sorted(
            obs,
            key=lambda o: (o.parent_source_id is not None, o.citation),
        )
        first = obs_sorted[0]
        document_name = first.source_metadata.get("document_name", "") if first.source_metadata else ""
        group_id = re.sub(r"[^A-Za-z0-9_]+", "_", key)
        groups.append(ObligationGroup(
            group_id=group_id,
            subpart=document_name or first.source_type,
            section_citation=key,
            section_title=first.mandate_title,
            topic_title=document_name or first.mandate_title,
            obligation_count=len(obs_sorted),
            obligations=obs_sorted,
        ))

    return groups


def detect_source_inventory(path: str) -> bool:
    """Return True if the workbook contains a ``Source_Inventory`` sheet.

    Used by :func:`regrisk.graphs.classify_graph.ingest_node` to dispatch
    between the regulation parser and the policy parser. Safe and fast:
    only reads the sheet directory, not the data.
    """
    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
    except Exception:
        return False
    return SOURCE_INVENTORY_SHEET in xl.sheet_names
