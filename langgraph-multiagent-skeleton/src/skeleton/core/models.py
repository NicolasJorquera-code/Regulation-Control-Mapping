"""
Domain data models — Pydantic v2 types for every pipeline artifact.

Pattern:
- Each pipeline stage produces a *frozen* (immutable) result model.
- Frozen models act as tamper-proof receipts: once SpecAgent produces a
  ``Finding``, downstream agents can read it but never mutate it.
- Use ``model_dump()`` for serialization and ``to_export_dict()`` for
  selective column projection (e.g., export only a subset of fields).

# CUSTOMIZE: Replace these models with your domain's data types.
# Keep the frozen-result pattern — it prevents subtle bugs when agents
# accidentally overwrite each other's outputs in shared graph state.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Intermediate pipeline artifacts
# ---------------------------------------------------------------------------

class SubQuestion(BaseModel, frozen=True):
    """One decomposed sub-question from the PlannerAgent.

    # CUSTOMIZE: Add fields like ``priority``, ``topic_area``, ``estimated_difficulty``.
    """

    question: str
    topic: str = ""


class Finding(BaseModel, frozen=True):
    """Research finding for one sub-question (from ResearcherAgent).

    # CUSTOMIZE: Add fields like ``confidence``, ``source_urls``, ``raw_snippets``.
    """

    sub_question: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Summary(BaseModel, frozen=True):
    """Synthesized summary of all findings (from SynthesizerAgent).

    # CUSTOMIZE: Add fields like ``key_themes``, ``limitations``.
    """

    text: str
    word_count: int = 0
    sources_used: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel, frozen=True):
    """Quality review of the summary (from ReviewerAgent).

    # CUSTOMIZE: Change ``issues`` / ``suggestions`` to match your quality rubric.
    """

    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final output record
# ---------------------------------------------------------------------------

class ResearchReport(BaseModel):
    """Final assembled output — merges findings, summary, and review.

    This is the pipeline's "export-ready" artifact.  The ``to_export_dict``
    method returns only the fields you want in the exported file.

    # CUSTOMIZE: Replace with your domain's final record type.
    """

    question: str = ""
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    summary: Summary | None = None
    review: ReviewResult | None = None

    def to_export_dict(self) -> dict:
        """Return the subset of fields destined for the exported report."""
        return {
            "question": self.question,
            "summary": self.summary.text if self.summary else "",
            "sources": self.summary.sources_used if self.summary else [],
            "review_passed": self.review.passed if self.review else None,
            "review_issues": self.review.issues if self.review else [],
            "findings_count": len(self.findings),
        }
