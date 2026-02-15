"""ChromaDB manifest store — upsert, search, list."""

from __future__ import annotations

import json
from typing import Any

import chromadb

from .config import ChromaDBConfig


class ManifestStore:
    """Wraps a ChromaDB PersistentClient for manifest storage.

    Embeddings are provided externally (from Ollama) — no default
    embedding function on the collection.
    """

    def __init__(self, cfg: ChromaDBConfig) -> None:
        self._client = chromadb.PersistentClient(path=cfg.path)
        # No embedding_function — we supply our own vectors
        self._collection = self._client.get_or_create_collection(
            name=cfg.collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_manifest(
        self,
        domain: str,
        manifest: dict[str, Any],
        embedding: list[float],
    ) -> None:
        """Insert or update a manifest with its embedding."""
        self._collection.upsert(
            ids=[domain],
            embeddings=[embedding],
            metadatas=[
                {
                    "name": manifest["name"],
                    "description": manifest["description"],
                    "manifest_json": json.dumps(manifest),
                    "invoke_method": manifest["invoke"]["method"],
                    "invoke_url": manifest["invoke"]["url"],
                    "tags": ",".join(manifest.get("tags") or []),
                }
            ],
            documents=[manifest["description"]],
        )

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for manifests by embedding similarity.

        Returns list of dicts with domain, name, description, manifest, score.
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self._collection.count() or 1),
            include=["metadatas", "distances", "documents"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        hits = []
        for i, domain in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            hits.append(
                {
                    "domain": domain,
                    "name": meta["name"],
                    "description": meta["description"],
                    "manifest": json.loads(meta["manifest_json"]),
                    "score": results["distances"][0][i],
                }
            )
        return hits

    def get_manifest(self, domain: str) -> dict[str, Any] | None:
        """Get a specific manifest by domain."""
        try:
            result = self._collection.get(ids=[domain], include=["metadatas"])
        except Exception:
            return None
        if not result["ids"]:
            return None
        meta = result["metadatas"][0]
        return json.loads(meta["manifest_json"])

    def list_domains(self) -> list[dict[str, str]]:
        """List all indexed domains with names."""
        result = self._collection.get(include=["metadatas"])
        entries = []
        for i, domain in enumerate(result["ids"]):
            meta = result["metadatas"][i]
            entries.append(
                {
                    "domain": domain,
                    "name": meta["name"],
                    "description": meta["description"],
                }
            )
        return entries

    def count(self) -> int:
        """Return number of indexed manifests."""
        return self._collection.count()
