"""FastAPI trust provider API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException

from .attestation import AttestationService
from .config import Config, load_config
from .db import TrustStore
from .keys import KeyManager
from .models import (
    AttestCapabilityRequest,
    AttestDomainRequest,
    ChallengeResponse,
    ChallengeStatusResponse,
    DomainAttestationsResponse,
    HealthResponse,
    JWKSResponse,
)

log = logging.getLogger("oap.trust.api")

# Module-level state, initialized during lifespan
_service: AttestationService | None = None
_keys: KeyManager | None = None
_store: TrustStore | None = None
_cfg: Config | None = None


def _find_config() -> str:
    """Find config.yaml relative to package location."""
    candidates = [
        Path("config.yaml"),
        Path(__file__).parent.parent / "config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service, _keys, _store, _cfg

    config_path = _find_config()
    _cfg = load_config(config_path)

    _keys = KeyManager(_cfg.keys)
    _keys.initialize()

    _store = TrustStore(_cfg.database)
    _service = AttestationService(_cfg, _keys, _store)

    count = _store.count_attestations()
    log.info("Trust API started — %d active attestations", count)
    yield

    _store.close()


app = FastAPI(
    title="OAP Trust Provider API",
    description="Reference trust provider for Open Application Protocol — domain and capability attestation",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Layer 1: Domain attestation ---


@app.post("/v1/attest/domain", response_model=ChallengeResponse)
async def attest_domain(req: AttestDomainRequest) -> ChallengeResponse:
    """Initiate Layer 1 domain attestation. Runs Layer 0 checks, returns a challenge."""
    try:
        return await _service.initiate_domain_attestation(
            req.domain, req.method
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/v1/attest/domain/{domain}/status", response_model=ChallengeStatusResponse)
async def attest_domain_status(domain: str) -> ChallengeStatusResponse:
    """Verify a pending domain challenge and issue attestation if verified."""
    return await _service.verify_domain_attestation(domain)


# --- Layer 2: Capability attestation ---


@app.post("/v1/attest/capability")
async def attest_capability(req: AttestCapabilityRequest) -> dict:
    """Run Layer 2 capability tests and issue attestation if passed."""
    test_result, attestation = await _service.attest_capability(req.domain)
    resp = {"test_result": test_result.model_dump()}
    if attestation:
        resp["attestation"] = attestation.model_dump(mode="json")
    return resp


# --- Query ---


@app.get("/v1/attestations/{domain}", response_model=DomainAttestationsResponse)
async def get_attestations(domain: str) -> DomainAttestationsResponse:
    """Fetch all valid attestations for a domain. This is what agents query."""
    attestations = _service.get_attestations(domain)
    return DomainAttestationsResponse(domain=domain, attestations=attestations)


# --- Keys ---


@app.get("/v1/keys", response_model=JWKSResponse)
async def get_keys() -> JWKSResponse:
    """JWKS public keys for verifying attestation signatures."""
    return JWKSResponse(**_keys.jwks())


# --- Health ---


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check."""
    count = _store.count_attestations()
    return HealthResponse(
        status="ok",
        attestation_count=count,
        key_loaded=_keys.is_loaded,
    )


def main() -> None:
    """Entry point for oap-trust-api command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config_path = _find_config()
    cfg = load_config(config_path)
    uvicorn.run(
        "oap_trust.api:app",
        host=cfg.api.host,
        port=cfg.api.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
