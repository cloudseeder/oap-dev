"""HTTP executor — sends chat requests to the OAP discovery service."""

from __future__ import annotations

import logging
from typing import Any

import httpx


log = logging.getLogger("oap.agent.executor")


async def execute_chat(
    discovery_url: str,
    messages: list[dict],
    model: str = "qwen3:8b",
    timeout: int = 120,
    debug: bool = True,
) -> dict[str, Any]:
    """Send a chat request to the OAP discovery service.

    Returns a dict with:
      - content: str — assistant reply text
      - tool_calls: list — tool executions from debug trace
      - experience_cache: str | None — hit/miss/degraded metadata
      - raw: dict — full parsed response
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "oap_debug": debug,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{discovery_url}/v1/chat", json=payload)
        resp.raise_for_status()
        raw = resp.json()

    content = ""
    tool_calls: list[dict] = []
    experience_cache: str | None = None

    # Extract content from Ollama-style response
    message = raw.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")

    # Extract tool calls from debug trace
    if debug and "oap_debug" in raw:
        dbg = raw["oap_debug"]
        for round_info in dbg.get("rounds", []):
            for te in round_info.get("tool_executions", []):
                tool_calls.append({
                    "tool": te.get("tool"),
                    "args": te.get("arguments"),
                    "result": te.get("result"),
                    "duration_ms": te.get("duration_ms"),
                })
        experience_cache = dbg.get("experience_cache")

    return {
        "content": content,
        "tool_calls": tool_calls,
        "experience_cache": experience_cache,
        "raw": raw,
    }


async def execute_task(
    discovery_url: str,
    prompt: str,
    model: str = "qwen3:8b",
    timeout: int = 120,
    debug: bool = False,
) -> dict[str, Any]:
    """Wrap a single prompt as a user message and execute via chat."""
    messages = [{"role": "user", "content": prompt}]
    return await execute_chat(
        discovery_url=discovery_url,
        messages=messages,
        model=model,
        timeout=timeout,
        debug=debug,
    )
