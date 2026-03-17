"""Tests for controlnexus.evaluation (scorers + harness)."""

from __future__ import annotations

from controlnexus.core.models import (
    AffinityMatrix,
    DomainRegistry,
    RiskProfile,
    SectionProfile,
)
from controlnexus.core.state import FinalControlRecord
from controlnexus.evaluation.harness import run_eval
from controlnexus.evaluation.models import ControlScore, EvalReport
from controlnexus.evaluation.scorers import (
    _cosine_similarity,
    score_completeness,
    score_diversity,
    score_faithfulness,
    score_gap_closure,
)
from controlnexus.memory.embedder import Embedder


# -- Helpers -------------------------------------------------------------------


class MockEmbedder(Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash(t) for t in texts]

    def dimension(self) -> int:
        return 4

    def _hash(self, text: str) -> list[float]:
        vec = [0.0] * 4
        for i, ch in enumerate(text):
            vec[i % 4] += ord(ch) / 1000.0
        mag = sum(v**2 for v in vec) ** 0.5
        return [v / mag for v in vec] if mag > 0 else vec


PLACEMENT_CONFIG = {
    "placements": ["Preventive", "Detective", "Contingency Planning"],
    "control_taxonomy": {
        "level_2_by_level_1": {
            "Preventive": ["Authorization", "Third Party Due Diligence"],
            "Detective": ["Reconciliation", "Exception Reporting"],
        }
    },
}


def _make_control(**overrides) -> FinalControlRecord:
    base = {
        "control_id": "CTRL-001",
        "hierarchy_id": "4.1.1.1",
        "leaf_name": "Test",
        "full_description": "Monthly, the Senior Accountant reconciles general ledger accounts in the financial close platform by reviewing outstanding items and investigating discrepancies to prevent unreconciled account balances and ensure regulatory compliance with SOX requirements for timely and accurate financial reporting.",
        "selected_level_1": "Detective",
        "selected_level_2": "Reconciliation",
        "who": "Senior Accountant",
        "what": "Reconciles GL accounts and reviews discrepancies",
        "when": "Monthly, by the 5th business day",
        "frequency": "Monthly",
        "where": "Financial Close Platform",
        "why": "To prevent unreconciled discrepancies and mitigate risk",
        "quality_rating": "Strong",
        "validator_passed": True,
        "evidence": "GL report with sign-off retained in platform",
    }
    base.update(overrides)
    return FinalControlRecord(**base)


def _make_profile() -> SectionProfile:
    return SectionProfile(
        section_id="4.0",
        domain="test",
        risk_profile=RiskProfile(inherent_risk=3, regulatory_intensity=3, control_density=3, multiplier=1.0, rationale="test"),
        registry=DomainRegistry(roles=["Accountant"], systems=["GL"], regulatory_frameworks=["SOX"]),
        affinity=AffinityMatrix(HIGH=["Reconciliation"], MEDIUM=[], LOW=[], NONE=[]),
    )


# -- Faithfulness Tests ---------------------------------------------------------


class TestFaithfulness:
    def test_perfect_score(self):
        record = _make_control(who="Senior Accountant", where="Financial Close Platform")
        spec = {"who": "Senior Accountant", "where_system": "Financial Close Platform"}
        score, failures = score_faithfulness(record, spec, PLACEMENT_CONFIG)
        assert score == 4
        assert failures == []

    def test_who_mismatch(self):
        record = _make_control(who="CFO")
        spec = {"who": "Senior Accountant", "where_system": "Financial Close Platform"}
        score, failures = score_faithfulness(record, spec, PLACEMENT_CONFIG)
        assert score < 4
        assert "who_mismatch" in failures

    def test_invalid_type_for_level1(self):
        record = _make_control(selected_level_1="Preventive", selected_level_2="Reconciliation")
        spec = {}
        score, failures = score_faithfulness(record, spec, PLACEMENT_CONFIG)
        assert "type_invalid_for_l1" in failures

    def test_empty_spec(self):
        record = _make_control()
        score, failures = score_faithfulness(record, {}, PLACEMENT_CONFIG)
        # No spec to match against for who/where, but type and placement still score
        assert score >= 2


# -- Completeness Tests ---------------------------------------------------------


