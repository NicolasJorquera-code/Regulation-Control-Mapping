"""
Lightweight event bus for pipeline observability and UI streaming.

Pattern: Protocol-based listener (dependency injection without inheritance).
The EventEmitter fans out immutable PipelineEvent snapshots to all
registered listeners.  Listeners that raise are caught and logged so a
bad observer never breaks the pipeline.

Usage:
    emitter = EventEmitter()
    emitter.on(my_listener_callback)
    emitter.stage_started("plan", run_id="run-1")

UI integration:
    The Streamlit UI registers a StreamlitEventListener before invoking
    the graph.  Each event is mapped to a status message (emoji + text)
    displayed in a live-updating container.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Pipeline lifecycle events.

    # CUSTOMIZE: Add domain-specific event types as your pipeline grows.
    # For example: DATA_INGESTED, EXPORT_STARTED, HUMAN_REVIEW_REQUESTED.
    """

    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"

    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    PROGRESS = "progress"

    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_RETRY = "agent_retry"

    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"

    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"

    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"

    WARNING = "warning"


# ---------------------------------------------------------------------------
# Immutable event snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineEvent:
    """Immutable event snapshot — safe to log, serialize, or replay."""

    event_type: EventType
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""
    stage: str = ""


# ---------------------------------------------------------------------------
# Listener protocol & emitter
# ---------------------------------------------------------------------------

class EventListener(Protocol):
    """Any callable matching this signature can observe pipeline events."""

    def __call__(self, event: PipelineEvent) -> None: ...


class EventEmitter:
    """Fan-out event dispatcher.

    Thread-safe for the common case (listeners added before pipeline
    starts, events emitted from a single thread).
    """

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def on(self, listener: EventListener) -> None:
        """Register a listener callback."""
        self._listeners.append(listener)

    def emit(self, event: PipelineEvent) -> None:
        """Dispatch *event* to every registered listener.

        Exceptions in listeners are caught and printed so that a faulty
        observer never crashes the pipeline.
        """
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as exc:  # noqa: BLE001
                print(f"[EventEmitter] listener error: {exc}")

    # ---- convenience helpers ----

    def stage_started(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.STAGE_STARTED, stage=stage, run_id=run_id, data=data))

    def stage_completed(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.STAGE_COMPLETED, stage=stage, run_id=run_id, data=data))

    def progress(self, message: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.PROGRESS, message=message, run_id=run_id, data=data))


# ---------------------------------------------------------------------------
# Built-in listener for CLI / debugging
# ---------------------------------------------------------------------------

def cli_listener(event: PipelineEvent) -> None:
    """Simple stdout printer — attach with ``emitter.on(cli_listener)``."""
    ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
    print(f"[{ts}] {event.event_type.value}: {event.message or event.stage}")
