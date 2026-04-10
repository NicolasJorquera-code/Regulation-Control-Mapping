"""Integration test — run the full research graph in deterministic mode."""

from __future__ import annotations

from pathlib import Path

from skeleton.graphs.research_graph import build_graph, reset_caches


def test_full_graph_deterministic():
    """The graph should complete end-to-end with no LLM client.

    Verifies:
    - All nodes execute without error
    - State contains sub_questions, findings, summary, review, final_report
    - final_report has the expected structure
    """
    reset_caches()

    config_path = str(Path(__file__).resolve().parents[1] / "config" / "default.yaml")

    graph = build_graph()
    result = graph.invoke({
        "question": "What are the benefits of multi-agent systems?",
        "config_path": config_path,
    })

    # --- Structure checks ---
    assert "sub_questions" in result
    assert len(result["sub_questions"]) > 0

    assert "findings" in result
    assert len(result["findings"]) > 0

    assert "summary" in result
    assert "text" in result["summary"]

    assert "review" in result

    assert "final_report" in result
    report = result["final_report"]
    assert report["question"] == "What are the benefits of multi-agent systems?"
    assert len(report["findings"]) > 0
    assert report["summary"] is not None

    reset_caches()


def test_graph_compiles():
    """The graph should compile without error."""
    graph = build_graph()
    assert graph is not None
