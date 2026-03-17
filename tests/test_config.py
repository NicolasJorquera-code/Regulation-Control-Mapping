"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.core.config import (
    ConfigValidationError,
    load_all_section_profiles,
    load_placement_methods,
    load_section_profile,
    load_section_profiles,
    load_standards,
    load_taxonomy,
    load_taxonomy_catalog,
)
from controlnexus.core.models import SectionProfile, TaxonomyItem


class TestLoadTaxonomyCatalog:
    def test_loads_control_types(self, taxonomy_path: Path):
        catalog = load_taxonomy_catalog(taxonomy_path)
        assert len(catalog.control_types) >= 24
        names = {ct.control_type for ct in catalog.control_types}
        assert "Reconciliation" in names
        assert "Authorization" in names

    def test_loads_business_units(self, taxonomy_path: Path):
        catalog = load_taxonomy_catalog(taxonomy_path)
        assert len(catalog.business_units) >= 17
        bu_ids = {bu.business_unit_id for bu in catalog.business_units}
        assert "BU-001" in bu_ids

    def test_cross_validation_passes(self, taxonomy_path: Path):
        catalog = load_taxonomy_catalog(taxonomy_path)
        known_types = {ct.control_type for ct in catalog.control_types}
        for bu in catalog.business_units:
            for ct in bu.key_control_types:
                assert ct in known_types, f"BU {bu.business_unit_id} references unknown type: {ct}"


class TestLoadTaxonomy:
    def test_returns_list_of_items(self, taxonomy_path: Path):
        items = load_taxonomy(taxonomy_path)
        assert isinstance(items, list)
        assert all(isinstance(item, TaxonomyItem) for item in items)


class TestLoadSectionProfile:
    def test_loads_section_4(self, config_dir: Path):
        profile = load_section_profile(config_dir / "sections" / "section_4.yaml")
        assert profile.section_id == "4.0"
        assert profile.domain is not None
        assert profile.risk_profile.multiplier > 0

    def test_affinity_has_types(self, section_4_profile: SectionProfile):
        assert len(section_4_profile.affinity.HIGH) > 0

    def test_registry_has_roles(self, section_4_profile: SectionProfile):
        assert len(section_4_profile.registry.roles) > 0

    def test_registry_has_systems(self, section_4_profile: SectionProfile):
        assert len(section_4_profile.registry.systems) > 0

    def test_has_exemplars(self, section_4_profile: SectionProfile):
        assert len(section_4_profile.exemplars) >= 1


class TestLoadSectionProfiles:
    def test_loads_multiple(self, config_dir: Path):
        profiles = load_section_profiles(config_dir, ["4", "9"])
        assert "4" in profiles
        assert "9" in profiles
        assert isinstance(profiles["4"], SectionProfile)

    def test_missing_section_raises(self, config_dir: Path):
        with pytest.raises(ConfigValidationError):
            load_section_profiles(config_dir, ["99"])


class TestLoadAllSectionProfiles:
    def test_loads_all_13(self, config_dir: Path):
        profiles = load_all_section_profiles(config_dir)
        assert len(profiles) == 13
        for i in range(1, 14):
            assert str(i) in profiles


class TestLoadStandards:
    def test_has_five_w(self, config_dir: Path):
        standards = load_standards(config_dir / "standards.yaml")
        assert "five_w" in standards

    def test_has_phrase_bank(self, config_dir: Path):
        standards = load_standards(config_dir / "standards.yaml")
        assert "phrase_bank" in standards

    def test_has_quality_ratings(self, config_dir: Path):
        standards = load_standards(config_dir / "standards.yaml")
        assert "quality_ratings" in standards


class TestLoadPlacementMethods:
    def test_has_placements(self, config_dir: Path):
        pm = load_placement_methods(config_dir / "placement_methods.yaml")
        assert "placements" in pm

    def test_has_methods(self, config_dir: Path):
        pm = load_placement_methods(config_dir / "placement_methods.yaml")
        assert "methods" in pm

    def test_has_taxonomy(self, config_dir: Path):
        pm = load_placement_methods(config_dir / "placement_methods.yaml")
        assert "control_taxonomy" in pm


class TestConfigValidationError:
    def test_is_value_error(self):
        err = ConfigValidationError("test")
        assert isinstance(err, ValueError)
