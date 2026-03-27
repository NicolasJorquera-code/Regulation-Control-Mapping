"""
Research graph — a 7-node LangGraph state machine.

Topology::

    START ─→ init ─→ plan ─→ research ─┐
                                        │ (loop: has_more?)
                                 ┌──────┘
                                 ▼
                              research ──→ synthesize ──→ review ──→ finalize ─→ END
                                               ▲                       │
                                               └── (retry if failed) ──┘

Pattern highlights:
1. **Conditional routing** — ``has_more_questions`` and ``should_retry``
   are edge functions that return the name of the next node.
2. **Annotated[list, add] reducer** — ``findings`` accumulates across
   loop iterations without overwriting.
3. **Module-level caches** — LLM client + agent instances are built once
   and reused across all node invocations (avoids TCP reconnect per node).
4. **Event emission** — every node emits events via the module-level
   ``EventEmitter`` so the UI can display live progress.
5. **Deterministic fallback** — when no LLM is available, every agent
   returns a deterministic result, making the graph fully testable
   without API keys.

# CUSTOMIZE: Replace nodes with your domain's pipeline stages.
# Keep the patterns (caching, events, conditional routing, reducers).
"""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.graph import END, START, StateGraph

from skeleton.agents.base import AgentContext
from skeleton.agents.planner import PlannerAgent
from skeleton.agents.researcher import ResearcherAgent
from skeleton.agents.reviewer import ReviewerAgent
from skeleton.agents.synthesizer import SynthesizerAgent
from skeleton.core.config import DomainConfig, default_config_path, load_config
from skeleton.core.events import EventEmitter, EventType, PipelineEvent
from skeleton.core.transport import build_client_from_env
from skeleton.graphs.state import ResearchState
from skeleton.tools.implementations import build_tool_executor
from skeleton.validation.validator import validate_summary


# ---------------------------------------------------------------------------
# Module-level singletons (reused across node invocations)
# ---------------------------------------------------------------------------

_emitter: EventEmitter = EventEmitter()
_llm_client_cache: Any = None  # AsyncTransportClient | None — set once
_agent_cache: dict[str, Any] = {}
_event_loop: asyncio.AbstractEventLoop | None = None

# Max retries for the review→re-synthesize loop
MAX_REVIEW_RETRIES = 2  # CUSTOMIZE: adjust retry budget


def set_emitter(emitter: EventEmitter) -> None:
    """Replace the module-level emitter (called by UI before graph run)."""
    global _emitter
    _emitter = emitter


def get_emitter() -> EventEmitter:
    return _emitter


def _emit(event_type: EventType, message: str = "", **data: Any) -> None:
    _emitter.emit(PipelineEvent(event_type=event_type, message=message, data=data))


def _get_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop for async agent calls."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _get_agent(name: str, context: AgentContext) -> Any:
    """Get or create a cached agent instance."""
    if name not in _agent_cache:
        agents = {
            "planner": PlannerAgent,
            "researcher": ResearcherAgent,
            "synthesizer": SynthesizerAgent,
            "reviewer": ReviewerAgent,
        }
        cls = agents[name]
        _agent_cache[name] = cls(context)
    return _agent_cache[name]


def _build_context() -> AgentContext:
    """Build an AgentContext, caching the LLM client."""
    global _llm_client_cache
    if _llm_client_cache is None:
        _llm_client_cache = build_client_from_env()  # may be None (no LLM)
    model = "gpt-4o"
    if _llm_client_cache:
        model = _llm_client_cache.model
    return AgentContext(client=_llm_client_cache, model=model)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def init_node(state: ResearchState) -> dict[str, Any]:
    """Load config, detect LLM availability, emit pipeline-started event."""
    _emit(EventType.PIPELINE_STARTED, "Pipeline started")

    config_path = state.get("config_path") or str(default_config_path())
    config = load_config(config_path)
    context = _build_context()

    _emit(EventType.STAGE_COMPLETED, "Init complete", llm_enabled=context.client is not None)

    return {
        "domain_config": config.model_dump(),
        "llm_enabled": context.client is not None,
        "retry_count": 0,
        "current_idx": 0,
        "review_feedback": "",
    }


def plan_node(state: ResearchState) -> dict[str, Any]:
    """Call PlannerAgent to decompose the question into sub-questions."""
    _emit(EventType.AGENT_STARTED, "PlannerAgent started")

    config = DomainConfig(**state["domain_config"])
    context = _build_context()
    agent = _get_agent("planner", context)

    loop = _get_loop()
    result = loop.run_until_complete(
        agent.execute(question=state["question"], config=config)
    )

    sub_questions = result.get("sub_questions", [])
    _emit(EventType.AGENT_COMPLETED, f"PlannerAgent produced {len(sub_questions)} sub-questions")

    return {
        "sub_questions": sub_questions,
        "current_idx": 0,
    }


def research_node(state: ResearchState) -> dict[str, Any]:
    """Call ResearcherAgent for the current sub-question."""
    idx = state.get("current_idx", 0)
    sub_questions = state.get("sub_questions", [])

    if idx >= len(sub_questions):
        return {}

    sq = sub_questions[idx]
    q_text = sq.get("question", "") if isinstance(sq, dict) else str(sq)

    _emit(EventType.ITEM_STARTED, f"Researching sub-question {idx + 1}/{len(sub_questions)}")
    _emit(EventType.AGENT_STARTED, "ResearcherAgent started")

    config = DomainConfig(**state["domain_config"])
    context = _build_context()
    agent = _get_agent("researcher", context)
    tool_executor = build_tool_executor(config)

    loop = _get_loop()
    result = loop.run_until_complete(
        agent.execute(question=q_text, config=config, tool_executor=tool_executor)
    )

    _emit(EventType.AGENT_COMPLETED, f"ResearcherAgent completed sub-question {idx + 1}")

    return {
        "findings": [result],  # uses Annotated[list, add] reducer → appended
        "current_idx": idx + 1,
        "current_sub_question": sq,
    }


