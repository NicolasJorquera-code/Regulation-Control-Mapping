"""
Async LLM HTTP transport layer with multi-provider support and retry logic.

Adapted from the skeleton project. Speaks the OpenAI chat-completions API.
Supports ICA (IBM Cloud AI) and OpenAI via environment-variable autodiscovery.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from regrisk.exceptions import TransportError

logger = logging.getLogger(__name__)

# Pre-compiled pattern for detecting version segments in URLs
_VERSION_PATH_RE = re.compile(r"/v\d+")


# ---------------------------------------------------------------------------
# Transport client
# ---------------------------------------------------------------------------

@dataclass
class AsyncTransportClient:
    """Async OpenAI-compatible chat-completion client."""

    api_key: str
    base_url: str
    model: str
    provider: str = "openai"
    ica_tool_calling: bool = False
    timeout_seconds: int = 120
    max_retries: int = 5
    max_backoff: int = 60

    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _resolved_url: str | None = field(default=None, repr=False)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
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

        # Use the resolved URL if we already found one, otherwise discover it
        if self._resolved_url:
            urls = [self._resolved_url]
        else:
            urls = self._candidate_urls()
            logger.info(
                "URL discovery: provider=%s candidates=%s",
                self.provider, urls,
            )

        logger.debug(
            "LLM request: model=%s messages=%d max_tokens=%d",
            self.model, len(messages), max_tokens,
        )

        for url in urls:
            for attempt in range(self.max_retries):
                is_last_attempt = (attempt == self.max_retries - 1)
                logger.debug("POST %s (attempt %d/%d)", url, attempt + 1, self.max_retries)
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
                        if self._resolved_url:
                            # URL previously worked — treat as transient error
                            last_exc = TransportError(f"Transient 404 from {url}")
                            if is_last_attempt:
                                logger.error("Transient 404 — retries exhausted for resolved URL %s", url)
                                break
                            wait = min(2 ** attempt * 3, self.max_backoff)
                            wait *= 0.5 + random.random() * 0.5
                            logger.warning("Transient 404 from resolved URL, retry in %.1fs (attempt %d/%d)", wait, attempt + 1, self.max_retries)
                            await asyncio.sleep(wait)
                            continue
                        logger.warning("404 from %s — skipping to next candidate", url)
                        last_exc = TransportError(f"404 from {url}")
                        break  # try next URL
                    if resp.status_code in (401, 403):
                        raise TransportError(f"Auth failure ({resp.status_code}): {resp.text[:200]}")
                    if resp.status_code == 429:
                        body = resp.text
                        if "insufficient_quota" in body.lower():
                            raise TransportError("Quota exceeded — check your API plan")
                        if is_last_attempt:
                            last_exc = TransportError(f"Rate limited after {self.max_retries} attempts")
                            break  # try next URL if any
                        wait = min(2 ** attempt, self.max_backoff)
                        wait *= 0.5 + random.random() * 0.5  # jitter
                        logger.warning("Rate limited, retry in %.1fs (attempt %d/%d)", wait, attempt + 1, self.max_retries)
                        await asyncio.sleep(wait)
                        last_exc = TransportError(f"Rate limited (attempt {attempt + 1})")
                        continue
                    if resp.status_code >= 500:
                        snippet = resp.text[:300]
                        last_exc = TransportError(
                            f"Server error {resp.status_code} from {url}: {snippet}"
                        )
                        if is_last_attempt:
                            logger.error("Server error %d — retries exhausted: %s", resp.status_code, snippet)
                            break
                        # 524 = Cloudflare origin timeout — server needs more recovery time
                        base_wait = 10 if resp.status_code == 524 else 2 ** attempt
                        wait = min(base_wait * (attempt + 1), self.max_backoff)
                        wait *= 0.5 + random.random() * 0.5  # jitter
                        logger.warning("Server error %d, retry in %.1fs (attempt %d/%d): %s", resp.status_code, wait, attempt + 1, self.max_retries, snippet)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code >= 400:
                        body = resp.text[:500]
                        logger.error("HTTP %d from %s: %s", resp.status_code, url, body)
                        raise TransportError(f"HTTP {resp.status_code} from {url}: {body}")

                    # --- Success ---
                    self._resolved_url = url
                    data = resp.json()
                    usage = data.get("usage", {})

                    # Include agent/node context if available
                    _ctx_label = ""
                    try:
                        from regrisk.tracing.decorators import get_current_trace_context
                        _ctx = get_current_trace_context()
                        parts = []
                        if _ctx.get("node_name"):
                            parts.append(f"node={_ctx['node_name']}")
                        if _ctx.get("agent_name"):
                            parts.append(f"agent={_ctx['agent_name']}")
                        if parts:
                            _ctx_label = f" [{', '.join(parts)}]"
                    except Exception:
                        pass

                    logger.info(
                        "  ↳ LLM OK%s — prompt=%s completion=%s total=%s",
                        _ctx_label,
                        usage.get("prompt_tokens", "?"),
                        usage.get("completion_tokens", "?"),
                        usage.get("total_tokens", "?"),
                    )
                    return data

                except httpx.TimeoutException as exc:
                    last_exc = TransportError(
                        f"Timeout after {self.timeout_seconds}s "
                        f"(attempt {attempt + 1}/{self.max_retries}): {type(exc).__name__}"
                    )
                    if is_last_attempt:
                        logger.error("Timeout on final attempt for %s: %s", url, exc)
                        break
                    wait = min(2 ** attempt * 5, self.max_backoff)
                    wait *= 0.5 + random.random() * 0.5
                    logger.warning("Timeout (attempt %d/%d) for %s, retry in %.1fs", attempt + 1, self.max_retries, url, wait)
                    await asyncio.sleep(wait)

                except httpx.RequestError as exc:
                    last_exc = TransportError(
                        f"Connection error (attempt {attempt + 1}/{self.max_retries}): "
                        f"{type(exc).__name__}: {exc}"
                    )
                    if is_last_attempt:
                        logger.error("Connection error on final attempt for %s: %s", url, exc)
                        break
                    wait = min(2 ** attempt, self.max_backoff)
                    wait *= 0.5 + random.random() * 0.5
                    logger.warning("Connection error (attempt %d/%d) for %s, retry in %.1fs: %s", attempt + 1, self.max_retries, url, wait, exc)
                    await asyncio.sleep(wait)

        logger.error("All LLM attempts exhausted. Last error: %s", last_exc)
        raise last_exc or TransportError("All attempts exhausted")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Use granular timeouts: short connect, long read (waiting for LLM generation)
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.timeout_seconds),
                    write=30.0,
                    pool=10.0,
                )
            )
        return self._client

    def _candidate_urls(self) -> list[str]:
        """Build the list of URLs to try for chat-completion."""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]

        if _VERSION_PATH_RE.search(base):
            # Base URL already has a version path (e.g. /apis/v3).
            # Only append /chat/completions — prepending /v1 would create
            # a broken path like /v3/v1/chat/completions.
            return [f"{base}/chat/completions"]

        return [f"{base}/v1/chat/completions", f"{base}/chat/completions"]


# ---------------------------------------------------------------------------
# Environment-based factory
# ---------------------------------------------------------------------------

def build_client_from_env(
    timeout_seconds: int = 120,
    model_override: str | None = None,
) -> AsyncTransportClient | None:
    """Auto-detect LLM provider from environment variables.

    Detection order: ICA → OpenAI. Returns None for deterministic mode.
    """
    # --- IBM Cloud AI (ICA) ---
    ica_key = os.environ.get("ICA_API_KEY")
    ica_base = os.environ.get("ICA_BASE_URL")
    if ica_key and ica_base:
        ica_timeout = int(os.environ.get("ICA_TIMEOUT", "300"))
        ica_retries = int(os.environ.get("ICA_MAX_RETRIES", "5"))
        ica_max_backoff = int(os.environ.get("ICA_MAX_BACKOFF", "60"))
        logger.info("Detected ICA provider: base_url=%s timeout=%ds retries=%d", ica_base, ica_timeout, ica_retries)
        ica_model = model_override or os.environ.get(
            "ICA_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
        ica_tool_calling = os.environ.get("ICA_TOOL_CALLING", "false").lower() in (
            "true", "1", "yes",
        )
        return AsyncTransportClient(
            api_key=ica_key,
            base_url=ica_base,
            model=ica_model,
            provider="ica",
            ica_tool_calling=ica_tool_calling,
            timeout_seconds=ica_timeout,
            max_retries=ica_retries,
            max_backoff=ica_max_backoff,
        )

    # --- OpenAI ---
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        logger.info("Detected OpenAI provider")
        return AsyncTransportClient(
            api_key=openai_key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
            model=model_override or os.environ.get("OPENAI_MODEL", "gpt-4o"),
            provider="openai",
            timeout_seconds=timeout_seconds,
        )

    return None
