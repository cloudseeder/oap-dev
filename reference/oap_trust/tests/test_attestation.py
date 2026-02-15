"""Tests for the attestation orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from oap_trust.attestation import AttestationService
from oap_trust.config import Config
from oap_trust.db import TrustStore
from oap_trust.keys import KeyManager

from .conftest import SAMPLE_MANIFEST


class TestAttestationService:
    @pytest.fixture
    def service(self, cfg: Config, key_manager: KeyManager, store: TrustStore):
        return AttestationService(cfg, key_manager, store)

    @respx.mock
    @pytest.mark.asyncio
    async def test_initiate_domain_attestation(self, service: AttestationService):
        """Initiate should run Layer 0 and return a challenge."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        result = await service.initiate_domain_attestation("example.com", "dns")
        assert result.domain == "example.com"
        assert result.method == "dns"
        assert len(result.token) > 0
        assert result.layer0.passed
        assert "oap-challenge=" in result.instructions

    @respx.mock
    @pytest.mark.asyncio
    async def test_initiate_fails_on_bad_manifest(self, service: AttestationService):
        """Initiation should fail if Layer 0 fails."""
        respx.get("https://bad.example/.well-known/oap.json").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(ValueError, match="Layer 0 checks failed"):
            await service.initiate_domain_attestation("bad.example", "dns")

    @respx.mock
    @pytest.mark.asyncio
    async def test_full_challenge_flow(self, service: AttestationService):
        """Full flow: initiate -> verify challenge -> get attestation."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )

        # Initiate
        challenge = await service.initiate_domain_attestation("example.com", "dns")

        # Mock DNS verification to succeed
        with patch(
            "oap_trust.attestation.verify_challenge",
            new_callable=AsyncMock,
            return_value=True,
        ):
            status = await service.verify_domain_attestation("example.com")

        assert status.challenge_verified
        assert status.attestation is not None
        assert status.attestation.layer == 1
        assert status.attestation.domain == "example.com"
        assert status.attestation.jws  # Non-empty JWS token

    @respx.mock
    @pytest.mark.asyncio
    async def test_challenge_not_verified(self, service: AttestationService):
        """If DNS challenge isn't met, verification should fail."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )

        # Initiate
        await service.initiate_domain_attestation("example.com", "dns")

        # Mock DNS verification to fail
        with patch(
            "oap_trust.attestation.verify_challenge",
            new_callable=AsyncMock,
            return_value=False,
        ):
            status = await service.verify_domain_attestation("example.com")

        assert not status.challenge_verified
        assert status.attestation is None

    @pytest.mark.asyncio
    async def test_verify_no_pending_challenge(self, service: AttestationService):
        """Verify with no pending challenge should return error."""
        status = await service.verify_domain_attestation("nochallenge.example")
        assert not status.challenge_verified
        assert "No pending challenge" in status.error

    @respx.mock
    @pytest.mark.asyncio
    async def test_attestation_signature_roundtrip(
        self, service: AttestationService, key_manager: KeyManager
    ):
        """Issued attestation JWS should be verifiable with the trust provider's keys."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )

        challenge = await service.initiate_domain_attestation("example.com", "dns")

        with patch(
            "oap_trust.attestation.verify_challenge",
            new_callable=AsyncMock,
            return_value=True,
        ):
            status = await service.verify_domain_attestation("example.com")

        # Verify the JWS token
        decoded = key_manager.verify(status.attestation.jws)
        assert decoded["sub"] == "example.com"
        assert decoded["oap_layer"] == 1
        assert decoded["oap_manifest_hash"].startswith("sha256:")

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_attestations(self, service: AttestationService):
        """Stored attestations should be retrievable."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )

        await service.initiate_domain_attestation("example.com", "dns")
        with patch(
            "oap_trust.attestation.verify_challenge",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await service.verify_domain_attestation("example.com")

        attestations = service.get_attestations("example.com")
        assert len(attestations) == 1
        assert attestations[0].layer == 1
        assert attestations[0].domain == "example.com"

    @respx.mock
    @pytest.mark.asyncio
    async def test_capability_attestation_pass(self, service: AttestationService):
        """Layer 2 should pass when endpoint is live."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        # Mock the invoke endpoint and health endpoint
        respx.head("https://example.com/api/test").mock(
            return_value=httpx.Response(200)
        )
        respx.get("https://example.com/health").mock(
            return_value=httpx.Response(200)
        )
        respx.post("https://example.com/api/test").mock(
            return_value=httpx.Response(
                200,
                json={"result": "world"},
                headers={"content-type": "application/json"},
            )
        )

        test_result, attestation = await service.attest_capability("example.com")
        assert test_result.passed
        assert test_result.endpoint_live
        assert attestation is not None
        assert attestation.layer == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_capability_attestation_fail(self, service: AttestationService):
        """Layer 2 should fail when endpoint is down."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        respx.head("https://example.com/api/test").mock(
            return_value=httpx.Response(503)
        )
        respx.get("https://example.com/health").mock(
            return_value=httpx.Response(503)
        )

        test_result, attestation = await service.attest_capability("example.com")
        assert not test_result.passed
        assert attestation is None
