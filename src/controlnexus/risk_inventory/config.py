"""Configuration loading for Risk Inventory Builder matrices and rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def default_risk_inventory_config_dir() -> Path:
    """Return the repo-level risk inventory config directory."""
    return resolve_project_root() / "config" / "risk_inventory"


def resolve_project_root() -> Path:
    """Resolve the active project root for source and installed execution."""
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "config" / "risk_inventory").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


class MatrixConfigLoader:
    """Load deterministic scoring and inventory configuration files."""

    def __init__(self, config_dir: Path | str | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir else default_risk_inventory_config_dir()

    def load(self, filename: str) -> dict[str, Any]:
        return read_yaml(self.config_dir / filename)

    def impact_scales(self) -> dict[str, Any]:
        return self.load("impact_scales.yaml")

    def likelihood_scale(self) -> dict[str, Any]:
        return self.load("likelihood_scale.yaml")

    def frequency_scale(self) -> dict[str, Any]:
        return self.load("frequency_scale.yaml")

    def inherent_matrix(self) -> dict[str, Any]:
        return self.load("inherent_risk_matrix.yaml")

    def residual_matrix(self) -> dict[str, Any]:
        return self.load("residual_risk_matrix.yaml")

    def control_effectiveness_criteria(self) -> dict[str, Any]:
        return self.load("control_effectiveness_criteria.yaml")

    def management_response_rules(self) -> dict[str, Any]:
        return self.load("management_response_rules.yaml")

    def taxonomy_crosswalk(self) -> dict[str, Any]:
        return self.load("risk_taxonomy_crosswalk.yaml")

    def root_cause_taxonomy(self) -> dict[str, Any]:
        return self.load("root_cause_taxonomy.yaml")

    def config_snapshot(self) -> dict[str, Any]:
        return {
            "impact_scales": self.impact_scales(),
            "frequency_scale": self.frequency_scale(),
            "likelihood_scale": self.likelihood_scale(),
            "inherent_risk_matrix": self.inherent_matrix(),
            "residual_risk_matrix": self.residual_matrix(),
            "control_effectiveness_criteria": self.control_effectiveness_criteria(),
            "management_response_rules": self.management_response_rules(),
            "risk_taxonomy_crosswalk": self.taxonomy_crosswalk(),
            "root_cause_taxonomy": self.root_cause_taxonomy(),
        }
