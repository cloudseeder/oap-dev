"""FastAPI router exposing OAP manifests as an OpenAPI 3.1 tool server.

Two endpoints turn the OAP discovery service into a standard OpenAPI tool
server consumable by Open WebUI, LangChain, or any OpenAPI-aware client:

  GET  /v1/openapi.json           — dynamically generated spec from all indexed manifests
  POST /v1/tools/call/{tool_name} — execution proxy that invokes the underlying manifest
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import ToolBridgeConfig
from .db import ManifestStore
from .ollama_client import OllamaClient
from .tool_api import EXEC_TOOL, EXEC_REGISTRY_ENTRY
from .tool_converter import manifest_to_tool
from .tool_executor import execute_exec_call, execute_tool_call
from .tool_models import ToolRegistryEntry

log = logging.getLogger("oap.openapi_server")

router = APIRouter(tags=["openapi-server"])

# Module-level state — set by api.py during lifespan initialization
_store: ManifestStore | None = None
_ollama: OllamaClient | None = None
_tool_bridge_cfg: ToolBridgeConfig | None = None
_credentials: dict[str, dict] = {}


class ToolCallResult(BaseModel):
    """Response from a tool execution."""
    result: str | None = None
    error: str | None = None


def _build_registry() -> dict[str, ToolRegistryEntry]:
    """Build a tool registry from all indexed manifests plus oap_exec."""
    registry: dict[str, ToolRegistryEntry] = {}

    if _store is None:
        return registry

    for entry in _store.list_domains():
        domain = entry["domain"]
        manifest = _store.get_manifest(domain)
        if manifest is None:
            continue
        try:
            reg_entry = manifest_to_tool(domain, manifest)
            tool_name = reg_entry.tool.function.name
            registry[tool_name] = reg_entry
        except Exception:
            log.warning("Failed to convert manifest %s", domain, exc_info=True)

    # Always include oap_exec
    registry[EXEC_TOOL.function.name] = EXEC_REGISTRY_ENTRY

    return registry


def _tool_parameters_to_schema(params) -> dict[str, Any]:
    """Convert ToolParameters to an OpenAPI JSON Schema object."""
    properties: dict[str, Any] = {}
    for name, param in params.properties.items():
        properties[name] = {
            "type": param.type,
            "description": param.description,
        }
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if params.required:
        schema["required"] = params.required
    return schema


@router.get("/v1/openapi.json")
async def openapi_spec() -> dict[str, Any]:
    """Dynamically generated OpenAPI 3.1 spec from all indexed manifests."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    registry = _build_registry()

    paths: dict[str, Any] = {}
    for tool_name, entry in registry.items():
        func = entry.tool.function
        schema = _tool_parameters_to_schema(func.parameters)

        paths[f"/v1/tools/call/{tool_name}"] = {
            "post": {
                "operationId": tool_name,
                "summary": entry.manifest.get("name", tool_name),
                "description": func.description,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": schema,
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Tool execution result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "result": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Tool not found"},
                    "500": {"description": "Execution error"},
                },
            }
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "OAP Tool Server",
            "description": (
                "OpenAPI tool server backed by OAP manifest discovery. "
                "Each endpoint corresponds to an OAP-discovered capability."
            ),
            "version": "1.0.0",
        },
        "paths": paths,
    }


@router.post("/v1/tools/call/{tool_name}")
async def call_tool(tool_name: str, arguments: dict[str, Any]) -> ToolCallResult:
    """Execute a tool by name with the given arguments."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    registry = _build_registry()

    if tool_name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tool '{tool_name}'. Available: {', '.join(sorted(registry.keys()))}",
        )

    cfg = _tool_bridge_cfg

    if tool_name == "oap_exec":
        command = arguments.get("command", "")
        if not command:
            return ToolCallResult(error="Missing required parameter: command")
        result = await execute_exec_call(
            command,
            stdin_text=arguments.get("stdin"),
            stdio_timeout=cfg.stdio_timeout if cfg else 10,
            ollama=_ollama,
            summarize_threshold=cfg.summarize_threshold if cfg else 16000,
            chunk_size=cfg.chunk_size if cfg else 6000,
            max_output=cfg.max_tool_result if cfg else 16000,
        )
    else:
        result = await execute_tool_call(
            tool_name,
            arguments,
            registry,
            http_timeout=cfg.http_timeout if cfg else 30,
            stdio_timeout=cfg.stdio_timeout if cfg else 10,
            credentials=_credentials,
            ollama=_ollama,
            summarize_threshold=cfg.summarize_threshold if cfg else 16000,
            chunk_size=cfg.chunk_size if cfg else 6000,
            max_output=cfg.max_tool_result if cfg else 16000,
        )

    if result.startswith("Error"):
        return ToolCallResult(error=result)

    return ToolCallResult(result=result)
