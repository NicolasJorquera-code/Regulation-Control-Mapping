"""Custom exception hierarchy for the regulatory obligation mapping pipeline."""


class RegRiskError(Exception):
    """Base exception for the regrisk pipeline."""


class IngestError(RegRiskError):
    """Data ingestion failed -- file not found, parse error, or schema mismatch."""


class TransportError(RegRiskError):
    """An LLM API call failed after all retries."""


class ValidationError(RegRiskError):
    """An LLM-produced artifact failed AI governance validation."""


class LLMRequiredError(RegRiskError):
    """The pipeline was invoked without a configured LLM client.

    regrisk is an LLM-driven pipeline; every agent requires a working
    transport client. Configure ICA_API_KEY or OPENAI_API_KEY in your
    environment (see ``.env.example``) before running the pipeline.
    """
