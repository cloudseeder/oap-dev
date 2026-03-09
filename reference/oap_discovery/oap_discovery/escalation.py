"""Escalate final reasoning to an external big LLM (Claude, GPT-4, etc.).

The small local model (qwen3:8b) handles tool discovery and execution.
For tasks matching escalate_prefixes, this module sends the tool results
to a big LLM for the final reasoning step — getting correct arithmetic,
unit conversions, and multi-step logic that small models struggle with.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from .config import EscalationConfig

log = logging.getLogger("oap.escalation")

_BASE_SYSTEM_PROMPT = (
    "Answer the user's question using ONLY the tool execution results below. "
    "FACTUAL ACCURACY IS MANDATORY — never embellish, exaggerate, or infer data "
    "that is not in the results. Use the provided current date for all date "
    "calculations — never guess today's date. If a tool returned an error or was not called, "
    "say so — never pretend an action succeeded when it didn't. "
    "Verify all arithmetic, dates, and calculations before responding. "
    "FORMAT: Use short plain text or simple markdown lists. No tables, no emoji "
    "section headers, no dramatic formatting. Keep it scannable and brief — "
    "a few lines, not a page."
)


def _format_tool_results(tool_results: list[dict]) -> str:
    """Format tool results into a readable block for the big LLM."""
    parts = []
    for i, tr in enumerate(tool_results, 1):
        parts.append(f"Tool call {i}: {tr.get('tool', 'unknown')}({tr.get('arguments', {})})")
        parts.append(f"Result: {tr.get('result', '(no output)')}")
        parts.append("")
    return "\n".join(parts)


_PROVIDER_KEY_VARS = {
    "openai": "OAP_OPENAI_API_KEY",
    "anthropic": "OAP_ANTHROPIC_API_KEY",
    "googleai": "OAP_GOOGLEAI_API_KEY",
}


def _get_api_key(config: EscalationConfig) -> str:
    """Resolve API key: config.api_key > OAP_ESCALATION_API_KEY > provider-specific env var."""
    if config.api_key:
        return config.api_key
    override = os.environ.get("OAP_ESCALATION_API_KEY", "")
    if override:
        return override
    provider_var = _PROVIDER_KEY_VARS.get(config.provider, "")
    return os.environ.get(provider_var, "") if provider_var else ""


async def escalate(
    user_message: str,
    tool_results: list[dict],
    config: EscalationConfig,
    persona: str = "",
) -> str | None:
    """Send tool results to a big LLM for final reasoning.

    Returns the response text, or None on any failure (timeout, auth, network).
    Failures are logged but never raised — the caller falls back to the small
    LLM's response.
    """
    api_key = _get_api_key(config)
    if not api_key:
        log.warning("Escalation skipped — no API key (set OAP_ESCALATION_API_KEY)")
        return None

    system_prompt = _BASE_SYSTEM_PROMPT
    if persona:
        system_prompt = (
            f"{persona} Respond in character, but NEVER let the persona alter facts. "
            "The persona affects tone and style only — dates, counts, statuses, and "
            "outcomes must be reported exactly as they appear in the tool results.\n\n"
            f"{system_prompt}"
        )

    today = datetime.now(timezone.utc).strftime("%A, %B %-d, %Y")
    formatted_results = _format_tool_results(tool_results)
    user_content = f"Today is {today}.\n\n{user_message}\n\n--- Tool execution results ---\n{formatted_results}"

    try:
        if config.provider == "anthropic":
            return await _call_anthropic(user_content, api_key, config, system_prompt)
        else:
            # OpenAI-compatible (covers OpenAI, OpenRouter, Groq, etc.)
            return await _call_openai(user_content, api_key, config, system_prompt)
    except Exception:
        log.exception("Escalation failed — falling back to small LLM response")
        return None


async def _call_openai(
    user_content: str,
    api_key: str,
    config: EscalationConfig,
    system_prompt: str = "",
) -> str | None:
    """Call an OpenAI-compatible chat completions endpoint."""
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
                "messages": [
                    {"role": "system", "content": system_prompt or _BASE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
                "max_tokens": config.max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(
    user_content: str,
    api_key: str,
    config: EscalationConfig,
    system_prompt: str = "",
) -> str | None:
    """Call the Anthropic Messages API."""
    base_url = config.base_url or "https://api.anthropic.com"
    url = f"{base_url.rstrip('/')}/v1/messages"

    async with httpx.AsyncClient(timeout=config.timeout) as client:
        resp = await client.post(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "max_tokens": config.max_tokens,
                "system": system_prompt or _BASE_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        # Anthropic returns content as a list of blocks
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return None
