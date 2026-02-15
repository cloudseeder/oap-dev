"""Shared fixtures for trust provider tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from oap_trust.config import (
    APIConfig,
    AttestationConfig,
    Config,
    DatabaseConfig,
    KeysConfig,
)
from oap_trust.db import TrustStore
from oap_trust.keys import KeyManager


SAMPLE_MANIFEST = {
    "oap": "1.0",
    "name": "Test Capability",
    "description": "A test capability for unit testing.",
    "invoke": {"method": "POST", "url": "https://example.com/api/test"},
    "input": {"format": "application/json", "description": "Test input"},
    "output": {"format": "application/json", "description": "Test output"},
    "examples": [
        {"input": {"text": "hello"}, "output": {"result": "world"}}
    ],
    "health": "https://example.com/health",
}


SAMPLE_MANIFEST_MINIMAL = {
    "oap": "1.0",
    "name": "Minimal",
    "description": "Minimal manifest.",
    "invoke": {"method": "GET", "url": "https://example.com/api/minimal"},
}


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that's cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def cfg(tmp_dir: Path) -> Config:
    """Config pointing at temp directories."""
    return Config(
        keys=KeysConfig(path=str(tmp_dir / "keys")),
        database=DatabaseConfig(path=str(tmp_dir / "trust.db")),
        attestation=AttestationConfig(request_timeout=5),
        api=APIConfig(port=8399),
    )


@pytest.fixture
def key_manager(cfg: Config) -> KeyManager:
    """Initialized key manager with ephemeral keys."""
    km = KeyManager(cfg.keys)
    km.initialize()
    return km


@pytest.fixture
def store(cfg: Config) -> TrustStore:
    """Fresh trust store in a temp directory."""
    s = TrustStore(cfg.database)
    yield s
    s.close()
