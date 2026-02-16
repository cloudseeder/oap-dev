"""Ed25519 key management, JWS signing, and JWKS endpoint format."""

from __future__ import annotations

import base64
import json
import logging
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
import jwt

from .config import KeysConfig

log = logging.getLogger("oap.trust.keys")


class KeyManager:
    """Manages Ed25519 keypair for signing attestations."""

    def __init__(self, cfg: KeysConfig) -> None:
        self._cfg = cfg
        self._key_dir = Path(cfg.path)
        self._private_key: Ed25519PrivateKey | None = None
        self._public_key: Ed25519PublicKey | None = None
        self._kid: str = "oap-trust-1"

    def initialize(self) -> None:
        """Load existing keypair or generate a new one."""
        self._key_dir.mkdir(parents=True, exist_ok=True)
        private_path = self._key_dir / "private.pem"
        public_path = self._key_dir / "public.pem"

        if private_path.exists():
            log.info("Loading existing keypair from %s", self._key_dir)
            private_pem = private_path.read_bytes()
            self._private_key = serialization.load_pem_private_key(private_pem, password=None)
            self._public_key = self._private_key.public_key()
        else:
            log.info("Generating new Ed25519 keypair in %s", self._key_dir)
            self._private_key = Ed25519PrivateKey.generate()
            self._public_key = self._private_key.public_key()

            private_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_pem = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            private_path.write_bytes(private_pem)
            # Set restrictive permissions on private key (600: owner read/write only)
            os.chmod(str(private_path), stat.S_IRUSR | stat.S_IWUSR)
            public_path.write_bytes(public_pem)
            log.info("Keypair saved")

    @property
    def is_loaded(self) -> bool:
        return self._private_key is not None

    def sign(self, payload: dict) -> str:
        """Sign a payload as a JWS (compact serialization) using Ed25519."""
        if self._private_key is None:
            raise RuntimeError("Keys not initialized — call initialize() first")
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="EdDSA",
            headers={"kid": self._kid},
        )

    def verify(self, token: str) -> dict:
        """Verify a JWS token and return the payload."""
        if self._public_key is None:
            raise RuntimeError("Keys not initialized — call initialize() first")
        return jwt.decode(token, self._public_key, algorithms=["EdDSA"])

    def jwks(self) -> dict:
        """Return the public key in JWKS format."""
        if self._public_key is None:
            raise RuntimeError("Keys not initialized — call initialize() first")

        # Get raw public key bytes (32 bytes for Ed25519)
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": x,
                    "kid": self._kid,
                    "use": "sig",
                    "alg": "EdDSA",
                }
            ]
        }

    def public_pem(self) -> str:
        """Return the public key as PEM string."""
        if self._public_key is None:
            raise RuntimeError("Keys not initialized — call initialize() first")
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
