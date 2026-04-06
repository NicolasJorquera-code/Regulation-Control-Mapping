"""Pipeline event system for UI streaming and observability.

Provides a lightweight event protocol that pipeline stages emit to report
progress, warnings, and results.  The EventEmitter decouples producers
(orchestrator, agents) from consumers (CLI, Streamlit, log sinks).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class EventType(str, Enum):
    """Pipeline event categories."""

    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"

    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"

    PROGRESS = "progress"

    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_RETRY = "agent.retry"

    VALIDATION_PASSED = "validation.passed"
    VALIDATION_FAILED = "validation.failed"

    EXPORT_STARTED = "export.started"
    EXPORT_COMPLETED = "export.completed"

    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"

    CONTROL_STARTED = "control.started"
    CONTROL_COMPLETED = "control.completed"

    WARNING = "warning"


@dataclass(frozen=True)
class PipelineEvent:
    """A single event emitted during pipeline execution."""

    event_type: EventType
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""
    stage: str = ""


class EventListener(Protocol):
    """Protocol for event consumers."""

    def __call__(self, event: PipelineEvent) -> None: ...


class EventEmitter:
    """Fan-out event dispatcher."""

    def __init__(self, listeners: list[EventListener] | None = None) -> None:
        self._listeners: list[EventListener] = list(listeners or [])

    def on(self, listener: EventListener) -> None:
        """Register a new listener."""
        self._listeners.append(listener)

    def emit(self, event: PipelineEvent) -> None:
        """Dispatch event to all registered listeners."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass  # listeners must not break the pipeline

    def stage_started(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(
            PipelineEvent(
                event_type=EventType.STAGE_STARTED,
                message=f"Stage started: {stage}",
                stage=stage,
                run_id=run_id,
                data=data,
            )
        )

    def stage_completed(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(
            PipelineEvent(
                event_type=EventType.STAGE_COMPLETED,
                message=f"Stage completed: {stage}",
                stage=stage,
                run_id=run_id,
                data=data,
            )
        )

    def progress(self, message: str, run_id: str = "", **data: Any) -> None:
        self.emit(
            PipelineEvent(
                event_type=EventType.PROGRESS,
                message=message,
                run_id=run_id,
                data=data,
            )
        )


def cli_listener(event: PipelineEvent) -> None:
    """Simple listener that prints events for CLI verbose mode."""
    print(f"[controlnexus] {event.message}")