def synthesize_node(state: ResearchState) -> dict[str, Any]:
    """Call SynthesizerAgent to merge all findings into a summary."""
    _emit(EventType.AGENT_STARTED, "SynthesizerAgent started")

    config = DomainConfig(**state["domain_config"])
    context = _build_context()
    agent = _get_agent("synthesizer", context)

    findings = state.get("findings", [])
    question = state.get("question", "")

    loop = _get_loop()
    result = loop.run_until_complete(
        agent.execute(question=question, findings=findings, config=config)
    )

    # Run deterministic validation
    validation = validate_summary(
        result,
        min_words=config.summary_min_words,
        max_words=config.summary_max_words,
    )

    if not validation.passed:
        _emit(EventType.VALIDATION_FAILED, f"Summary validation failed: {validation.failures}")
    else:
        _emit(EventType.VALIDATION_PASSED, "Summary validation passed")

    _emit(EventType.AGENT_COMPLETED, "SynthesizerAgent completed")

    return {"summary": result}


def review_node(state: ResearchState) -> dict[str, Any]:
    """Call ReviewerAgent to critique the summary."""
    _emit(EventType.AGENT_STARTED, "ReviewerAgent started")

    config = DomainConfig(**state["domain_config"])
    context = _build_context()
    agent = _get_agent("reviewer", context)

    summary_text = state.get("summary", {}).get("text", "")
    question = state.get("question", "")

    loop = _get_loop()
    result = loop.run_until_complete(
        agent.execute(question=question, summary_text=summary_text, config=config)
    )

    passed = result.get("passed", True)
    retry_count = state.get("retry_count", 0)

    if not passed:
        _emit(EventType.AGENT_RETRY, f"Review failed (attempt {retry_count + 1})")
        feedback = "; ".join(result.get("issues", []))
    else:
        _emit(EventType.AGENT_COMPLETED, "ReviewerAgent passed")
        feedback = ""

    return {
        "review": result,
        "retry_count": retry_count + 1,
        "review_feedback": feedback,
    }


def finalize_node(state: ResearchState) -> dict[str, Any]:
    """Assemble the final report from accumulated state."""
    from skeleton.core.models import ResearchReport, SubQuestion, Finding, Summary, ReviewResult

    sub_questions = [
        SubQuestion(**sq) if isinstance(sq, dict) else sq
        for sq in state.get("sub_questions", [])
    ]
    findings = [
        Finding(**f) if isinstance(f, dict) else f
        for f in state.get("findings", [])
    ]

    summary_data = state.get("summary")
    summary = Summary(**summary_data) if summary_data else None

    review_data = state.get("review")
    review = ReviewResult(**review_data) if review_data else None

    report = ResearchReport(
        question=state.get("question", ""),
        sub_questions=sub_questions,
        findings=findings,
        summary=summary,
        review=review,
    )

    _emit(EventType.PIPELINE_COMPLETED, f"Pipeline completed — {len(findings)} findings")

    return {"final_report": report.model_dump()}


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def has_more_questions(state: ResearchState) -> str:
    """Route: loop back to ``research`` if more sub-questions remain,
    otherwise proceed to ``synthesize``.
    """
    idx = state.get("current_idx", 0)
    total = len(state.get("sub_questions", []))
    if idx < total:
        return "research"
    return "synthesize"


def should_retry(state: ResearchState) -> str:
    """Route: if review failed and retries remain, go back to
    ``synthesize``; otherwise proceed to ``finalize``.

    # CUSTOMIZE: Adjust retry logic or add more sophisticated gating.
    """
    review = state.get("review", {})
    passed = review.get("passed", True)
    retry_count = state.get("retry_count", 0)

    if not passed and retry_count <= MAX_REVIEW_RETRIES:
        return "synthesize"
    return "finalize"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Build and compile the research graph.

    Returns a compiled LangGraph ``CompiledGraph`` ready for
    ``.invoke(input_state)``.

    # CUSTOMIZE: Add/remove nodes; change the topology.
    """
    graph = StateGraph(ResearchState)

    # --- nodes ---
    graph.add_node("init", init_node)
    graph.add_node("plan", plan_node)
    graph.add_node("research", research_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("review", review_node)
    graph.add_node("finalize", finalize_node)

    # --- edges ---
    graph.add_edge(START, "init")
    graph.add_edge("init", "plan")
    graph.add_edge("plan", "research")

    # After each research step: loop or proceed
    graph.add_conditional_edges("research", has_more_questions)

    # After synthesis: review
    graph.add_edge("synthesize", "review")

    # After review: retry synthesis or finalize
    graph.add_conditional_edges("review", should_retry)

    graph.add_edge("finalize", END)

    return graph.compile()


def reset_caches() -> None:
    """Reset module-level caches (useful between test runs)."""
    global _llm_client_cache, _agent_cache, _event_loop
    _llm_client_cache = None
    _agent_cache.clear()
    if _event_loop and not _event_loop.is_closed():
        _event_loop.close()
    _event_loop = None
