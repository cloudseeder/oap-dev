"""Tests for Ed25519 key management and JWS signing."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from oap_trust.config import KeysConfig
from oap_trust.keys import KeyManager


class TestKeyManager:
    def test_generate_and_load_keys(self, tmp_dir: Path):
        """Keys are generated on first run and loaded on subsequent runs."""
        cfg = KeysConfig(path=str(tmp_dir / "keys"))

        # First run: generate
        km1 = KeyManager(cfg)
        km1.initialize()
        assert km1.is_loaded
        assert (tmp_dir / "keys" / "private.pem").exists()
        assert (tmp_dir / "keys" / "public.pem").exists()

        # Second run: load existing
        km2 = KeyManager(cfg)
        km2.initialize()
        assert km2.is_loaded

        # Both should produce the same JWKS
        assert km1.jwks() == km2.jwks()

    def test_sign_verify_roundtrip(self, key_manager: KeyManager):
        """Sign a payload and verify it returns the same claims."""
        payload = {
            "iss": "test",
            "sub": "example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "oap_layer": 1,
        }
        token = key_manager.sign(payload)
        assert isinstance(token, str)
        assert len(token) > 0

        decoded = key_manager.verify(token)
        assert decoded["iss"] == "test"
        assert decoded["sub"] == "example.com"
        assert decoded["oap_layer"] == 1

    def test_verify_expired_token(self, key_manager: KeyManager):
        """Expired tokens should fail verification."""
        payload = {
            "iss": "test",
            "sub": "example.com",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
        token = key_manager.sign(payload)

        import jwt
        with pytest.raises(jwt.ExpiredSignatureError):
            key_manager.verify(token)

    def test_jwks_format(self, key_manager: KeyManager):
        """JWKS output should have correct structure."""
        jwks = key_manager.jwks()
        assert "keys" in jwks
        assert len(jwks["keys"]) == 1

        key = jwks["keys"][0]
        assert key["kty"] == "OKP"
        assert key["crv"] == "Ed25519"
        assert key["alg"] == "EdDSA"
        assert key["use"] == "sig"
        assert "kid" in key
        assert "x" in key

    def test_public_pem(self, key_manager: KeyManager):
        """Public PEM should be a valid PEM string."""
        pem = key_manager.public_pem()
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert pem.strip().endswith("-----END PUBLIC KEY-----")

    def test_sign_without_init_raises(self, tmp_dir: Path):
        """Signing before initialize() should raise."""
        km = KeyManager(KeysConfig(path=str(tmp_dir / "keys")))
        with pytest.raises(RuntimeError, match="not initialized"):
            km.sign({"test": 1})
