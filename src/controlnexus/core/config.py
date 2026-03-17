"""Configuration loading for ControlNexus.

Loads and validates YAML configuration files: taxonomy, section profiles,
standards, placement methods, and run configs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from controlnexus.core.models import RunConfig, SectionProfile, TaxonomyCatalog, TaxonomyItem

logger = logging.getLogger(__name__)


class ConfigValidationError(ValueError):
    """Raised when cross-file config validation fails."""


def _read_yaml(path: Path) -> dict[str, Any]:
    logger.debug("Reading YAML file: %s", path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigValidationError(f"YAML root must be a mapping in {path}")
    return data


def load_taxonomy(path: Path) -> list[TaxonomyItem]:
    """Load control type definitions from a taxonomy YAML file."""
    return load_taxonomy_catalog(path).control_types


def load_taxonomy_catalog(path: Path) -> TaxonomyCatalog:
    """Load the full taxonomy catalog including control types and business units.

    Validates that all business-unit key_control_types reference known types.
    """
    payload = _read_yaml(path)
    raw_items = payload.get("control_types", [])
    if not isinstance(raw_items, list):
        raise ConfigValidationError(f"control_types must be a list in {path}")
    control_types = [TaxonomyItem(**item) for item in raw_items]

    raw_business_units = payload.get("business_units", [])
    if raw_business_units is None:
        raw_business_units = []
    if not isinstance(raw_business_units, list):
        raise ConfigValidationError(f"business_units must be a list in {path}")

    catalog = TaxonomyCatalog(control_types=control_types, business_units=raw_business_units)
    known_types = {item.control_type for item in catalog.control_types}
    invalid_refs: list[str] = []
    for bu in catalog.business_units:
        for control_type in bu.key_control_types:
            if control_type not in known_types:
                invalid_refs.append(f"{bu.business_unit_id}: {control_type}")

    if invalid_refs:
        joined = ", ".join(sorted(set(invalid_refs)))
        raise ConfigValidationError(
            "business_units references unknown control types: " + joined
        )
    return catalog


def load_section_profile(path: Path) -> SectionProfile:
    """Load a single section profile from a YAML file."""
    return SectionProfile(**_read_yaml(path))


def load_section_profiles(config_dir: Path, section_ids: list[str]) -> dict[str, SectionProfile]:
    """Load section profiles for the given section IDs."""
    profiles: dict[str, SectionProfile] = {}
    for section_id in section_ids:
        section_path = config_dir / "sections" / f"section_{section_id}.yaml"
        if not section_path.exists():
            raise ConfigValidationError(
                f"Missing section profile for section {section_id}: {section_path}"
            )
        profiles[section_id] = load_section_profile(section_path)
    logger.info("Loaded %d section profiles: %s", len(profiles), section_ids)
    return profiles


def load_all_section_profiles(config_dir: Path) -> dict[str, SectionProfile]:
    """Load all 13 section profiles from the config directory."""
    section_ids = [str(i) for i in range(1, 14)]
    return load_section_profiles(config_dir, section_ids)


def load_run_config(path: str | Path) -> RunConfig:
    """Load a run configuration from a YAML file."""
    run_path = Path(path)
    logger.info("Loading run config: %s", run_path)
    return RunConfig(**_read_yaml(run_path))


def load_standards(path: Path) -> dict[str, Any]:
    """Load the standards configuration (5W standards, phrase bank, quality ratings)."""
    return _read_yaml(path)


def load_placement_methods(path: Path) -> dict[str, Any]:
    """Load placement and method definitions along with taxonomy constraints."""
    return _read_yaml(path)


def default_paths(project_root: Path) -> tuple[Path, Path]:
    """Return default config directory and taxonomy path for a project root."""
    config_dir = project_root / "config"
    taxonomy_path = config_dir / "taxonomy.yaml"
    return config_dir, taxonomy_path
