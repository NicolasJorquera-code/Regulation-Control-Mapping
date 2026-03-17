"""Embedding abstraction for ControlNexus.

Wraps sentence-transformers behind a protocol so tests can inject a mock.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder(ABC):
    """Abstract embedder protocol."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...


class SentenceTransformerEmbedder(Embedder):
    """Production embedder using sentence-transformers.

    Uses all-MiniLM-L6-v2 (384-dim) by default — fast inference,
    good quality for short text (30-80 words).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]

    def dimension(self) -> int:
        return self._dim
