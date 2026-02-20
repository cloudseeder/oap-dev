"""Pydantic v2 models for Ollama tool bridge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Ollama tool definition schema ---


class ToolParameter(BaseModel):
    """A single parameter in a tool's JSON Schema."""

    type: str = "string"
    description: str = ""


class ToolParameters(BaseModel):
    """JSON Schema for tool parameters (Ollama format)."""

    type: str = "object"
    properties: dict[str, ToolParameter] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolFunction(BaseModel):
    """Ollama tool function definition."""

    name: str
    description: str
    parameters: ToolParameters


class Tool(BaseModel):
    """Ollama tool definition."""

    type: str = "function"
    function: ToolFunction


class ToolRegistryEntry(BaseModel):
    """Maps a tool name back to its domain + manifest for execution."""

    tool: Tool
    domain: str
    manifest: dict[str, Any]


# --- API request/response models ---


class ToolsRequest(BaseModel):
    """Request to discover tools for a task."""

    task: str = Field(description="Natural language task description", min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20, description="Number of tools to return")


class ToolsResponse(BaseModel):
    """Response with Ollama tool definitions."""

    tools: list[Tool] = Field(default_factory=list)
    registry: dict[str, ToolRegistryEntry] = Field(
        default_factory=dict,
        description="Tool name -> registry entry for execution",
    )


class ChatMessage(BaseModel):
    """Ollama chat message."""

    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    """Ollama-compatible chat request with OAP extensions."""

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    tools: list[Tool] | None = None

    # OAP extensions
    oap_discover: bool = Field(default=True, description="Enable OAP tool discovery")
    oap_top_k: int = Field(default=3, ge=1, le=20, description="Number of tools to discover")
    oap_auto_execute: bool = Field(default=True, description="Auto-execute tool calls")
    oap_max_rounds: int = Field(default=3, ge=1, le=10, description="Max tool call rounds")