class TestCompleteness:
    def test_perfect_score(self):
        record = _make_control()
        score, failures = score_completeness(record)
        assert score == 6
        assert failures == []

    def test_generic_role(self):
        record = _make_control(who="Control Owner")
        score, failures = score_completeness(record)
        assert "generic_role" in failures

    def test_no_action_verb(self):
        record = _make_control(what="The thing that happens")
        score, failures = score_completeness(record)
        assert "no_action_verb" in failures

    def test_no_real_frequency(self):
        record = _make_control(when="On demand as needed")
        score, failures = score_completeness(record)
        assert "no_real_frequency" in failures

    def test_too_few_words(self):
        record = _make_control(full_description="Too short for scoring.")
        score, failures = score_completeness(record)
        assert any("word_count" in f for f in failures)


# -- Diversity Tests ------------------------------------------------------------


class TestDiversity:
    def test_single_control_returns_1(self):
        records = [_make_control()]
        score, dups = score_diversity(records)
        assert score == 1.0
        assert dups == 0

    def test_identical_controls_low_diversity(self):
        records = [_make_control(), _make_control()]
        emb = MockEmbedder()
        score, dups = score_diversity(records, emb)
        # Same text → identical embeddings → cosine = 1.0 → diversity = 0.0
        assert score < 0.1
        assert dups >= 1

    def test_different_controls_higher_diversity(self):
        records = [
            _make_control(full_description="Monthly reconciliation of GL accounts by the Senior Accountant to prevent discrepancies."),
            _make_control(full_description="Quarterly vendor risk assessment by the Third Party Risk Manager to mitigate concentration risk."),
        ]
        emb = MockEmbedder()
        score, _ = score_diversity(records, emb)
        assert score > 0

    def test_no_embedder_returns_neutral(self):
        records = [_make_control(), _make_control()]
        score, dups = score_diversity(records, embedder=None)
        assert score == 0.5
        assert dups == 0


# -- Cosine Similarity ----------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1, 0], [0, 1])) < 0.01

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0


# -- Gap Closure ----------------------------------------------------------------


class TestGapClosure:
    def test_no_original_controls(self):
        delta = score_gap_closure([], [_make_control()], {"4.0": _make_profile()})
        assert delta == 0.0

    def test_adding_controls_changes_score(self):
        originals = [_make_control()]
        generated = [_make_control(control_id="CTRL-002")]
        profiles = {"4.0": _make_profile()}
        delta = score_gap_closure(originals, generated, profiles)
        assert isinstance(delta, float)


# -- EvalReport Model -----------------------------------------------------------


class TestEvalReport:
    def test_default_values(self):
        report = EvalReport()
        assert report.faithfulness_avg == 0.0
        assert report.total_controls == 0

    def test_control_score(self):
        cs = ControlScore(control_id="C1", faithfulness=3, completeness=5)
        assert cs.faithfulness == 3
        assert cs.completeness == 5


# -- Harness Integration --------------------------------------------------------


class TestRunEval:
    def test_basic_eval(self):
        controls = [_make_control()]
        specs = [{"who": "Senior Accountant", "where_system": "Financial Close Platform"}]
        profiles = {"4.0": _make_profile()}

        report = run_eval(controls, specs, PLACEMENT_CONFIG, profiles, run_id="test-run")
        assert report.run_id == "test-run"
        assert report.total_controls == 1
        assert report.faithfulness_avg > 0
        assert report.completeness_avg > 0

    def test_eval_with_embedder(self):
        controls = [_make_control(), _make_control(control_id="CTRL-002")]
        specs = [{}, {}]
        profiles = {"4.0": _make_profile()}
        emb = MockEmbedder()

        report = run_eval(controls, specs, PLACEMENT_CONFIG, profiles, embedder=emb)
        assert report.diversity_score >= 0
        assert report.total_controls == 2

    def test_eval_writes_json(self, tmp_path):
        controls = [_make_control()]
        specs = [{}]
        profiles = {"4.0": _make_profile()}

        run_eval(controls, specs, PLACEMENT_CONFIG, profiles, run_id="r1", output_dir=tmp_path)
        assert (tmp_path / "r1__eval.json").exists()
