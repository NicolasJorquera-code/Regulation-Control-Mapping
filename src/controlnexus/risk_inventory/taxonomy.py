"""Risk taxonomy crosswalk loading for Risk Inventory Builder."""

from __future__ import annotations

from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.models import RiskTaxonomyNode


def load_risk_inventory_taxonomy(config_dir: str | None = None) -> list[RiskTaxonomyNode]:
    """Load inventory-ready taxonomy nodes from the risk inventory crosswalk."""
    loader = MatrixConfigLoader(config_dir)
    payload = loader.taxonomy_crosswalk()
    return [RiskTaxonomyNode.model_validate(item) for item in payload.get("nodes", [])]


def find_applicable_nodes(
    process_text: str,
    nodes: list[RiskTaxonomyNode],
    *,
    include_all_if_none: bool = False,
) -> list[RiskTaxonomyNode]:
    """Select taxonomy nodes by configured process-pattern keywords."""
    text = process_text.lower()
    selected = []
    for node in nodes:
        patterns = [p.lower() for p in node.applicable_process_patterns]
        if any(pattern in text for pattern in patterns):
            selected.append(node)
    if not selected and include_all_if_none:
        return nodes
    return selected
