"""Pydantic v2 models for procedural memory experience records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .models import DiscoverMatch


# --- Experience record models ---


class IntentRecord(BaseModel):
    """Captured intent from the original task."""

    raw: str = Field(description="Original natural language task text")
    fingerprint: str = Field(
        description="Hierarchical category, e.g. 'query.zoning.parcel_lookup'"
    )
    domain: str = Field(description="Broad domain, e.g. 'civic.land_use'")


class DiscoveryRecord(BaseModel):
    """How the manifest was discovered."""

    query_used: str = Field(description="Query sent to vector search")
    manifest_matched: str = Field(description="Domain of the matched manifest")
    manifest_version: str | None = Field(
        default=None, description="Manifest version at time of match"
    )
    confidence: float = Field(description="Discovery confidence score (0-1)")


class ParameterMapping(BaseModel):
    """How one parameter was extracted and transformed."""

    source: str = Field(
        description="Where the value came from, e.g. 'intent.entity.parcel_number'"
    )
    transform: str | None = Field(
        default=None, description="Transform applied, e.g. 'remove_hyphens'"
    )
    value_used: str = Field(description="Actual value sent in the invocation")


class InvocationRecord(BaseModel):
    """How the capability was invoked."""

    endpoint: str = Field(description="URL path or command used")
    method: str = Field(description="HTTP method or 'stdio'")
    parameter_mapping: dict[str, ParameterMapping] = Field(
        default_factory=dict,
        description="Parameter name -> mapping details",
    )
    headers_required: list[str] = Field(
        default_factory=list,
        description="Headers needed (templates, not actual secrets)",
    )


class CorrectionEntry(BaseModel):
    """A failed attempt and its fix."""

    attempted: str = Field(description="What was tried")
    error: str = Field(description="Error received")
    fix: str = Field(description="What fixed it")


class OutcomeRecord(BaseModel):
    """Result of the invocation."""

    status: str = Field(description="'success' or 'failure'")
    http_code: int | None = Field(
        default=None, description="HTTP response code if applicable"
    )
    response_summary: str = Field(
        description="Brief summary of what was returned"
    )
    latency_ms: int | None = Field(
        default=None, description="Round-trip time in milliseconds"
    )


class ExperienceRecord(BaseModel):
    """Complete procedural memory record for one manifest interaction."""

    id: str = Field(description="Unique ID, e.g. 'exp_20260219_a3f7b2c1'")
    timestamp: datetime = Field(description="When this record was created")
    use_count: int = Field(
        default=1, description="How many times this pattern has been used"
    )
    last_used: datetime = Field(description="When this pattern was last used")

    intent: IntentRecord
    discovery: DiscoveryRecord
    invocation: InvocationRecord
    outcome: OutcomeRecord
    corrections: list[CorrectionEntry] = Field(default_factory=list)


# --- API request/response models ---


class ExperienceInvokeRequest(BaseModel):
    """Request to the experience-augmented invoke endpoint."""

    task: str = Field(description="Natural language task description", min_length=1, max_length=2000)
    top_k: int = Field(
        default=5, ge=1, le=20, description="Candidates for vector search if needed"
    )
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to use cache without re-discovery",
    )


class ExperienceRoute(BaseModel):
    """Which path the engine took."""

    path: str = Field(
        description="'cache_hit', 'partial_match', or 'full_discovery'"
    )
    cache_confidence: float | None = Field(
        default=None, description="Confidence of cache match if any"
    )
    experience_id: str | None = Field(
        default=None, description="ID of experience record used or created"
    )


class InvocationResult(BaseModel):
    """Result of actually executing an invocation."""

    status: str = Field(description="'success' or 'failure'")
    http_code: int | None = Field(default=None)
    response_body: str = Field(default="", description="Truncated response content")
    latency_ms: int = Field(default=0)
    error: str | None = Field(default=None, description="Error message if failed")


class ExperienceInvokeResponse(BaseModel):
    """Response from the experience-augmented endpoint."""

    task: str
    route: ExperienceRoute
    match: DiscoverMatch | None = None
    experience: ExperienceRecord | None = Field(
        default=None, description="Experience record used or created"
    )
    invocation_result: InvocationResult | None = Field(
        default=None, description="Result of executing the invocation"
    )
    candidates: list[DiscoverMatch] = []
