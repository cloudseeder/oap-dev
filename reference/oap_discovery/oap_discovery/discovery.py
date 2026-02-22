"""Discovery engine — vector search + LLM reasoning."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .db import ManifestStore
from .models import DiscoverMatch, DiscoverMeta, DiscoverResponse, InvokeSpec, LLMCallMeta
from .ollama_client import OllamaClient

log = logging.getLogger("oap.discovery")

SYSTEM_PROMPT = """\
You are an OAP (Open Application Protocol) discovery assistant. Your job is to \
pick the single best capability manifest that matches a user's task.

You will be given a task and a numbered list of candidate manifests. Each candidate \
has a domain, name, and description.

Respond with ONLY a JSON object (no markdown, no extra text):
{"pick": "<domain>", "reason": "<one sentence explaining why this is the best match>"}

If none of the candidates match the task at all, respond:
{"pick": null, "reason": "<explanation>"}
"""


def _strip_think_blocks(text: str) -> str:
    """Remove qwen3 <think>...</think> blocks from response."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from text."""
    # Try the whole string first
    text = _strip_think_blocks(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON within the text
    match = re.search(r"\{[^{}]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _format_candidates(hits: list[dict[str, Any]]) -> str:
    """Format search hits for the LLM prompt."""
    lines = []
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. [{hit['domain']}] {hit['name']}")
        lines.append(f"   {hit['description']}")
        lines.append("")
    return "\n".join(lines)


class DiscoveryEngine:
    """Combines vector search with LLM reasoning for manifest discovery."""

    def __init__(self, store: ManifestStore, ollama: OllamaClient) -> None:
        self._store = store
        self._ollama = ollama

    async def discover(self, task: str, top_k: int = 10) -> DiscoverResponse:
        """Find the best manifest for a task.

        1. Embed the task as a query
        2. Vector search for top_k candidates
        3. LLM picks the best match and explains why
        """
        t0 = time.monotonic()

        # Step 1: Embed task
        query_embedding, embed_metrics = await self._ollama.embed_query(task)

        # Step 2: Vector search
        hits = self._store.search(query_embedding, n_results=top_k)

        if not hits:
            total_ms = (time.monotonic() - t0) * 1000
            meta = DiscoverMeta(
                embed=LLMCallMeta(
                    model=embed_metrics.model,
                    prompt_tokens=embed_metrics.prompt_tokens,
                    generated_tokens=0,
                    total_ms=embed_metrics.total_ms,
                ),
                search_results=0,
                total_ms=total_ms,
            )
            return DiscoverResponse(task=task, meta=meta)

        # Build candidate list for response
        candidates = [
            DiscoverMatch(
                domain=h["domain"],
                name=h["name"],
                description=h["description"],
                invoke=InvokeSpec.model_validate(h["manifest"]["invoke"]),
                score=h["score"],
            )
            for h in hits
        ]

        # Step 3: LLM reasoning
        prompt = f"Task: {task}\n\nCandidates:\n{_format_candidates(hits)}\n"
        reason_meta: LLMCallMeta | None = None

        try:
            raw, reason_metrics = await self._ollama.generate(
                prompt, system=SYSTEM_PROMPT, timeout=120.0,
                think=False, format="json",
            )
            reason_meta = LLMCallMeta(
                model=reason_metrics.model,
                prompt_tokens=reason_metrics.prompt_tokens,
                generated_tokens=reason_metrics.generated_tokens,
                total_ms=reason_metrics.total_ms,
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
            )
            parsed = _extract_json(raw)

            if parsed and parsed.get("pick"):
                pick_domain = parsed["pick"]
                reason = parsed.get("reason", "")

                # Find the picked candidate
                match = None
                for c in candidates:
                    if c.domain == pick_domain:
                        match = c
                        match.reason = reason
                        break

                if match:
                    total_ms = (time.monotonic() - t0) * 1000
                    meta = DiscoverMeta(
                        embed=LLMCallMeta(
                            model=embed_metrics.model,
                            prompt_tokens=embed_metrics.prompt_tokens,
                            generated_tokens=0,
                            total_ms=embed_metrics.total_ms,
                        ),
                        reason=reason_meta,
                        search_results=len(hits),
                        total_ms=total_ms,
                    )
                    log.info(
                        "discover task=%r embed=%dms llm=%dms tokens_in=%d tokens_out=%d",
                        task, embed_metrics.total_ms, reason_metrics.total_ms,
                        reason_metrics.prompt_tokens, reason_metrics.generated_tokens,
                    )
                    return DiscoverResponse(task=task, match=match, candidates=candidates, meta=meta)

            # LLM said no match
            if parsed and parsed.get("pick") is None:
                total_ms = (time.monotonic() - t0) * 1000
                meta = DiscoverMeta(
                    embed=LLMCallMeta(
                        model=embed_metrics.model,
                        prompt_tokens=embed_metrics.prompt_tokens,
                        generated_tokens=0,
                        total_ms=embed_metrics.total_ms,
                    ),
                    reason=reason_meta,
                    search_results=len(hits),
                    total_ms=total_ms,
                )
                return DiscoverResponse(task=task, candidates=candidates, meta=meta)

        except Exception:
            log.exception("LLM reasoning failed, falling back to top vector match")

        # Fallback: return top vector result
        total_ms = (time.monotonic() - t0) * 1000
        meta = DiscoverMeta(
            embed=LLMCallMeta(
                model=embed_metrics.model,
                prompt_tokens=embed_metrics.prompt_tokens,
                generated_tokens=0,
                total_ms=embed_metrics.total_ms,
            ),
            reason=reason_meta,
            search_results=len(hits),
            total_ms=total_ms,
        )
        fallback = candidates[0]
        fallback.reason = "Selected by vector similarity (LLM reasoning unavailable)"
        return DiscoverResponse(task=task, match=fallback, candidates=candidates, meta=meta)
