"""
Custom exception hierarchy for the multi-agent pipeline.

Pattern: Define specific exception types so callers can catch and react
to different failure modes (agent logic error vs. external API failure
vs. validation rejection) without inspecting message strings.

# CUSTOMIZE: Add domain-specific exception types as your pipeline grows.
"""


class AgentError(Exception):
    """An agent failed to produce a valid result.

    Raise this when an agent's output cannot be parsed or doesn't meet
    the expected contract. The orchestration layer can then decide to
    retry, fall back to a deterministic path, or abort.
    """


class TransportError(Exception):
    """An LLM API call failed after all retries.

    Raise this for HTTP-level failures (timeouts, 5xx, auth errors).
    Callers should NOT retry — the transport layer has already exhausted
    its retry budget before raising this.
    """


class ValidationError(Exception):
    """A pipeline artifact failed deterministic validation.

    Raise this when a validator rejects output (e.g. missing fields,
    constraint violations). Carries structured failure codes so the
    agent can receive targeted feedback on what to fix.
    """

    def __init__(self, message: str, failures: list[str] | None = None):
        super().__init__(message)
        self.failures = failures or []
