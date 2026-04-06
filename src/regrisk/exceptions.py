"""Custom exception hierarchy for the regulatory obligation mapping pipeline."""


class RegRiskError(Exception):
    """Base exception for the regrisk pipeline."""


class IngestError(RegRiskError):
    """Data ingestion failed — file not found, parse error, or schema mismatch."""


class AgentError(RegRiskError):
    """An agent failed to produce a valid result."""


class TransportError(RegRiskError):
    """An LLM API call failed after all retries."""


class ValidationError(RegRiskError):
    """A pipeline artifact failed deterministic validation."""
