"""
Async LLM HTTP transport layer with multi-provider support and retry logic.

Pattern: Protocol-agnostic async client that speaks the OpenAI
chat-completions API.  Supports multiple providers (OpenAI, Anthropic)
via environment-variable autodiscovery, exponential-backoff retries,
and URL path discovery for reverse-proxy setups.

Usage:
    client = build_client_from_env()
    if client:
        result = await client.chat_completion(messages=[...])

# CUSTOMIZE: Add more providers by extending ``build_client_from_env``
# and ``_candidate_urls``.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from skeleton.exceptions import TransportError


# ---------------------------------------------------------------------------
# Transport client
# ---------------------------------------------------------------------------

@dataclass
class AsyncTransportClient:
    """Async OpenAI-compatible chat-completion client.

    Attributes are set once at construction; the underlying ``httpx``
    client is lazily created on first call.
    """

    api_key: str
    base_url: str
    model: str
    # CUSTOMIZE: Add your provider name here if you use a custom gateway.
    provider: str = "openai"
    timeout_seconds: int = 120
    max_retries: int = 3

    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _working_url: str | None = field(default=None, repr=False)

    # ---- public API ----

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1400,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        """Send a chat-completion request with automatic retry + URL discovery."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        client = await self._get_client()
        last_exc: Exception | None = None

        urls = [self._working_url] if self._working_url else self._candidate_urls()

        for url in urls:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if resp.status_code == 404:
                        break  # try next URL
                    if resp.status_code in (401, 403):
                        raise TransportError(f"Auth failure ({resp.status_code}): {resp.text[:200]}")
                    if resp.status_code == 429:
                        body = resp.text
                        if "insufficient_quota" in body.lower():
                            raise TransportError("Quota exceeded")
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
                        last_exc = TransportError(f"Rate limited (attempt {attempt + 1})")
                        continue
                    if resp.status_code >= 500:
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
                        last_exc = TransportError(f"Server error {resp.status_code}")
                        continue

                    resp.raise_for_status()
                    self._working_url = url
                    return resp.json()

                except httpx.RequestError as exc:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    last_exc = TransportError(str(exc))

        raise last_exc or TransportError("All attempts exhausted")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ---- internals ----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    def _candidate_urls(self) -> list[str]:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return [f"{base}/v1/chat/completions", f"{base}/chat/completions"]


# ---------------------------------------------------------------------------
# Environment-based factory
# ---------------------------------------------------------------------------

def build_client_from_env(
    timeout_seconds: int = 120,
    model_override: str | None = None,
) -> AsyncTransportClient | None:
    """Auto-detect LLM provider from environment variables.

    Detection order:
        1. OPENAI_API_KEY  → OpenAI  (default model: gpt-4o)
        2. ANTHROPIC_API_KEY → Anthropic (default model: claude-sonnet-4-20250514)

    Returns ``None`` when no credentials are found (LLM-disabled mode).

    # CUSTOMIZE: Add more providers or change the detection order.
    """
    # --- OpenAI ---
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return AsyncTransportClient(
            api_key=openai_key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
            model=model_override or os.environ.get("OPENAI_MODEL", "gpt-4o"),
            provider="openai",
            timeout_seconds=timeout_seconds,
        )

    # --- Anthropic ---
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        return AsyncTransportClient(
            api_key=anthropic_key,
            base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            model=model_override or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            provider="anthropic",
            timeout_seconds=timeout_seconds,
        )

    return None
