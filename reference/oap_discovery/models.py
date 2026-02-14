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
    task: str = Field(description="Natural language task description")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of candidates for vector search")


class DiscoverMatch(BaseModel):
    domain: str
    name: str
    description: str
    invoke: InvokeSpec
    score: float = Field(description="Vector similarity score (lower = more similar)")
    reason: str | None = Field(default=None, description="LLM reasoning for why this matches")


class DiscoverResponse(BaseModel):
    task: str
    match: DiscoverMatch | None = None
    candidates: list[DiscoverMatch] = []


class ManifestEntry(BaseModel):
    domain: str
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    index_count: int
