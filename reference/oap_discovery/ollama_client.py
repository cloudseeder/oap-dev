"""Async Ollama client for embeddings and generation."""

from __future__ import annotations

import httpx

from .config import OllamaConfig


class OllamaClient:
    """Async wrapper around the Ollama HTTP API."""

    def __init__(self, cfg: OllamaConfig) -> None:
        self._cfg = cfg
        self._base = cfg.base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=cfg.timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def healthy(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            resp = await self._client.get(f"{self._base}/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def embed(self, text: str, *, prefix: str = "search_document: ") -> list[float]:
        """Embed text using the configured embedding model.

        nomic-embed-text requires prefixes:
        - "search_document: " for documents being stored
        - "search_query: " for queries being searched
        """
        resp = await self._client.post(
            f"{self._base}/api/embed",
            json={
                "model": self._cfg.embed_model,
                "input": f"{prefix}{text}",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"][0]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (uses search_query prefix)."""
        return await self.embed(text, prefix="search_query: ")

    async def embed_document(self, text: str) -> list[float]:
        """Embed a document for storage (uses search_document prefix)."""
        return await self.embed(text, prefix="search_document: ")

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Generate text using the configured generation model.

        Returns the raw response text (may contain <think> blocks from qwen3).
        """
        payload: dict = {
            "model": self._cfg.generate_model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        resp = await self._client.post(
            f"{self._base}/api/generate",
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["response"]
