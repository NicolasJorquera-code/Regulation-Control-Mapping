"""Evaluation data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ControlScore(BaseModel):
    """Per-control evaluation scores."""

    control_id: str
    faithfulness: int = 0  # 0-4
    completeness: int = 0  # 0-6
    failures: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    """Aggregated evaluation report across all generated controls."""

    run_id: str = ""
    faithfulness_avg: float = 0.0
    completeness_avg: float = 0.0
    diversity_score: float = 0.0
    near_duplicate_count: int = 0
    gap_closure_delta: float = 0.0
    per_control_scores: list[ControlScore] = Field(default_factory=list)
    total_controls: int = 0
