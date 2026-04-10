"""Async LLM transport layer for ControlNexus.

Provides AsyncTransportClient wrapping httpx.AsyncClient with retry logic,
candidate URL discovery, and multi-provider support (ICA, OpenAI, Anthropic).
"""

from __future__ import annotations

import asyncio
import logging

from controlnexus.core.constants import DEFAULT_MODEL
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv

from controlnexus.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transport client
# ---------------------------------------------------------------------------


@dataclass
class AsyncTransportClient:
    """Async HTTP client for LLM chat completions.

    Tries candidate URLs in order, caches the first successful one,
    and retries with exponential backoff on transient failures.
    """

    api_key: str
    base_url: str
    model: str
    provider: str = "openai"  # "ica", "openai", or "anthropic"
    ica_tool_calling: bool = False  # True enables XML tool-call simulation for ICA
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
        # Strip trailing /v1 to avoid doubled paths like /v1/v1/chat/completions
        if base.endswith("/v1"):
            base = base[:-3]
        candidates = [f"{base}/v1/chat/completions", f"{base}/chat/completions"]
        if self._working_url:
            return [self._working_url] + [u for u in candidates if u != self._working_url]
        return candidates

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1400,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request with retry and URL discovery.

        Returns the raw JSON response dict.
        """
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        last_error: Exception | None = None
        for url in self._candidate_urls():
            for attempt in range(self.max_retries):
                try:
                    logger.debug("POST to %s (attempt %d)", url, attempt + 1)
                    resp = await client.post(url, json=payload, headers=headers)
                    logger.debug("Response from %s: HTTP %d", url, resp.status_code)

                    if resp.status_code == 404:
                        # Distinguish API errors (correct URL, bad request)
                        # from genuine path-not-found (wrong URL pattern).
                        try:
                            body = resp.json()
                            if "error" in body:
                                err_msg = body["error"]
                                if isinstance(err_msg, dict):
                                    err_msg = err_msg.get("message", str(body["error"]))
                                raise ExternalServiceException(
                                    f"API error at {url}: {err_msg}"
                                )
                        except (ValueError, KeyError, TypeError):
                            pass
                        last_error = ExternalServiceException(f"404 at {url}")
                        break  # try next URL

                    if resp.status_code in (401, 403):
                        raise ExternalServiceException(f"Authentication failure at {url} (HTTP {resp.status_code})")

                    if resp.status_code == 429:
                        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                        err = body.get("error", {})
                        if isinstance(err, dict) and err.get("code") == "insufficient_quota":
                            raise ExternalServiceException(
                                "OpenAI quota exceeded — check your plan and billing at https://platform.openai.com/account/billing"
                            )
                        # Rate-limited but not quota — retry with backoff
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2**attempt)
                            continue

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
                        await asyncio.sleep(2**attempt)
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2**attempt)

        raise ExternalServiceException("All LLM endpoint candidates exhausted") from last_error

    async def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


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
        ica_tool_calling = os.getenv("ICA_TOOL_CALLING", "false").lower() in ("true", "1", "yes")
        logger.info("LLM client configured (ICA, tool_calling=%s): %s", ica_tool_calling, base_url)
        return AsyncTransportClient(
            api_key=api_key,
            base_url=base_url,
            model=model_id,
            provider="ica",
            ica_tool_calling=ica_tool_calling,
            timeout_seconds=timeout_seconds,
        )

    # OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    model_id = model_override or os.getenv("OPENAI_MODEL_ID", DEFAULT_MODEL)
    if api_key:
        logger.info("LLM client configured (OpenAI): %s", base_url)
        return AsyncTransportClient(
            api_key=api_key,
            base_url=base_url,
            model=model_id,
            provider="openai",
            timeout_seconds=timeout_seconds,
        )

    # Anthropic (via OpenAI-compatible proxy or direct)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model_id = model_override or os.getenv("ANTHROPIC_MODEL_ID", "claude-sonnet-4-6")
        logger.info("LLM client configured (Anthropic): %s", base_url)
        return AsyncTransportClient(
            api_key=api_key,
            base_url=base_url,
            model=model_id,
            provider="anthropic",
            timeout_seconds=timeout_seconds,
        )

    logger.info("LLM credentials not found — LLM mode disabled")
    return None
