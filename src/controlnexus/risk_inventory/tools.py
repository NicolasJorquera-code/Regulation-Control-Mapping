"""Read-only tools for Risk Inventory Builder agents."""

from __future__ import annotations

from typing import Any, Callable

from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.models import RiskInventoryWorkspace


def knowledge_base_lookup(workspace: RiskInventoryWorkspace, entity_type: str, entity_id: str = "") -> dict[str, Any]:
    """Look up configured knowledge-base entities by type and optional id."""
    entity_type = entity_type.lower().strip()
    if entity_type in {"business_unit", "business_units", "bu"}:
        rows = [item.model_dump() for item in workspace.business_units]
        return _filter_rows(rows, ("bu_id", "bu_name"), entity_id)
    if entity_type in {"process", "processes", "procedure", "procedures"}:
        rows = [item.model_dump() for item in workspace.processes]
        return _filter_rows(rows, ("process_id", "process_name"), entity_id)
    if entity_type in {"control", "controls", "control_inventory"}:
        rows = [item.model_dump() for item in workspace.control_inventory]
        return _filter_rows(rows, ("control_id", "control_name"), entity_id)
    if entity_type in {"issue", "issues"}:
        rows = [item.model_dump() for item in workspace.issues]
        return _filter_rows(rows, ("issue_id", "title"), entity_id)
    if entity_type in {"evidence", "artifact", "evidence_artifacts"}:
        rows = [item.model_dump() for item in workspace.evidence_artifacts]
        return _filter_rows(rows, ("evidence_id", "name"), entity_id)
    return {"records": [], "error": f"Unknown knowledge-base entity type: {entity_type}"}


def risk_taxonomy_lookup(workspace: RiskInventoryWorkspace, taxonomy_id: str = "", query: str = "") -> dict[str, Any]:
    rows = [item.model_dump() for item in workspace.risk_taxonomy_l2]
    if taxonomy_id:
        return _filter_rows(rows, ("id", "level_2_category"), taxonomy_id)
    return _query_rows(rows, query, ("level_1_category", "level_2_category", "definition"))


def control_taxonomy_lookup(workspace: RiskInventoryWorkspace, control_type: str = "") -> dict[str, Any]:
    rows = [item.model_dump() for item in workspace.control_taxonomy]
    return _query_rows(rows, control_type, ("code", "name", "family", "description"))


def control_inventory_search(
    workspace: RiskInventoryWorkspace,
    query: str = "",
    process_id: str = "",
    taxonomy_node_id: str = "",
) -> dict[str, Any]:
    rows = []
    for control in workspace.control_inventory:
        include = True
        if process_id and process_id not in control.process_ids:
            include = False
        if taxonomy_node_id and taxonomy_node_id not in control.taxonomy_node_ids:
            include = False
        if include:
            rows.append(control.model_dump())
    return _query_rows(rows, query, ("control_id", "control_name", "control_type", "description"))


def evidence_lookup(workspace: RiskInventoryWorkspace, evidence_id: str = "", control_id: str = "") -> dict[str, Any]:
    rows = [item.model_dump() for item in workspace.evidence_artifacts]
    if evidence_id:
        return _filter_rows(rows, ("evidence_id", "name"), evidence_id)
    if control_id:
        return {"records": [row for row in rows if row.get("control_id") == control_id]}
    return {"records": rows}


def obligation_lookup(
    workspace: RiskInventoryWorkspace,
    framework: str = "",
    process_id: str = "",
    taxonomy_node_id: str = "",
) -> dict[str, Any]:
    rows = []
    for obligation in workspace.regulatory_obligations:
        row = obligation.model_dump()
        if framework and framework.lower() not in obligation.framework.lower():
            continue
        if process_id and process_id not in obligation.process_ids:
            continue
        if taxonomy_node_id and taxonomy_node_id not in obligation.risk_taxonomy_ids:
            continue
        rows.append(row)
    return {"records": rows}


def kri_lookup(workspace: RiskInventoryWorkspace, taxonomy_node_id: str = "", kri_id: str = "") -> dict[str, Any]:
    rows = [item.model_dump() for item in workspace.kri_library]
    if kri_id:
        return _filter_rows(rows, ("kri_id", "kri_name"), kri_id)
    if taxonomy_node_id:
        return {"records": [row for row in rows if row.get("risk_taxonomy_id") == taxonomy_node_id]}
    return {"records": rows}


def scoring_matrix_lookup(matrix: str = "") -> dict[str, Any]:
    loader = MatrixConfigLoader()
    matrix = matrix.lower().strip()
    if matrix in {"impact", "impact_scales"}:
        return loader.impact_scales()
    if matrix in {"likelihood", "likelihood_scale"}:
        return loader.likelihood_scale()
    if matrix in {"inherent", "inherent_risk"}:
        return loader.inherent_matrix()
    if matrix in {"residual", "residual_risk"}:
        return loader.residual_matrix()
    if matrix in {"management_response", "response"}:
        return loader.management_response_rules()
    return {
        "available": [
            "impact",
            "likelihood",
            "inherent",
            "residual",
            "management_response",
        ]
    }


def build_risk_inventory_tool_executor(
    workspace: RiskInventoryWorkspace,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return a tool executor closure suitable for agent tool loops."""
    dispatch: dict[str, Callable[..., dict[str, Any]]] = {
        "knowledge_base_lookup": lambda **kw: knowledge_base_lookup(workspace, **kw),
        "risk_taxonomy_lookup": lambda **kw: risk_taxonomy_lookup(workspace, **kw),
        "control_taxonomy_lookup": lambda **kw: control_taxonomy_lookup(workspace, **kw),
        "control_inventory_search": lambda **kw: control_inventory_search(workspace, **kw),
        "evidence_lookup": lambda **kw: evidence_lookup(workspace, **kw),
        "obligation_lookup": lambda **kw: obligation_lookup(workspace, **kw),
        "kri_lookup": lambda **kw: kri_lookup(workspace, **kw),
        "scoring_matrix_lookup": lambda **kw: scoring_matrix_lookup(**kw),
    }

    def executor(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        func = dispatch.get(tool_name)
        if func is None:
            return {"error": f"Unknown risk inventory tool: {tool_name}"}
        try:
            return func(**arguments)
        except Exception as exc:  # noqa: BLE001 - tool errors are returned to agents
            return {"error": str(exc)}

    return executor


def _filter_rows(rows: list[dict[str, Any]], keys: tuple[str, ...], value: str) -> dict[str, Any]:
    if not value:
        return {"records": rows}
    lowered = value.lower()
    return {
        "records": [
            row for row in rows if any(lowered == str(row.get(key, "")).lower() for key in keys)
        ]
    }


def _query_rows(rows: list[dict[str, Any]], query: str, keys: tuple[str, ...]) -> dict[str, Any]:
    if not query:
        return {"records": rows}
    lowered = query.lower()
    return {
        "records": [
            row
            for row in rows
            if any(lowered in str(row.get(key, "")).lower() for key in keys)
        ]
    }
