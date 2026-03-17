"""Evaluation harness: run all scorers and produce an EvalReport."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from controlnexus.core.models import SectionProfile
from controlnexus.core.state import FinalControlRecord
from controlnexus.evaluation.models import ControlScore, EvalReport
from controlnexus.evaluation.scorers import (
    score_completeness,
    score_diversity,
    score_faithfulness,
    score_gap_closure,
)
from controlnexus.memory.embedder import Embedder

logger = logging.getLogger(__name__)


def run_eval(
    generated_controls: list[FinalControlRecord],
    specs: list[dict[str, Any]],
    placement_config: dict[str, Any],
    section_profiles: dict[str, SectionProfile],
    original_controls: list[FinalControlRecord] | None = None,
    embedder: Embedder | None = None,
    run_id: str = "",
    output_dir: Path | None = None,
) -> EvalReport:
    """Run all 4 evaluation dimensions and build an EvalReport.

    Args:
        generated_controls: Controls to evaluate.
        specs: List of locked spec dicts (parallel to generated_controls).
        placement_config: Placement/taxonomy config from YAML.
        section_profiles: Section profiles for gap closure scoring.
        original_controls: Original controls (for gap closure delta).
        embedder: Optional embedder for diversity scoring.
        run_id: Run identifier for tracking.
        output_dir: If provided, writes {run_id}__eval.json here.

    Returns:
        EvalReport with all scores.
    """
    per_control: list[ControlScore] = []
    total_faith = 0
    total_comp = 0

    for i, record in enumerate(generated_controls):
        spec = specs[i] if i < len(specs) else {}

        faith_score, faith_failures = score_faithfulness(record, spec, placement_config)
        comp_score, comp_failures = score_completeness(record)

        total_faith += faith_score
        total_comp += comp_score

        per_control.append(ControlScore(
            control_id=record.control_id,
            faithfulness=faith_score,
            completeness=comp_score,
            failures=faith_failures + comp_failures,
        ))

    n = len(generated_controls) or 1
    faith_avg = round(total_faith / n, 2)
    comp_avg = round(total_comp / n, 2)

    diversity, near_dups = score_diversity(generated_controls, embedder)

    gap_delta = 0.0
    if original_controls:
        gap_delta = score_gap_closure(original_controls, generated_controls, section_profiles)

    report = EvalReport(
        run_id=run_id,
        faithfulness_avg=faith_avg,
        completeness_avg=comp_avg,
        diversity_score=diversity,
        near_duplicate_count=near_dups,
        gap_closure_delta=gap_delta,
        per_control_scores=per_control,
        total_controls=len(generated_controls),
    )

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{run_id}__eval.json" if run_id else "eval.json"
        out_path = output_dir / filename
        out_path.write_text(json.dumps(report.model_dump(), indent=2))
        logger.info("Eval report written to %s", out_path)

    return report
