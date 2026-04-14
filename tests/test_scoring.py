"""Tests for scoring helpers — derive_inherent_rating and deduplicate_risks."""

from __future__ import annotations

from regrisk.core.scoring import deduplicate_risks, derive_inherent_rating


def _risk(
    risk_id: str,
    citation: str,
    category: str,
    impact: int = 2,
    frequency: int = 2,
    sub_category: str = "Sub",
) -> dict:
    return {
        "risk_id": risk_id,
        "source_citation": citation,
        "risk_category": category,
        "sub_risk_category": sub_category,
        "impact_rating": impact,
        "frequency_rating": frequency,
    }


class TestDeriveInherentRating:
    def test_critical(self):
        assert derive_inherent_rating(4, 3) == "Critical"

    def test_high(self):
        assert derive_inherent_rating(4, 2) == "High"

    def test_medium(self):
        assert derive_inherent_rating(2, 2) == "Medium"

    def test_low(self):
        assert derive_inherent_rating(1, 1) == "Low"


class TestDeduplicateRisks:
    def test_no_duplicates_unchanged(self):
        risks = [
            _risk("RISK-001", "CFR-1", "Compliance Risk", 3, 4),
            _risk("RISK-002", "CFR-1", "Operational Risk", 2, 3),
            _risk("RISK-003", "CFR-2", "Compliance Risk", 2, 2),
        ]
        result = deduplicate_risks(risks)
        assert len(result) == 3
        assert [r["risk_id"] for r in result] == ["RISK-001", "RISK-002", "RISK-003"]

    def test_same_category_keeps_highest_score(self):
        risks = [
            _risk("RISK-001", "CFR-1", "Compliance Risk", impact=2, frequency=2),  # score 4
            _risk("RISK-002", "CFR-1", "Compliance Risk", impact=3, frequency=4),  # score 12 -> kept
        ]
        result = deduplicate_risks(risks)
        assert len(result) == 1
        assert result[0]["impact_rating"] == 3
        assert result[0]["frequency_rating"] == 4
        assert result[0]["risk_id"] == "RISK-001"  # re-sequenced

    def test_different_categories_kept(self):
        risks = [
            _risk("RISK-001", "CFR-1", "Compliance Risk", 3, 3),
            _risk("RISK-002", "CFR-1", "Operational Risk", 3, 3),
        ]
        result = deduplicate_risks(risks)
        assert len(result) == 2

    def test_tiebreak_on_higher_impact(self):
        risks = [
            _risk("RISK-001", "CFR-1", "Compliance Risk", impact=2, frequency=4),  # score 8
            _risk("RISK-002", "CFR-1", "Compliance Risk", impact=4, frequency=2),  # score 8, higher impact
        ]
        result = deduplicate_risks(risks)
        assert len(result) == 1
        assert result[0]["impact_rating"] == 4

    def test_ids_resequenced(self):
        risks = [
            _risk("RISK-005", "CFR-1", "Compliance Risk", 3, 4),
            _risk("RISK-010", "CFR-1", "Compliance Risk", 2, 2),  # lower, removed
            _risk("RISK-015", "CFR-2", "Operational Risk", 2, 2),
        ]
        result = deduplicate_risks(risks)
        assert len(result) == 2
        assert result[0]["risk_id"] == "RISK-001"
        assert result[1]["risk_id"] == "RISK-002"

    def test_custom_prefix(self):
        risks = [_risk("R-001", "CFR-1", "Compliance Risk")]
        result = deduplicate_risks(risks, id_prefix="R")
        assert result[0]["risk_id"] == "R-001"

    def test_empty_input(self):
        assert deduplicate_risks([]) == []

    def test_preserves_order_of_winners(self):
        risks = [
            _risk("RISK-001", "CFR-1", "A", 1, 1),
            _risk("RISK-002", "CFR-2", "B", 2, 2),
            _risk("RISK-003", "CFR-1", "A", 4, 4),  # replaces RISK-001
            _risk("RISK-004", "CFR-3", "C", 1, 1),
        ]
        result = deduplicate_risks(risks)
        # Winner for CFR-1/A is RISK-003 but it takes the position of RISK-001 (idx 0)
        assert len(result) == 3
        assert result[0]["source_citation"] == "CFR-1"
        assert result[0]["impact_rating"] == 4
        assert result[1]["source_citation"] == "CFR-2"
        assert result[2]["source_citation"] == "CFR-3"
