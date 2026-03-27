"""
Minimal Streamlit UI — demonstrates the UI ↔ Backend contract.

Pattern:
1. **Graph invocation** — the UI builds an ``input_state`` dict and calls
   ``graph.invoke(input_state)``.  The returned dict contains the final
   report.  The UI never imports agent internals.
2. **Live progress** — a ``StreamlitEventListener`` subscribes to the
   graph's ``EventEmitter``.  Each ``PipelineEvent`` is mapped to an
   emoji + status line displayed in a live-updating container.
3. **Session state** — Streamlit's ``st.session_state`` stores config
   and results across reruns (Streamlit reruns the script on every
   widget interaction).

# CUSTOMIZE: Replace the layout, input widgets, and result rendering
# with your domain's UI.  Keep the three patterns above.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from skeleton.core.config import default_config_path, load_config
from skeleton.core.events import EventEmitter, EventType, PipelineEvent
from skeleton.export.markdown import export_to_markdown
from skeleton.graphs.research_graph import build_graph, set_emitter


# ---------------------------------------------------------------------------
# Event → UI mapping
# ---------------------------------------------------------------------------

_EVENT_EMOJI: dict[EventType, str] = {
    EventType.PIPELINE_STARTED: "🚀",
    EventType.PIPELINE_COMPLETED: "✅",
    EventType.PIPELINE_FAILED: "❌",
    EventType.STAGE_STARTED: "📋",
    EventType.STAGE_COMPLETED: "✔️",
    EventType.PROGRESS: "⏳",
    EventType.AGENT_STARTED: "🤖",
    EventType.AGENT_COMPLETED: "✔️",
    EventType.AGENT_FAILED: "❌",
    EventType.AGENT_RETRY: "🔄",
    EventType.VALIDATION_PASSED: "✅",
    EventType.VALIDATION_FAILED: "⚠️",
    EventType.TOOL_CALLED: "🔧",
    EventType.TOOL_COMPLETED: "🔧",
    EventType.ITEM_STARTED: "📝",
    EventType.ITEM_COMPLETED: "📝",
    EventType.WARNING: "⚠️",
}


# ---------------------------------------------------------------------------
# Streamlit event listener
# ---------------------------------------------------------------------------

class StreamlitEventListener:
    """Accumulates events and renders them in a Streamlit container.

    # CUSTOMIZE: Change the emoji mapping or add richer rendering
    # (progress bars, expandable sections, etc.).
    """

    def __init__(self, container: st.delta_generator.DeltaGenerator) -> None:
        self._container = container
        self._lines: list[str] = []

    def __call__(self, event: PipelineEvent) -> None:
        emoji = _EVENT_EMOJI.get(event.event_type, "•")
        line = f"{emoji} {event.message or event.stage}"
        self._lines.append(line)
        self._container.markdown("\n\n".join(self._lines))


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Multi-Agent Research Assistant",
        page_icon="🔬",
        layout="wide",
    )

    st.title("🔬 Multi-Agent Research Assistant")
    st.caption("A starter skeleton demonstrating LangGraph multi-agent patterns")

    # ---- Sidebar: configuration ----
    with st.sidebar:
        st.header("Configuration")

        config_path = st.text_input(
            "Config YAML path",
            value=str(default_config_path()),
            help="Path to your domain config YAML file.",
        )

        # Try to load config for display
        try:
            config = load_config(config_path)
        except Exception:
            config = None

        if config:
            st.success(f"Config loaded: **{config.name}**")
            st.markdown(f"- Max sub-questions: {config.max_sub_questions}")
            st.markdown(f"- Summary words: {config.summary_min_words}–{config.summary_max_words}")
            st.markdown(f"- Quality criteria: {len(config.quality_criteria)}")
        else:
            st.warning("Could not load config. Using defaults.")

        st.divider()
        st.markdown(
            "**LLM Status:** Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` "
            "env vars to enable LLM mode. Without them, the pipeline "
            "runs in deterministic-fallback mode."
        )

    # ---- Main area: input + run ----
    question = st.text_area(
        "Research Question",
        placeholder="e.g., What are the key differences between LangGraph and CrewAI for building multi-agent systems?",
        height=100,
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        run_btn = st.button("🔬 Run Research", type="primary", disabled=not question)

    # ---- Results area ----
    if run_btn and question:
        _run_pipeline(question, config_path)

    # Show previous results if they exist
    elif "final_report" in st.session_state:
        _render_results(st.session_state["final_report"])


def _run_pipeline(question: str, config_path: str) -> None:
    """Invoke the research graph and display live progress + results."""
    # Wire up the event listener
    progress_container = st.empty()
    emitter = EventEmitter()
    listener = StreamlitEventListener(progress_container)
    emitter.on(listener)
    set_emitter(emitter)

    # Build input state
    input_state = {
        "question": question,
        "config_path": config_path,
    }

    # Run the graph
    with st.spinner("Running research pipeline…"):
        graph = build_graph()
        result = graph.invoke(input_state)

    # Store results in session state
    st.session_state["final_report"] = result.get("final_report", {})

    # Clear progress and show results
    progress_container.empty()
    _render_results(st.session_state["final_report"])


def _render_results(report: dict) -> None:
    """Render the final research report."""
    if not report:
        return

    st.divider()
    st.header("Results")

    # ---- Summary ----
    summary = report.get("summary")
    if summary:
        st.subheader("Summary")
        st.write(summary.get("text", ""))
        wc = summary.get("word_count", 0)
        sources = summary.get("sources_used", [])
        st.caption(f"{wc} words • {len(sources)} sources cited")

    # ---- Review ----
    review = report.get("review")
    if review:
        passed = review.get("passed", True)
        if passed:
            st.success("Quality review: **PASSED**")
        else:
            st.warning("Quality review: **NEEDS REVISION**")
            for issue in review.get("issues", []):
                st.markdown(f"- {issue}")

    # ---- Findings ----
    findings = report.get("findings", [])
    if findings:
        st.subheader(f"Findings ({len(findings)})")
        for i, f in enumerate(findings, 1):
            with st.expander(f"Finding {i}: {f.get('sub_question', '')[:80]}"):
                st.write(f.get("answer", ""))
                sources = f.get("sources", [])
                if sources:
                    st.caption("Sources: " + ", ".join(sources))
                conf = f.get("confidence", 0)
                st.progress(conf, text=f"Confidence: {conf:.0%}")

    # ---- Export ----
    st.divider()
    md = export_to_markdown(
        question=report.get("question", ""),
        findings=findings,
        summary=summary,
        review=review,
    )
    st.download_button(
        "📥 Download as Markdown",
        data=md,
        file_name="research_report.md",
        mime="text/markdown",
    )


if __name__ == "__main__":
    main()
