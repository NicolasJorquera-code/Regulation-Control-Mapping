"""
Public API for the regrisk tracing package.

Quick-start::

    from regrisk.tracing import TraceDB, SQLiteTraceListener, TracingTransportClient, trace_node

    db = TraceDB("data/traces.db")
    listener = SQLiteTraceListener(db, run_id="abc-123")
    emitter.on(listener)
"""

from regrisk.tracing.db import TraceDB
from regrisk.tracing.decorators import trace_node, get_current_trace_context, set_current_trace_context
from regrisk.tracing.listener import SQLiteTraceListener
from regrisk.tracing.transport_wrapper import TracingTransportClient

__all__ = [
    "TraceDB",
    "SQLiteTraceListener",
    "TracingTransportClient",
    "trace_node",
    "get_current_trace_context",
    "set_current_trace_context",
]
