"""
Pipeline state models — the data that flows through the LangGraph graph.

Pattern:
- Each stage reads fields it needs from state and writes its result.
- Frozen Pydantic models (``Finding``, ``Summary``, ``ReviewResult``)
  ensure agents cannot mutate each other's outputs.
- ``to_export_dict()`` on the final record gives a projection suitable
  for file export.

This module re-exports the domain models so graph nodes import from one
place: ``from skeleton.core.state import Finding, Summary, ...``

# CUSTOMIZE: Replace with your domain's pipeline state types.
"""

from skeleton.core.models import (
    Finding,
    ResearchReport,
    ReviewResult,
    SubQuestion,
    Summary,
)

__all__ = [
    "Finding",
    "ResearchReport",
    "ReviewResult",
    "SubQuestion",
    "Summary",
]
