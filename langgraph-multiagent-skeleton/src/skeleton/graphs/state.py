"""
LangGraph state definition for the research pipeline.

Pattern: Use ``TypedDict`` (not Pydantic) for LangGraph state because
LangGraph operates on plain dicts internally.  For list fields that
multiple nodes may append to concurrently, use
``Annotated[list, operator.add]`` — this tells LangGraph to *merge*
(concatenate) partial updates instead of overwriting.

# CUSTOMIZE: Add / remove fields to match your pipeline stages.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    """Typed state flowing through the research graph.

    Fields are partitioned by pipeline stage:

    **Input** (set before graph invocation):
        - question: the user's research question
        - config_path: path to the domain config YAML

    **Loaded by init_node**:
        - domain_config: validated DomainConfig as a dict
        - llm_enabled: whether an LLM client was found

    **Set by plan_node**:
        - sub_questions: list of decomposed sub-question dicts

    **Loop tracking** (research_node iterates over sub_questions):
        - current_idx: index into sub_questions
        - current_sub_question: the sub-question being processed

    **Accumulated by research_node** (uses ``add`` reducer):
        - findings: list of Finding dicts (one per sub-question)

    **Set by synthesize_node**:
        - summary: the synthesized summary dict

    **Set by review_node**:
        - review: the quality review dict

    **Retry tracking**:
        - retry_count: how many times synthesis has been retried
        - review_feedback: concatenated issue list for retry prompt

    **Final output** (set by finalize_node):
        - final_report: the assembled ResearchReport dict
    """

    # Input
    question: str
    config_path: str

    # Init
    domain_config: dict[str, Any]
    llm_enabled: bool

    # Plan
    sub_questions: list[dict[str, Any]]

    # Research loop
    current_idx: int
    current_sub_question: dict[str, Any]

    # Accumulated findings — ``operator.add`` merges partial lists
    findings: Annotated[list[dict[str, Any]], operator.add]

    # Synthesis
    summary: dict[str, Any]

    # Review
    review: dict[str, Any]

    # Retry
    retry_count: int
    review_feedback: str

    # Final
    final_report: dict[str, Any]
