"""Custom exceptions for the ControlNexus pipeline."""


class AgentExecutionException(Exception):
    """Raised when an agent fails to produce a valid result."""


class ExternalServiceException(Exception):
    """Raised when an external service (LLM API) call fails."""


class ValidationException(Exception):
    """Raised when a control fails deterministic validation."""
