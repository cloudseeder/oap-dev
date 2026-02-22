"""Async Ollama client for embeddings and generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .config import OllamaConfig

log = logging.getLogger("oap.ollama")


@dataclass
class OllamaMetrics:
    """Telemetry extracted from an Ollama response."""

    model: str
    prompt_tokens: int
    generated_tokens: int
    total_ms: float
    eval_ms: float


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

    async def embed(self, text: str, *, prefix: str = "search_document: ") -> tuple[list[float], OllamaMetrics]:
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
        metrics = OllamaMetrics(
            model=data.get("model", self._cfg.embed_model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            generated_tokens=0,
            total_ms=data.get("total_duration", 0) / 1_000_000,
            eval_ms=0,
        )
        log.info("ollama embed model=%s tokens=%d ms=%.0f", metrics.model, metrics.prompt_tokens, metrics.total_ms)
        return data["embeddings"][0], metrics

    async def embed_query(self, text: str) -> tuple[list[float], OllamaMetrics]:
        """Embed a search query (uses search_query prefix)."""
        return await self.embed(text, prefix="search_query: ")

    async def embed_document(self, text: str) -> tuple[list[float], OllamaMetrics]:
        """Embed a document for storage (uses search_document prefix)."""
        return await self.embed(text, prefix="search_document: ")

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        timeout: float = 60.0,
        think: bool | None = None,
    ) -> tuple[str, OllamaMetrics]:
        """Generate text using the configured generation model.

        Returns the raw response text (may contain <think> blocks from qwen3)
        and metrics extracted from the Ollama response.
        Set think=False to disable qwen3's thinking chain.
        """
        payload: dict = {
            "model": self._cfg.generate_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": self._cfg.num_ctx},
            "keep_alive": self._cfg.keep_alive,
        }
        if think is not None:
            payload["think"] = think
        if system:
            payload["system"] = system

        resp = await self._client.post(
            f"{self._base}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        metrics = OllamaMetrics(
            model=data.get("model", self._cfg.generate_model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            generated_tokens=data.get("eval_count", 0),
            total_ms=data.get("total_duration", 0) / 1_000_000,
            eval_ms=data.get("eval_duration", 0) / 1_000_000,
        )
        log.info(
            "ollama generate model=%s tokens_in=%d tokens_out=%d ms=%.0f",
            metrics.model, metrics.prompt_tokens, metrics.generated_tokens, metrics.total_ms,
        )
        return data["response"], metrics

    async def chat(
        self,
        user_msg: str,
        *,
        system: str | None = None,
        timeout: float = 60.0,
        think: bool | None = None,
        temperature: float | None = None,
        format: str | None = None,
    ) -> tuple[str, OllamaMetrics]:
        """Chat using the configured generation model.

        Uses /api/chat so the model's chat template is applied.
        Set think=False to disable qwen3's thinking chain.
        Set temperature=0 for deterministic output.
        Set format="json" to constrain output to valid JSON only.
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_msg})

        options: dict = {"num_ctx": self._cfg.num_ctx}
        if temperature is not None:
            options["temperature"] = temperature

        payload: dict = {
            "model": self._cfg.generate_model,
            "messages": messages,
            "stream": False,
            "options": options,
            "keep_alive": self._cfg.keep_alive,
        }
        if think is not None:
            payload["think"] = think
        if format is not None:
            payload["format"] = format

        resp = await self._client.post(
            f"{self._base}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        metrics = OllamaMetrics(
            model=data.get("model", self._cfg.generate_model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            generated_tokens=data.get("eval_count", 0),
            total_ms=data.get("total_duration", 0) / 1_000_000,
            eval_ms=data.get("eval_duration", 0) / 1_000_000,
        )
        content = data.get("message", {}).get("content", "")
        log.info(
            "ollama chat model=%s tokens_in=%d tokens_out=%d ms=%.0f",
            metrics.model, metrics.prompt_tokens, metrics.generated_tokens, metrics.total_ms,
        )
        return content, metrics
