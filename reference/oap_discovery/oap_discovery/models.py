"""Pydantic v2 models for OAP v1.0 manifests and API types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Manifest models (v1.0 spec) ---


class InvokeSpec(BaseModel):
    method: str = Field(description="HTTP method (GET, POST) or 'stdio'")
    url: str = Field(description="Endpoint URL or command path for stdio")
    auth: str | None = None
    auth_url: str | None = None
    auth_in: str | None = Field(default=None, description="Where to send credentials: header or query")
    auth_name: str | None = Field(default=None, description="Header or query param name for the credential")
    headers: dict[str, str] | None = Field(default=None, description="Additional required headers as key-value pairs")
    streaming: bool | None = None


class IOSpec(BaseModel):
    format: str = Field(description="MIME type")
    description: str = Field(description="What this accepts or produces")
    schema_url: str | None = Field(default=None, alias="schema")


class Example(BaseModel):
    input: str | dict[str, Any] | None = None
    output: str | dict[str, Any] | None = None
    description: str | None = None


class Publisher(BaseModel):
    name: str | None = None
    contact: str | None = None
    url: str | None = None


class Manifest(BaseModel):
    """OAP v1.0 manifest. Four required fields: oap, name, description, invoke."""

    oap: str = Field(description="Protocol version")
    name: str = Field(description="Capability name")
    description: str = Field(description="Plain English description for LLM reasoning")
    invoke: InvokeSpec

    # Recommended but optional
    input: IOSpec | None = None
    output: IOSpec | None = None

    # Optional
    url: str | None = None
    publisher: Publisher | None = None
    examples: list[Example] | None = None
    tags: list[str] | None = None
    health: str | None = None
    docs: str | None = None
    version: str | None = None
    updated: str | None = None


# --- API request/response models ---


class DiscoverRequest(BaseModel):
    task: str = Field(description="Natural language task description", min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20, description="Number of candidates for vector search")


class DiscoverMatch(BaseModel):
    domain: str
    name: str
    description: str
    invoke: InvokeSpec
    score: float = Field(description="Vector similarity score (lower = more similar)")
    reason: str | None = Field(default=None, description="LLM reasoning for why this matches")


class LLMCallMeta(BaseModel):
    model: str
    prompt_tokens: int
    generated_tokens: int
    total_ms: float
    prompt: str | None = None
    system_prompt: str | None = None


class DiscoverMeta(BaseModel):
    embed: LLMCallMeta
    reason: LLMCallMeta | None = None
    search_results: int
    total_ms: float


class DiscoverResponse(BaseModel):
    task: str
    match: DiscoverMatch | None = None
    candidates: list[DiscoverMatch] = []
    meta: DiscoverMeta | None = None


class ManifestEntry(BaseModel):
    domain: str
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    index_count: int
