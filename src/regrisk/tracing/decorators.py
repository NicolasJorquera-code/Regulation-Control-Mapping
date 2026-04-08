"""
Graph-node tracing decorator — records timing & state summaries.

Wraps each LangGraph node function to capture:

* Entry / exit timestamps and duration
* A *summary* of the input state (which keys are present, list/dict sizes)
* A *summary* of the output dict
* Any exceptions raised

It also maintains a **thread-local trace context** (current node name and
agent name) that the ``TracingTransportClient`` reads to annotate LLM calls.

Usage in graph builders::

    from regrisk.tracing import trace_node, TraceDB

    db = TraceDB("data/traces.db")
    run_id = "abc-123"

    # Wrap an existing node function:
    graph.add_node("init", trace_node(db, run_id, "init")(init_node))
"""

from __future__ import annotations

import functools
import json
import logging
import threading
import time
from typing import Any, Callable

from regrisk.tracing.db import TraceDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread-local trace context (read by TracingTransportClient)
# ---------------------------------------------------------------------------

_trace_context = threading.local()


def set_current_trace_context(node_name: str = "", agent_name: str = "") -> None:
    """Set the current node/agent context (called automatically by ``trace_node``)."""
    _trace_context.node_name = node_name
    _trace_context.agent_name = agent_name


def get_current_trace_context() -> dict[str, str]:
    """Return the current trace context dict."""
    return {
        "node_name": getattr(_trace_context, "node_name", ""),
        "agent_name": getattr(_trace_context, "agent_name", ""),
    }


# ---------------------------------------------------------------------------
# State summariser (lightweight — no full data copies)
# ---------------------------------------------------------------------------

def _summarise_state(state: dict[str, Any]) -> str:
    """Return a compact JSON summary of a state dict.

    For each key, records its type and — for lists/dicts — its length.
    This lets you see *what* changed without storing megabytes of obligation data.

    Example output::

        {"regulation_name": "str(45)", "obligation_groups": "list(12)", "errors": "list(0)"}
    """
    summary: dict[str, str] = {}
    for key, val in state.items():
        if isinstance(val, list):
            summary[key] = f"list({len(val)})"
        elif isinstance(val, dict):
            summary[key] = f"dict({len(val)})"
        elif isinstance(val, str):
            summary[key] = f"str({len(val)})"
        elif isinstance(val, bool):
            summary[key] = str(val)
        elif isinstance(val, (int, float)):
            summary[key] = str(val)
        elif val is None:
            summary[key] = "None"
        else:
            summary[key] = type(val).__name__
    return json.dumps(summary)


# ---------------------------------------------------------------------------
# Decorator factory
# ---------------------------------------------------------------------------

def trace_node(
    db: TraceDB,
    run_id: str,
    node_name: str,
) -> Callable:
    """Decorator factory that instruments a LangGraph node function.

    Parameters
    ----------
    db : TraceDB
        Open trace database.
    run_id : str
        Current pipeline run identifier.
    node_name : str
        Human-readable name for this node (e.g. ``"classify_group"``).

    Returns
    -------
    decorator
        A function decorator that can wrap any ``(state) -> dict`` node.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            # Set context so the transport wrapper knows where LLM calls originate
            set_current_trace_context(node_name=node_name, agent_name="")

            input_summary = _summarise_state(state)
            started_at = time.time()

            logger.info("")
            logger.info("━" * 60)
            logger.info("▶ NODE: %s", node_name)
            logger.info("━" * 60)

            try:
                result = fn(state)
                output_summary = _summarise_state(result) if isinstance(result, dict) else "{}"
                completed_at = time.time()
                duration_ms = (completed_at - started_at) * 1000

                logger.info(
                    "✔ NODE: %s completed in %.1fs — output keys: %s",
                    node_name, duration_ms / 1000,
                    ", ".join(result.keys()) if isinstance(result, dict) else "(empty)",
                )

                db.insert_node_execution(
                    run_id=run_id,
                    node_name=node_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    input_summary=input_summary,
                    output_summary=output_summary,
                )
                return result

            except Exception as exc:
                completed_at = time.time()
                duration_ms = (completed_at - started_at) * 1000

                logger.error(
                    "✘ NODE: %s failed after %.1fs — %s: %s",
                    node_name, duration_ms / 1000, type(exc).__name__, exc,
                )

                db.insert_node_execution(
                    run_id=run_id,
                    node_name=node_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    input_summary=input_summary,
                    output_summary="{}",
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise

            finally:
                # Clear context after the node finishes
                set_current_trace_context()

        return wrapper
    return decorator
