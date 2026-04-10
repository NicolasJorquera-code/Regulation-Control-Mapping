"""
Lightweight event bus for pipeline observability and UI streaming.

Adapted from the skeleton project's event bus with domain-specific events
for the regulatory obligation mapping pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Pipeline lifecycle events."""

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

    # Domain-specific events
    INGEST_COMPLETED = "ingest_completed"
    GROUP_CLASSIFIED = "group_classified"
    MAPPING_COMPLETED = "mapping_completed"
    COVERAGE_ASSESSED = "coverage_assessed"
    RISK_SCORED = "risk_scored"
    REVIEW_CHECKPOINT = "review_checkpoint"


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
    """Fan-out event dispatcher."""

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def on(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def emit(self, event: PipelineEvent) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning("EventEmitter listener error: %s", exc)

    def stage_started(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.STAGE_STARTED, stage=stage, run_id=run_id, data=data))

    def stage_completed(self, stage: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.STAGE_COMPLETED, stage=stage, run_id=run_id, data=data))

    def progress(self, message: str, run_id: str = "", **data: Any) -> None:
        self.emit(PipelineEvent(EventType.PROGRESS, message=message, run_id=run_id, data=data))
