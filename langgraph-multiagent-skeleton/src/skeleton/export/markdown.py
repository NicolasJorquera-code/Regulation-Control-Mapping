"""
Markdown export — render research results as a readable report.

# CUSTOMIZE: Replace with your domain's export format (Excel, PDF, JSON, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_to_markdown(
    question: str,
    findings: list[dict[str, Any]],
    summary: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Render research results as Markdown text.

    If *output_path* is given, writes to that file and returns the path.
    Otherwise returns the Markdown string.

    # CUSTOMIZE: Change the template, add sections, or switch to a
    # different format entirely.
    """
    lines: list[str] = []

    lines.append(f"# Research Report\n")
    lines.append(f"**Question:** {question}\n")

    # --- Findings ---
    lines.append("## Findings\n")
    for i, f in enumerate(findings, 1):
        sq = f.get("sub_question", f"Sub-question {i}")
        answer = f.get("answer", "No answer")
        sources = f.get("sources", [])
        confidence = f.get("confidence", 0)

        lines.append(f"### {i}. {sq}\n")
        lines.append(f"{answer}\n")
        if sources:
            lines.append("**Sources:** " + ", ".join(sources) + "\n")
        lines.append(f"**Confidence:** {confidence:.0%}\n")

    # --- Summary ---
    if summary:
        lines.append("## Summary\n")
        lines.append(f"{summary.get('text', '')}\n")
        used = summary.get("sources_used", [])
        if used:
            lines.append("**Sources used:** " + ", ".join(used) + "\n")

    # --- Review ---
    if review:
        lines.append("## Quality Review\n")
        status = "PASSED" if review.get("passed") else "NEEDS REVISION"
        lines.append(f"**Status:** {status}\n")
        for issue in review.get("issues", []):
            lines.append(f"- Issue: {issue}")
        for suggestion in review.get("suggestions", []):
            lines.append(f"- Suggestion: {suggestion}")
        lines.append("")

    md = "\n".join(lines)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        return str(path)

    return md
