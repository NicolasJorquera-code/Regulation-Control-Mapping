"""ChromaDB-backed control memory store.

Provides nearest-neighbor retrieval, semantic deduplication, and
historical run comparison for the ControlNexus pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb

from controlnexus.memory.embedder import Embedder

logger = logging.getLogger(__name__)


class ControlMemory:
    """Vector memory store for control descriptions.

    One ChromaDB collection per organization: ``controls_{bank_id}``.
    Each document is a control's ``full_description`` with metadata
    for section_id, control_type, business_unit_id, and run_id.
    """

    def __init__(
        self,
        embedder: Embedder,
        chroma_client: chromadb.ClientAPI | None = None,
    ) -> None:
        """Initialise with an embedder and optional ChromaDB client."""
        self._embedder = embedder
        self._client = chroma_client or chromadb.Client()

    def _collection_name(self, bank_id: str) -> str:
        return f"controls_{bank_id}"

    def _get_or_create_collection(self, bank_id: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=self._collection_name(bank_id),
            metadata={"hnsw:space": "cosine"},
        )

    def index_controls(
        self,
        bank_id: str,
        records: list[dict[str, Any]],
        run_id: str = "",
    ) -> int:
        """Index control records into the vector store.

        Args:
            bank_id: Organization identifier.
            records: List of dicts with at least 'control_id' and
                     'full_description'. Optional: 'hierarchy_id',
                     'selected_level_2', 'business_unit_id'.
            run_id: Run identifier for historical tracking.

        Returns:
            Number of records indexed.
        """
        if not records:
            return 0

        collection = self._get_or_create_collection(bank_id)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []

        for rec in records:
            doc = rec.get("full_description", "")
            if not doc:
                continue

            ctrl_id = rec.get("control_id", "")
            hierarchy_id = rec.get("hierarchy_id", "")
            section_id = hierarchy_id.split(".")[0] + ".0" if hierarchy_id else ""

            ids.append(ctrl_id)
            documents.append(doc)
            metadatas.append(
                {
                    "section_id": section_id,
                    "control_type": rec.get("selected_level_2", "") or rec.get("control_type", ""),
                    "business_unit_id": rec.get("business_unit_id", ""),
                    "run_id": run_id,
                    "hierarchy_id": hierarchy_id,
                }
            )

        if not documents:
            return 0

        embeddings = self._embedder.embed(documents)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Indexed %d controls for bank %s (run %s)", len(ids), bank_id, run_id)
        return len(ids)

    def query_similar(
        self,
        bank_id: str,
        text: str,
        n: int = 5,
        section_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find controls similar to the given text.

        Args:
            bank_id: Organization identifier.
            text: Query text (typically a full_description).
            n: Number of results to return.
            section_filter: Optional section_id to filter by (e.g. "4.0").

        Returns:
            List of dicts with 'document', 'score', 'metadata', 'id'.
        """
        collection = self._get_or_create_collection(bank_id)

        if collection.count() == 0:
            return []

        embedding = self._embedder.embed([text])[0]

        where_filter = None
        if section_filter:
            where_filter = {"section_id": section_filter}

        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(n, collection.count()),
            where=where_filter,
            include=["documents", "distances", "metadatas"],
        )

        matches: list[dict[str, Any]] = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns cosine distance; similarity = 1 - distance
                distance = results["distances"][0][i] if results["distances"] else 0
                matches.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i] if results["documents"] else "",
                        "score": round(1 - distance, 4),
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    }
                )

        return matches

    def check_duplicate(
        self,
        bank_id: str,
        text: str,
        threshold: float = 0.92,
    ) -> tuple[bool, str | None]:
        """Check if text is a near-duplicate of an existing control.

        Args:
            bank_id: Organization identifier.
            text: Full description to check.
            threshold: Cosine similarity threshold (default 0.92).

        Returns:
            (is_duplicate, existing_control_id or None)
        """
        matches = self.query_similar(bank_id, text, n=1)
        if matches and matches[0]["score"] >= threshold:
            return True, matches[0]["id"]
        return False, None

    def compare_runs(
        self,
        bank_id: str,
        run_id_a: str,
        run_id_b: str,
    ) -> dict[str, Any]:
        """Compare two runs by counting controls and checking overlap.

        Returns dict with counts and overlap metrics.
        """
        collection = self._get_or_create_collection(bank_id)

        results_a = collection.get(where={"run_id": run_id_a}, include=["documents"])
        results_b = collection.get(where={"run_id": run_id_b}, include=["documents"])

        count_a = len(results_a["ids"]) if results_a["ids"] else 0
        count_b = len(results_b["ids"]) if results_b["ids"] else 0

        ids_a = set(results_a["ids"]) if results_a["ids"] else set()
        ids_b = set(results_b["ids"]) if results_b["ids"] else set()
        overlap = ids_a & ids_b

        return {
            "run_a_count": count_a,
            "run_b_count": count_b,
            "overlap_count": len(overlap),
            "new_in_b": count_b - len(overlap),
            "removed_from_a": count_a - len(overlap),
        }

    def clear(self, bank_id: str) -> None:
        """Delete the entire collection for a bank."""
        try:
            self._client.delete_collection(self._collection_name(bank_id))
            logger.info("Cleared collection for bank %s", bank_id)
        except Exception:
            logger.debug("Collection for bank %s not found, nothing to clear", bank_id)
