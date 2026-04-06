"""
ClassifyState — TypedDict for Graph 1 (Ingest + Classify).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ClassifyState(TypedDict, total=False):
    # Input
    regulation_path: str
    apqc_path: str
    controls_dir: str
    config_path: str
    scope_config: dict[str, Any]

    # Init
    pipeline_config: dict[str, Any]
    risk_taxonomy: dict[str, Any]
    llm_enabled: bool

    # Ingest (deterministic)
    regulation_name: str
    total_obligations: int
    obligation_groups: list[dict[str, Any]]
    apqc_nodes: list[dict[str, Any]]
    controls: list[dict[str, Any]]

    # Classification loop
    classify_idx: int
    classified_obligations: Annotated[list[dict[str, Any]], operator.add]

    # Errors
    errors: Annotated[list[str], operator.add]
