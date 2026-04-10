"""
Shared infrastructure for LangGraph graph modules.

Extracts the duplicated module-level singleton pattern (emitter, LLM client
cache, agent cache, event loop) used by both classify_graph and assess_graph.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from regrisk.agents.base import AgentContext
from regrisk.core.constants import DEFAULT_MODEL
from regrisk.core.events import EventEmitter, EventType, PipelineEvent
from regrisk.core.transport import AsyncTransportClient, build_client_from_env
from regrisk.tracing.transport_wrapper import TracingTransportClient

logger = logging.getLogger(__name__)


class GraphInfra:
    """Encapsulates the module-level caches shared across graph node invocations.

    Each graph module (classify_graph, assess_graph) creates its own instance.
    """

    def __init__(self) -> None:
        self.emitter: EventEmitter = EventEmitter()
        self._llm_client_cache: AsyncTransportClient | None = None
        self._agent_cache: dict[str, Any] = {}
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def set_emitter(self, emitter: EventEmitter) -> None:
        """Replace the current event emitter."""
        self.emitter = emitter

    def get_emitter(self) -> EventEmitter:
        """Return the current event emitter."""
        return self.emitter

    def emit_event(self, event_type: EventType, message: str = "", **data: Any) -> None:
        """Emit a pipeline event through the emitter."""
        self.emitter.emit(PipelineEvent(event_type=event_type, message=message, data=data))

    def get_or_create_event_loop(self) -> asyncio.AbstractEventLoop:
        """Return the cached event loop, creating a new one if needed."""
        if self._event_loop is None or self._event_loop.is_closed():
            self._event_loop = asyncio.new_event_loop()
        return self._event_loop

    def build_agent_context(self, max_tokens: int = 8000) -> AgentContext:
        """Build an AgentContext, caching the LLM client across calls."""
        if self._llm_client_cache is None:
            self._llm_client_cache = build_client_from_env()
        model = DEFAULT_MODEL
        if self._llm_client_cache:
            model = self._llm_client_cache.model
        return AgentContext(client=self._llm_client_cache, model=model, max_tokens=max_tokens)

    def get_agent(self, name: str, agent_classes: dict[str, type], context: AgentContext) -> Any:
        """Return a cached agent instance, creating it if needed."""
        if name not in self._agent_cache:
            cls = agent_classes[name]
            self._agent_cache[name] = cls(context)
        return self._agent_cache[name]

    def reset_caches(self) -> None:
        """Reset all caches (for test isolation and between runs)."""
        self._llm_client_cache = None
        self._agent_cache = {}
        if self._event_loop and not self._event_loop.is_closed():
            if self._event_loop.is_running():
                self._event_loop = None
            else:
                self._event_loop.close()
                self._event_loop = None
        else:
            self._event_loop = None
        self.emitter = EventEmitter()

    def install_tracing_transport(self, trace_db: Any, run_id: str) -> None:
        """Replace the cached LLM client with a tracing wrapper."""
        if self._llm_client_cache is None:
            self._llm_client_cache = build_client_from_env()
        if self._llm_client_cache and not isinstance(self._llm_client_cache, TracingTransportClient):
            self._llm_client_cache = TracingTransportClient(self._llm_client_cache, trace_db, run_id)
        # Update already-cached agents so they use the wrapped client
        for agent in self._agent_cache.values():
            if hasattr(agent, "context") and agent.context.client is not self._llm_client_cache:
                agent.context.client = self._llm_client_cache
