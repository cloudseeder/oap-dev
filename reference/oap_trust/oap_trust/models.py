"""Pydantic v2 models for trust provider API types."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field


# --- Enums ---


class TrustLayer(IntEnum):
    UNVERIFIED = 0
    DOMAIN = 1
    CAPABILITY = 2


class ChallengeMethod(str):
    DNS = "dns"
    HTTP = "http"


class ChallengeStatus(str):
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"


# --- Layer 0 ---


class Layer0Result(BaseModel):
    domain: str
    https: bool = Field(description="Manifest served over HTTPS")
    valid_json: bool = Field(description="Valid JSON document")
    has_required_fields: bool = Field(description="Has oap, name, description, invoke")
    valid_version: bool = Field(description="oap field is a recognized version")
    manifest_hash: str | None = Field(default=None, description="SHA-256 hash of manifest")
    passed: bool = Field(description="All Layer 0 checks passed")
    errors: list[str] = Field(default_factory=list)


# --- Challenge / Layer 1 ---


class AttestDomainRequest(BaseModel):
    domain: str = Field(description="Domain to attest (e.g. example.com)")
    method: str = Field(default="dns", description="Challenge method: dns or http")


class ChallengeResponse(BaseModel):
    domain: str
    method: str
    token: str
    instructions: str = Field(description="Human-readable instructions for the publisher")
    expires_at: datetime
    layer0: Layer0Result


class ChallengeStatusResponse(BaseModel):
    domain: str
    challenge_verified: bool
    attestation: AttestationRecord | None = None
    error: str | None = None


# --- Layer 2 ---


class AttestCapabilityRequest(BaseModel):
    domain: str = Field(description="Domain to test capabilities for")


class CapabilityTestResult(BaseModel):
    endpoint_live: bool = Field(description="Invoke URL responded")
    health_ok: bool | None = Field(default=None, description="Health endpoint responded")
    format_match: bool | None = Field(default=None, description="Output format matches manifest")
    example_passed: bool | None = Field(default=None, description="Example invocation succeeded")
    errors: list[str] = Field(default_factory=list)
    passed: bool


# --- Attestation ---


class AttestationRecord(BaseModel):
    domain: str
    layer: int
    jws: str = Field(description="Signed JWS attestation token")
    manifest_hash: str
    issued_at: datetime
    expires_at: datetime
    verification_method: str | None = None


class AttestationPayload(BaseModel):
    """Claims inside the JWS token."""
    iss: str = Field(description="Trust provider identifier")
    sub: str = Field(description="Attested domain")
    iat: int = Field(description="Issued at (Unix timestamp)")
    exp: int = Field(description="Expires at (Unix timestamp)")
    oap_layer: int = Field(description="Trust layer (0, 1, 2)")
    oap_manifest_hash: str = Field(description="SHA-256 hash of the manifest at verification time")
    oap_verification_method: str | None = Field(default=None, description="How domain was verified")


# --- API responses ---


class DomainAttestationsResponse(BaseModel):
    domain: str
    attestations: list[AttestationRecord]


class JWKSResponse(BaseModel):
    keys: list[dict]


class HealthResponse(BaseModel):
    status: str
    attestation_count: int
    key_loaded: bool


# Forward reference update
ChallengeStatusResponse.model_rebuild()
