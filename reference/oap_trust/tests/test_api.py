"""Tests for the FastAPI trust provider API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from oap_trust.api import app, lifespan
from oap_trust.config import Config

from .conftest import SAMPLE_MANIFEST


@pytest.fixture
def client(cfg: Config, tmp_dir):
    """TestClient with config pointing at temp dirs."""
    # Patch _find_config so it doesn't look for real config files
    with patch("oap_trust.api._find_config", return_value=str(tmp_dir / "config.yaml")), \
         patch("oap_trust.api.load_config", return_value=cfg):
        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["key_loaded"] is True
        assert isinstance(data["attestation_count"], int)


class TestKeysEndpoint:
    def test_jwks(self, client: TestClient):
        resp = client.get("/v1/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert "keys" in data
        assert len(data["keys"]) == 1
        assert data["keys"][0]["alg"] == "EdDSA"
        assert data["keys"][0]["crv"] == "Ed25519"


class TestAttestationsEndpoint:
    def test_get_empty(self, client: TestClient):
        resp = client.get("/v1/attestations/unknown.example")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "unknown.example"
        assert data["attestations"] == []


class TestDomainAttestation:
    @respx.mock
    def test_initiate(self, client: TestClient):
        """POST /v1/attest/domain should return a challenge."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        resp = client.post(
            "/v1/attest/domain",
            json={"domain": "example.com", "method": "dns"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "example.com"
        assert data["method"] == "dns"
        assert "token" in data
        assert data["layer0"]["passed"] is True

    @respx.mock
    def test_initiate_bad_manifest(self, client: TestClient):
        """Should return 400 if Layer 0 fails."""
        respx.get("https://bad.example/.well-known/oap.json").mock(
            return_value=httpx.Response(404)
        )
        resp = client.post(
            "/v1/attest/domain",
            json={"domain": "bad.example"},
        )
        assert resp.status_code == 400

    @respx.mock
    def test_full_flow(self, client: TestClient):
        """Initiate -> verify -> fetch attestations."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )

        # Initiate
        resp = client.post(
            "/v1/attest/domain",
            json={"domain": "example.com"},
        )
        assert resp.status_code == 200

        # Verify (mock DNS)
        with patch(
            "oap_trust.attestation.verify_challenge",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.get("/v1/attest/domain/example.com/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["challenge_verified"] is True
        assert data["attestation"] is not None

        # Fetch attestations
        resp = client.get("/v1/attestations/example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["attestations"]) == 1
        assert data["attestations"][0]["layer"] == 1


class TestCapabilityAttestation:
    @respx.mock
    def test_capability_pass(self, client: TestClient):
        """POST /v1/attest/capability with live endpoint."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
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

        resp = client.post(
            "/v1/attest/capability",
            json={"domain": "example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["test_result"]["passed"] is True
        assert data["attestation"] is not None
