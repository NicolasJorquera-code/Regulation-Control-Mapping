"""
Event listener that persists PipelineEvents to the SQLite trace database.

Implements the ``EventListener`` protocol from ``regrisk.core.events``, so you
can attach it to any ``EventEmitter``::

    from regrisk.tracing import TraceDB, SQLiteTraceListener

    db = TraceDB("data/traces.db")
    listener = SQLiteTraceListener(db, run_id="abc-123")
    emitter.on(listener)          # receives every PipelineEvent
"""

from __future__ import annotations

from regrisk.core.events import EventType, PipelineEvent
from regrisk.tracing.db import TraceDB


class SQLiteTraceListener:
    """Callable that writes each ``PipelineEvent`` to the ``events`` table.

    Also detects pipeline lifecycle events to update the ``runs`` table:

    * ``PIPELINE_COMPLETED`` → status = "completed"
    * ``PIPELINE_FAILED``    → status = "failed"
    """

    def __init__(self, db: TraceDB, run_id: str) -> None:
        self.db = db
        self.run_id = run_id

    def __call__(self, event: PipelineEvent) -> None:
        # Persist every event
        self.db.insert_event(
            run_id=self.run_id,
            event_type=event.event_type.value,
            stage=event.stage,
            message=event.message,
            data=event.data,
            timestamp=event.timestamp,
        )

        # Update run status on lifecycle boundaries
        if event.event_type == EventType.PIPELINE_COMPLETED:
            reg_name = event.data.get("regulation_name")
            self.db.update_run_status(self.run_id, "completed", regulation_name=reg_name)
        elif event.event_type == EventType.PIPELINE_FAILED:
            self.db.update_run_status(self.run_id, "failed")
