"""Async LLM transport layer for ControlNexus.

Provides AsyncTransportClient wrapping httpx.AsyncClient with retry logic,
candidate URL discovery, and multi-provider support (ICA, OpenAI, Anthropic).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv

from controlnexus.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)


@dataclass
class AsyncTransportClient:
    """Async HTTP client for LLM chat completions.

    Tries candidate URLs in order, caches the first successful one,
    and retries with exponential backoff on transient failures.
    """

    api_key: str
    base_url: str
    model: str
    timeout_seconds: int = 120
    max_retries: int = 3
    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _working_url: str | None = field(default=None, repr=False)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    def _candidate_urls(self) -> list[str]:
        base = self.base_url.rstrip("/")
        candidates = [f"{base}/v1/chat/completions", f"{base}/chat/completions"]
        if self._working_url:
            return [self._working_url] + [u for u in candidates if u != self._working_url]
        return candidates

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1400,
    ) -> dict[str, Any]:
        """Send a chat completion request with retry and URL discovery.

        Returns the raw JSON response dict.
        """
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        last_error: Exception | None = None
        for url in self._candidate_urls():
            for attempt in range(self.max_retries):
                try:
                    logger.debug("POST to %s (attempt %d)", url, attempt + 1)
                    resp = await client.post(url, json=payload, headers=headers)

                    if resp.status_code == 404:
                        last_error = ExternalServiceException(f"404 at {url}")
                        break  # try next URL

                    if resp.status_code in (401, 403):
                        raise ExternalServiceException(
                            f"Authentication failure at {url} (HTTP {resp.status_code})"
                        )

                    resp.raise_for_status()
                    self._working_url = url
                    return resp.json()

                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code in (401, 403):
                        raise ExternalServiceException(
                            f"Authentication failure at {url} (HTTP {exc.response.status_code})"
                        ) from exc
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)

        raise ExternalServiceException("All LLM endpoint candidates exhausted") from last_error

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def build_client_from_env(
    timeout_seconds: int = 120,
    model_override: str | None = None,
) -> AsyncTransportClient | None:
    """Build an AsyncTransportClient from environment variables.

    Checks providers in order: ICA, OpenAI, Anthropic.
    Returns None if no credentials found (LLM mode disabled).
    """
    load_dotenv()

    # ICA
    api_key = os.getenv("ICA_API_KEY")
    base_url = os.getenv("ICA_BASE_URL")
    model_id = model_override or os.getenv("ICA_MODEL_ID")
    if api_key and base_url and model_id:
        logger.info("LLM client configured (ICA): %s", base_url)
        return AsyncTransportClient(
            api_key=api_key, base_url=base_url, model=model_id,
            timeout_seconds=timeout_seconds,
        )

    # OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    model_id = model_override or os.getenv("OPENAI_MODEL_ID", "gpt-4o")
    if api_key:
        logger.info("LLM client configured (OpenAI): %s", base_url)
        return AsyncTransportClient(
            api_key=api_key, base_url=base_url, model=model_id,
            timeout_seconds=timeout_seconds,
        )

    # Anthropic (via OpenAI-compatible proxy or direct)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model_id = model_override or os.getenv("ANTHROPIC_MODEL_ID", "claude-sonnet-4-6")
        logger.info("LLM client configured (Anthropic): %s", base_url)
        return AsyncTransportClient(
            api_key=api_key, base_url=base_url, model=model_id,
            timeout_seconds=timeout_seconds,
        )

    logger.info("LLM credentials not found — LLM mode disabled")
    return None
