"""Streamlit progress listener — renders a live progress bar + status log.

Implements the ``EventListener`` protocol so it can be attached to any
``EventEmitter`` alongside ``SQLiteTraceListener``.

Usage inside a pipeline runner::

    progress_bar = st.progress(0, text="Initializing…")
    with st.status("Classification Pipeline", expanded=True) as status:
        listener = StreamlitProgressListener(progress_bar, status, "classify")
        emitter.on(listener)
        result = graph.invoke(input_state)
        status.update(label="Complete!", state="complete")
"""

from __future__ import annotations

import re

from regrisk.core.events import EventType, PipelineEvent

# Regex to extract "(3/10)" counters from event messages.
_COUNTER_RE = re.compile(r"\((\d+)/(\d+)\)")

# Phase weight maps — values are (start%, end%) of the overall progress bar.
# Weights should cover 0‥1 and must be monotonically increasing.
_CLASSIFY_PHASES: dict[str, tuple[float, float]] = {
    "init":       (0.00, 0.05),
    "ingest":     (0.05, 0.10),
    "classify":   (0.10, 0.95),
    "finalize":   (0.95, 1.00),
}

_ASSESS_PHASES: dict[str, tuple[float, float]] = {
    "map":          (0.00, 0.30),
    "prep_assess":  (0.30, 0.35),
    "assess":       (0.35, 0.75),
    "prep_risk":    (0.75, 0.78),
    "extract":      (0.78, 0.95),
    "finalize":     (0.95, 1.00),
}

# Map EventType → internal phase name.
_CLASSIFY_EVENT_PHASE: dict[EventType, str] = {
    EventType.PIPELINE_STARTED:  "init",
    EventType.STAGE_COMPLETED:   "ingest",   # "Init complete" ends init phase
    EventType.STAGE_STARTED:     "ingest",   # "Ingesting data"
    EventType.INGEST_COMPLETED:  "classify",
    EventType.ITEM_STARTED:      "classify", # "Classifying … (X/Y)"
    EventType.GROUP_CLASSIFIED:  "classify",
    EventType.PIPELINE_COMPLETED: "finalize",
}

_ASSESS_EVENT_PHASE: dict[EventType, str] = {
    EventType.ITEM_STARTED:       "map",      # disambiguated by message below
    EventType.MAPPING_COMPLETED:  "map",
    EventType.STAGE_STARTED:      "prep_assess",  # disambiguated by message
    EventType.STAGE_COMPLETED:    "prep_assess",
    EventType.COVERAGE_ASSESSED:  "assess",
    EventType.RISK_SCORED:        "extract",
    EventType.PIPELINE_COMPLETED: "finalize",
}

# Events that get written to the status log (phase-level, not per-item).
_LOG_EVENTS: set[EventType] = {
    EventType.PIPELINE_STARTED,
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    EventType.INGEST_COMPLETED,
    EventType.GROUP_CLASSIFIED,
    EventType.MAPPING_COMPLETED,
    EventType.COVERAGE_ASSESSED,
    EventType.RISK_SCORED,
    EventType.PIPELINE_COMPLETED,
    EventType.PIPELINE_FAILED,
}


class StreamlitProgressListener:
    """Fan-in event listener that drives ``st.progress`` + ``st.status``."""

    def __init__(self, progress_bar, status_container, graph_type: str) -> None:
        self._bar = progress_bar
        self._status = status_container
        self._phases = _CLASSIFY_PHASES if graph_type == "classify" else _ASSESS_PHASES
        self._event_phase_map = (
            _CLASSIFY_EVENT_PHASE if graph_type == "classify" else _ASSESS_EVENT_PHASE
        )
        self._graph_type = graph_type
        self._current_phase = ""
        self._progress: float = 0.0

    # ------------------------------------------------------------------
    # EventListener protocol
    # ------------------------------------------------------------------

    def __call__(self, event: PipelineEvent) -> None:
        phase = self._resolve_phase(event)
        if phase and phase in self._phases:
            self._current_phase = phase
            self._update_progress(event, phase)

        # Write phase-level milestones to the status log.
        if event.event_type in _LOG_EVENTS:
            icon = _event_icon(event.event_type)
            self._status.write(f"{icon} {event.message}")

        # Update the progress bar text with the latest message.
        label = event.message or "Processing…"
        clamped = min(max(int(self._progress * 100), 0), 100)
        self._bar.progress(clamped, text=label)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_phase(self, event: PipelineEvent) -> str:
        """Determine which internal phase an event belongs to."""
        etype = event.event_type
        msg = event.message.lower()

        if self._graph_type == "assess":
            # Disambiguate ITEM_STARTED / STAGE_STARTED by message content.
            if etype == EventType.ITEM_STARTED:
                if "mapping" in msg or "map" in msg:
                    return "map"
                if "assess" in msg or "coverage" in msg:
                    return "assess"
                if "risk" in msg or "extract" in msg:
                    return "extract"
                return self._current_phase or "map"
            if etype == EventType.STAGE_STARTED:
                if "coverage" in msg or "assessment" in msg:
                    return "prep_assess"
                if "risk" in msg:
                    return "prep_risk"
                if "finali" in msg:
                    return "finalize"
                return self._current_phase or "prep_assess"
            if etype == EventType.STAGE_COMPLETED:
                if "prepared" in msg or "assessment" in msg:
                    return "prep_assess"
                if "gaps" in msg or "risk" in msg:
                    return "prep_risk"
                return self._current_phase or "prep_assess"

        return self._event_phase_map.get(etype, self._current_phase or "")

    def _update_progress(self, event: PipelineEvent, phase: str) -> None:
        """Compute overall progress [0, 1] from phase weights + item counter."""
        start, end = self._phases[phase]
        span = end - start

        # Try to extract (X/Y) from the message for within-phase interpolation.
        match = _COUNTER_RE.search(event.message)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            fraction = current / total if total else 0.0
        else:
            # No counter — snap to start of phase (events like STAGE_STARTED),
            # or end of phase (events like *_COMPLETED / *_CLASSIFIED).
            if event.event_type in (
                EventType.PIPELINE_COMPLETED,
                EventType.STAGE_COMPLETED,
                EventType.INGEST_COMPLETED,
                EventType.GROUP_CLASSIFIED,
                EventType.MAPPING_COMPLETED,
                EventType.COVERAGE_ASSESSED,
                EventType.RISK_SCORED,
            ):
                fraction = 1.0
            else:
                fraction = 0.0

        self._progress = max(self._progress, start + span * fraction)


def _event_icon(event_type: EventType) -> str:
    """Return a small emoji prefix for status-log lines."""
    return {
        EventType.PIPELINE_STARTED:  "🚀",
        EventType.STAGE_STARTED:     "⏳",
        EventType.STAGE_COMPLETED:   "✅",
        EventType.INGEST_COMPLETED:  "📥",
        EventType.GROUP_CLASSIFIED:  "🏷️",
        EventType.MAPPING_COMPLETED: "🗺️",
        EventType.COVERAGE_ASSESSED: "🔍",
        EventType.RISK_SCORED:       "⚠️",
        EventType.PIPELINE_COMPLETED: "🎉",
        EventType.PIPELINE_FAILED:   "❌",
    }.get(event_type, "•")
