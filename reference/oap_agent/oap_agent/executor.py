"""HTTP executor — sends chat requests to the OAP discovery service."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .config import EscalationConfig

log = logging.getLogger("oap.agent.executor")

_PROVIDER_KEY_VARS = {
    "openai": "OAP_OPENAI_API_KEY",
    "anthropic": "OAP_ANTHROPIC_API_KEY",
    "googleai": "OAP_GOOGLEAI_API_KEY",
}


def _get_api_key(config: EscalationConfig) -> str:
    """Resolve API key: config > OAP_ESCALATION_API_KEY > provider-specific env var."""
    if config.api_key:
        return config.api_key
    override = os.environ.get("OAP_ESCALATION_API_KEY", "")
    if override:
        return override
    provider_var = _PROVIDER_KEY_VARS.get(config.provider, "")
    return os.environ.get(provider_var, "") if provider_var else ""


async def execute_chat(
    discovery_url: str,
    messages: list[dict],
    model: str = "qwen3:8b",
    timeout: int = 300,
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
    escalation_usage: dict | None = None

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

    escalation_usage = raw.get("oap_escalation_usage")
    chat_usage = raw.get("oap_usage")

    # When the LLM spent all rounds on tool calls with no text summary,
    # use the last tool result as the response content
    if not content.strip() and tool_calls:
        for tc in reversed(tool_calls):
            result = tc.get("result", "")
            if result and not result.startswith("Error"):
                content = result
                break

    return {
        "content": content,
        "tool_calls": tool_calls,
        "experience_cache": experience_cache,
        "escalation_usage": escalation_usage,
        "chat_usage": chat_usage,
        "raw": raw,
    }


async def execute_conversational(
    discovery_url: str,
    messages: list[dict],
    model: str = "qwen3:8b",
    timeout: int = 300,
) -> dict[str, Any]:
    """Send a conversational (no-tool) chat request via the tool bridge.

    Passes oap_discover=false so the tool bridge skips fingerprinting,
    discovery, tool injection, and system prompt rewriting.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "oap_discover": False,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{discovery_url}/v1/chat", json=payload)
        resp.raise_for_status()
        raw = resp.json()

    content = ""
    message = raw.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")

    return {
        "content": content,
        "tool_calls": [],
        "experience_cache": None,
        "raw": raw,
    }


async def execute_escalated(
    messages: list[dict],
    config: EscalationConfig,
) -> dict[str, Any] | None:
    """Send a conversational request directly to a big LLM.

    Used when Ollama is busy with a background task and the message
    doesn't need tools. Returns None on any failure so the caller
    can fall back to cancelling the task and using Ollama.
    """
    api_key = _get_api_key(config)
    if not api_key:
        log.warning("Escalation skipped — no API key")
        return None

    try:
        if config.provider == "anthropic":
            result = await _call_anthropic_chat(messages, api_key, config)
        else:
            result = await _call_openai_chat(messages, api_key, config)
        if result:
            log.info("Escalated conversational response to %s/%s", config.provider, config.model)
        return result
    except Exception:
        log.exception("Conversational escalation failed — will fall back to Ollama")
        return None


async def _call_openai_chat(
    messages: list[dict],
    api_key: str,
    config: EscalationConfig,
) -> dict[str, Any] | None:
    base_url = config.base_url or "https://api.openai.com/v1"
    url = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=config.timeout) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": config.max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return {
            "content": data["choices"][0]["message"]["content"],
            "tool_calls": [],
            "experience_cache": None,
            "escalation_usage": {
                "model": config.model,
                "provider": "openai",
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            "raw": data,
        }


async def _call_anthropic_chat(
    messages: list[dict],
    api_key: str,
    config: EscalationConfig,
) -> dict[str, Any] | None:
    base_url = config.base_url or "https://api.anthropic.com"
    url = f"{base_url.rstrip('/')}/v1/messages"

    # Anthropic takes system as a top-level param, not in messages
    system_prompt = ""
    api_messages = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            api_messages.append(m)

    payload: dict[str, Any] = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "messages": api_messages,
        "temperature": 0.5,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=config.timeout) as client:
        resp = await client.post(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        text = None
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break
        if text is None:
            return None
        return {
            "content": text,
            "tool_calls": [],
            "experience_cache": None,
            "escalation_usage": {
                "model": config.model,
                "provider": "anthropic",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
            "raw": data,
        }


async def execute_task(
    discovery_url: str,
    prompt: str,
    model: str = "qwen3:8b",
    timeout: int = 300,
    debug: bool = True,
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
