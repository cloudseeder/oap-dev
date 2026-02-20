"""FastAPI router for Ollama tool bridge endpoints."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from .config import OllamaConfig, ToolBridgeConfig, load_credentials
from .discovery import DiscoveryEngine
from .db import ManifestStore
from .tool_converter import manifest_to_tool
from .tool_executor import execute_tool_call
from .tool_models import (
    ChatMessage,
    ChatRequest,
    Tool,
    ToolRegistryEntry,
    ToolsRequest,
    ToolsResponse,
)

log = logging.getLogger("oap.tool_api")

router = APIRouter(tags=["tool-bridge"])

# Set by api.py during lifespan initialization
_engine: DiscoveryEngine | None = None
_store: ManifestStore | None = None
_ollama_cfg: OllamaConfig | None = None
_tool_bridge_cfg: ToolBridgeConfig | None = None


def _require_enabled() -> tuple[DiscoveryEngine, ManifestStore, OllamaConfig, ToolBridgeConfig]:
    """Raise 503 if the tool bridge is not initialized."""
    if _engine is None or _store is None or _ollama_cfg is None or _tool_bridge_cfg is None:
        raise HTTPException(
            status_code=503,
            detail="Tool bridge is not enabled. Set tool_bridge.enabled: true in config.",
        )
    if not _tool_bridge_cfg.enabled:
        raise HTTPException(
            status_code=503,
            detail="Tool bridge is disabled in configuration.",
        )
    return _engine, _store, _ollama_cfg, _tool_bridge_cfg


async def _discover_tools(
    engine: DiscoveryEngine,
    store: ManifestStore,
    task: str,
    top_k: int,
) -> tuple[list[Tool], dict[str, ToolRegistryEntry]]:
    """Run discovery and convert results to Ollama tools."""
    result = await engine.discover(task, top_k=top_k)

    tools: list[Tool] = []
    registry: dict[str, ToolRegistryEntry] = {}

    # Collect all candidate domains
    domains = set()
    if result.match:
        domains.add(result.match.domain)
    for c in result.candidates:
        domains.add(c.domain)

    for domain in domains:
        manifest = store.get_manifest(domain)
        if manifest is None:
            continue
        entry = manifest_to_tool(domain, manifest)
        tools.append(entry.tool)
        registry[entry.tool.function.name] = entry

    return tools, registry


@router.post("/v1/tools", response_model=ToolsResponse)
async def discover_tools(req: ToolsRequest) -> ToolsResponse:
    """Discover manifests for a task and return as Ollama tool definitions."""
    engine, store, _, _ = _require_enabled()
    tools, registry = await _discover_tools(engine, store, req.task, req.top_k)
    return ToolsResponse(tools=tools, registry=registry)


@router.post("/v1/chat")
async def chat_proxy(req: ChatRequest) -> dict[str, Any]:
    """Transparent Ollama proxy with OAP tool discovery.

    1. Extract task from the last user message
    2. Discover tools via OAP
    3. Merge with any client-provided tools
    4. Forward to Ollama /api/chat
    5. If tool_calls, execute via invoker and loop
    6. Return final response with metadata
    """
    engine, store, ollama_cfg, bridge_cfg = _require_enabled()

    max_rounds = min(req.oap_max_rounds, bridge_cfg.max_rounds)
    tools: list[Tool] = []
    registry: dict[str, ToolRegistryEntry] = {}

    # Discover tools from the last user message
    if req.oap_discover:
        last_user_msg = ""
        for msg in reversed(req.messages):
            if msg.role == "user" and msg.content:
                last_user_msg = msg.content
                break

        if last_user_msg:
            tools, registry = await _discover_tools(
                engine, store, last_user_msg, req.oap_top_k,
            )

    # Merge client-provided tools
    if req.tools:
        tools.extend(req.tools)

    # Build Ollama request
    messages = [m.model_dump(exclude_none=True) for m in req.messages]

    for round_num in range(max_rounds):
        ollama_payload: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            ollama_payload["tools"] = [t.model_dump() for t in tools]

        # Forward to Ollama
        try:
            async with httpx.AsyncClient(timeout=bridge_cfg.ollama_timeout) as client:
                resp = await client.post(
                    f"{ollama_cfg.base_url.rstrip('/')}/api/chat",
                    json=ollama_payload,
                )
                resp.raise_for_status()
                ollama_resp = resp.json()
        except httpx.HTTPStatusError as e:
            log.error("Ollama HTTP %d: %s", e.response.status_code, e.response.text[:500])
            raise HTTPException(
                status_code=502,
                detail=f"Ollama returned HTTP {e.response.status_code}",
            )
        except httpx.HTTPError as e:
            log.exception("Ollama request failed")
            raise HTTPException(status_code=502, detail=f"Ollama request failed: {type(e).__name__}: {e}")

        # Check for tool calls
        resp_message = ollama_resp.get("message", {})
        tool_calls = resp_message.get("tool_calls")

        if not tool_calls or not req.oap_auto_execute:
            # No tool calls or auto-execute disabled — return as-is
            ollama_resp["oap_tools_injected"] = len(registry)
            ollama_resp["oap_round"] = round_num + 1
            return ollama_resp

        # Execute tool calls
        log.info("Round %d: executing %d tool call(s)", round_num + 1, len(tool_calls))

        # Append assistant message with tool calls
        messages.append(resp_message)

        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = fn.get("arguments", {})

            result_str = await execute_tool_call(
                tool_name,
                tool_args,
                registry,
                http_timeout=bridge_cfg.http_timeout,
                stdio_timeout=bridge_cfg.stdio_timeout,
                credentials=load_credentials(bridge_cfg.credentials_file),
            )

            # Append tool result message
            messages.append({
                "role": "tool",
                "content": result_str,
            })

    # Max rounds exceeded — return last response
    ollama_resp["oap_tools_injected"] = len(registry)
    ollama_resp["oap_round"] = max_rounds
    return ollama_resp
