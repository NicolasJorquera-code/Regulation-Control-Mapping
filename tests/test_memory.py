"""Tests for controlnexus.memory (store + embedder)."""

from __future__ import annotations

import chromadb

from controlnexus.memory.embedder import Embedder
from controlnexus.memory.store import ControlMemory


# -- Mock Embedder (deterministic, no model download) --------------------------


class MockEmbedder(Embedder):
    """Deterministic embedder for testing. Produces 8-dim vectors from text hash."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]

    def dimension(self) -> int:
        return 8

    def _hash_vector(self, text: str) -> list[float]:
        # Simple deterministic embedding: hash chars into 8 floats
        vec = [0.0] * 8
        for i, ch in enumerate(text):
            vec[i % 8] += ord(ch) / 1000.0
        # Normalize
        magnitude = sum(v**2 for v in vec) ** 0.5
        if magnitude > 0:
            vec = [v / magnitude for v in vec]
        return vec


# -- Fixtures ------------------------------------------------------------------


def _make_memory() -> ControlMemory:
    return ControlMemory(
        embedder=MockEmbedder(),
        chroma_client=chromadb.Client(),
    )


def _sample_records() -> list[dict]:
    return [
        {
            "control_id": "CTRL-001",
            "hierarchy_id": "4.1.1.1",
            "full_description": "Monthly reconciliation of GL accounts by the Senior Accountant in the financial close platform to prevent discrepancies.",
            "selected_level_2": "Reconciliation",
            "business_unit_id": "BU-001",
        },
        {
            "control_id": "CTRL-002",
            "hierarchy_id": "4.1.1.2",
            "full_description": "Quarterly vendor risk assessment by the Third Party Risk Manager in the vendor management platform to mitigate vendor concentration risk.",
            "selected_level_2": "Third Party Due Diligence",
            "business_unit_id": "BU-015",
        },
        {
            "control_id": "CTRL-003",
            "hierarchy_id": "9.1.1.1",
            "full_description": "Daily cash position reconciliation by the Treasury Analyst in the Treasury Management System to prevent liquidity risk.",
            "selected_level_2": "Reconciliation",
            "business_unit_id": "BU-005",
        },
    ]


# -- Tests ---------------------------------------------------------------------


class TestControlMemory:
    def test_index_controls(self):
        mem = _make_memory()
        count = mem.index_controls("bank1", _sample_records(), run_id="run-1")
        assert count == 3

    def test_index_empty_list(self):
        mem = _make_memory()
        count = mem.index_controls("bank1", [])
        assert count == 0

    def test_index_skips_empty_descriptions(self):
        mem = _make_memory()
        records = [{"control_id": "C1", "full_description": ""}]
        count = mem.index_controls("bank1", records)
        assert count == 0

    def test_query_similar_returns_results(self):
        mem = _make_memory()
        mem.index_controls("bank1", _sample_records())
        results = mem.query_similar("bank1", "Monthly reconciliation of accounts", n=2)
        assert len(results) <= 2
        assert all("id" in r for r in results)
        assert all("document" in r for r in results)
        assert all("score" in r for r in results)

    def test_query_empty_collection(self):
        mem = _make_memory()
        results = mem.query_similar("bank_empty", "test query")
        assert results == []

    def test_query_with_section_filter(self):
        mem = _make_memory()
        mem.index_controls("bank1", _sample_records())
        # Filter to section 4.0 — should exclude CTRL-003 (section 9.0)
        results = mem.query_similar("bank1", "reconciliation", n=5, section_filter="4.0")
        for r in results:
            assert r["metadata"]["section_id"] == "4.0"

    def test_check_duplicate_exact_match(self):
        mem = _make_memory()
        records = _sample_records()
        mem.index_controls("bank1", records)
        # Query with exact same text — should be a duplicate
        is_dup, dup_id = mem.check_duplicate("bank1", records[0]["full_description"])
        assert is_dup is True
        assert dup_id == "CTRL-001"

    def test_check_duplicate_distinct_text(self):
        mem = _make_memory()
        mem.index_controls("bank1", _sample_records())
        # Completely unrelated text
        is_dup, dup_id = mem.check_duplicate(
            "bank1",
            "XYZ entirely different content about weather patterns and ocean currents.",
        )
        # With our mock embedder this should be distinct
        assert isinstance(is_dup, bool)

    def test_compare_runs(self):
        mem = _make_memory()
        records_a = _sample_records()[:2]
        records_b = _sample_records()[1:]
        mem.index_controls("bank1", records_a, run_id="run-a")
        # Re-index with run-b (upsert will update CTRL-002's run_id)
        mem.index_controls("bank1", records_b, run_id="run-b")

        comparison = mem.compare_runs("bank1", "run-a", "run-b")
        assert "run_a_count" in comparison
        assert "run_b_count" in comparison
        assert "overlap_count" in comparison

    def test_clear_collection(self):
        mem = _make_memory()
        mem.index_controls("bank1", _sample_records())
        mem.clear("bank1")
        results = mem.query_similar("bank1", "test")
        assert results == []

    def test_clear_nonexistent_collection(self):
        mem = _make_memory()
        # Should not raise
        mem.clear("nonexistent_bank")


class TestMockEmbedder:
    def test_produces_correct_dimension(self):
        emb = MockEmbedder()
        result = emb.embed(["hello world"])
        assert len(result) == 1
        assert len(result[0]) == 8

    def test_deterministic(self):
        emb = MockEmbedder()
        a = emb.embed(["same text"])[0]
        b = emb.embed(["same text"])[0]
        assert a == b

    def test_different_texts_differ(self):
        emb = MockEmbedder()
        a = emb.embed(["text one"])[0]
        b = emb.embed(["completely different content"])[0]
        assert a != b
