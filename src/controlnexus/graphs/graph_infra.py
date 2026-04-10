"""Shared graph infrastructure for LangGraph-based pipelines.

Provides module-level caches and helpers used by both the ControlForge
Modular graph and any future graph pipelines:

- **Event emitter**: fan-out event dispatch via ``set_emitter`` / ``_emit_event``.
- **Async event loop**: persistent loop so httpx connection pools survive
  across synchronous LangGraph node calls.
- **LLM client cache**: single ``AsyncTransportClient`` per process.
- **Agent cache**: one ``BaseAgent`` proxy per agent name.

All caches are cleared by ``reset_caches()``.

.. note::
   If the feature branch ``control_builder_helpers.py`` has duplicated
   emitter/async/agent patterns, it should also import from this module
   when merged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from controlnexus.agents.base import AgentContext, BaseAgent
from controlnexus.core.events import EventEmitter, EventType, PipelineEvent
from controlnexus.core.transport import build_client_from_env

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event emitter management
# ---------------------------------------------------------------------------

_emitter: EventEmitter = EventEmitter()


def set_emitter(emitter: EventEmitter) -> None:
    """Set the module-level emitter (called by UI layer before graph run)."""
    global _emitter
    _emitter = emitter


def get_emitter() -> EventEmitter:
    """Return the current module-level emitter."""
    return _emitter


def _emit_event(event_type: EventType, message: str = "", **data: Any) -> None:
    """Emit an event on the module-level emitter."""
    _emitter.emit(PipelineEvent(event_type=event_type, message=message, data=data))


# ---------------------------------------------------------------------------
# Async event loop
# ---------------------------------------------------------------------------

_event_loop: asyncio.AbstractEventLoop | None = None


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop for LLM calls.

    A dedicated loop is kept alive so the async httpx connection pool
    doesn't break between synchronous LangGraph node calls
    (``asyncio.run()`` would close the loop each time, killing TCP
    connections).
    """
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _run_async_in_loop(coro: Any) -> Any:
    """Run an async coroutine on the persistent event loop."""
    return _get_or_create_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# LLM client and agent caches
# ---------------------------------------------------------------------------

_llm_client_cache: dict[str, Any] = {}  # {"client": AsyncTransportClient | None}
_agent_cache: dict[str, BaseAgent] = {}  # {"SpecAgent": agent, ...}


def _get_client() -> Any | None:
    """Return the cached transport client, building it once."""
    if "client" not in _llm_client_cache:
        _llm_client_cache["client"] = build_client_from_env()
    return _llm_client_cache["client"]


def _get_agent(name: str) -> BaseAgent | None:
    """Return a cached BaseAgent wrapper with the given display *name*.

    Returns ``None`` when no LLM credentials are available.
    """
    client = _get_client()
    if client is None:
        return None

    if name not in _agent_cache:

        class _Proxy(BaseAgent):
            async def execute(self, **kwargs: Any) -> dict[str, Any]:
                raise NotImplementedError  # we use call_llm directly

        ctx = AgentContext(client=client, model=client.model)
        _agent_cache[name] = _Proxy(ctx, name=name)

    return _agent_cache[name]


# ---------------------------------------------------------------------------
# Cache reset
# ---------------------------------------------------------------------------


def reset_caches() -> None:
    """Clear all module-level caches (useful between test runs)."""
    global _event_loop
    if _event_loop is not None and not _event_loop.is_closed():
        _event_loop.close()
    _event_loop = None
    _llm_client_cache.clear()
    _agent_cache.clear()
