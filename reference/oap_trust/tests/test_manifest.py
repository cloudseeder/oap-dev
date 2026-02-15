"""Tests for manifest fetching and Layer 0 verification."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from oap_trust.config import AttestationConfig
from oap_trust.manifest import check_layer0, fetch_manifest, hash_manifest

from .conftest import SAMPLE_MANIFEST, SAMPLE_MANIFEST_MINIMAL


@pytest.fixture
def attest_cfg() -> AttestationConfig:
    return AttestationConfig(request_timeout=5)


class TestHashManifest:
    def test_deterministic(self):
        """Same input produces same hash."""
        h1 = hash_manifest(SAMPLE_MANIFEST)
        h2 = hash_manifest(SAMPLE_MANIFEST)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_input_different_hash(self):
        h1 = hash_manifest(SAMPLE_MANIFEST)
        h2 = hash_manifest(SAMPLE_MANIFEST_MINIMAL)
        assert h1 != h2


class TestFetchManifest:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_success(self, attest_cfg: AttestationConfig):
        """Successfully fetch a manifest over HTTPS."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        manifest, url = await fetch_manifest("example.com", attest_cfg)
        assert manifest["name"] == "Test Capability"
        assert url == "https://example.com/.well-known/oap.json"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_404(self, attest_cfg: AttestationConfig):
        """404 should raise."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_manifest("example.com", attest_cfg)

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_http_when_allowed(self, attest_cfg: AttestationConfig):
        """HTTP should work when allow_http=True."""
        respx.get("http://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        manifest, url = await fetch_manifest(
            "example.com", attest_cfg, allow_http=True
        )
        assert manifest["name"] == "Test Capability"


class TestLayer0:
    @respx.mock
    @pytest.mark.asyncio
    async def test_layer0_pass(self, attest_cfg: AttestationConfig):
        """Full manifest should pass Layer 0."""
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_MANIFEST)
        )
        result = await check_layer0("example.com", attest_cfg)
        assert result.passed
        assert result.https
        assert result.valid_json
        assert result.has_required_fields
        assert result.valid_version
        assert result.manifest_hash is not None
        assert result.errors == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_layer0_missing_fields(self, attest_cfg: AttestationConfig):
        """Manifest missing required fields should fail."""
        bad_manifest = {"oap": "1.0", "name": "Incomplete"}
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=bad_manifest)
        )
        result = await check_layer0("example.com", attest_cfg)
        assert not result.passed
        assert not result.has_required_fields
        assert any("Missing required" in e for e in result.errors)

    @respx.mock
    @pytest.mark.asyncio
    async def test_layer0_bad_version(self, attest_cfg: AttestationConfig):
        """Unknown OAP version should fail."""
        bad = {**SAMPLE_MANIFEST, "oap": "99.0"}
        respx.get("https://example.com/.well-known/oap.json").mock(
            return_value=httpx.Response(200, json=bad)
        )
        result = await check_layer0("example.com", attest_cfg)
        assert not result.passed
        assert not result.valid_version

    @respx.mock
    @pytest.mark.asyncio
    async def test_layer0_fetch_error(self, attest_cfg: AttestationConfig):
        """Network error should fail gracefully."""
        respx.get("https://unreachable.example/.well-known/oap.json").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await check_layer0("unreachable.example", attest_cfg)
        assert not result.passed
        assert not result.valid_json
