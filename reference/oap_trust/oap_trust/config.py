"""YAML + environment variable configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class KeysConfig:
    path: str = "./oap_trust_data/keys"
    rotation_days: int = 365


@dataclass
class DatabaseConfig:
    path: str = "./oap_trust_data/trust.db"


@dataclass
class AttestationConfig:
    layer1_expiry_days: int = 90
    layer2_expiry_days: int = 7
    challenge_ttl_seconds: int = 3600
    request_timeout: int = 10
    max_manifest_size: int = 1_048_576  # 1MB


@dataclass
class APIConfig:
    host: str = "127.0.0.1"
    port: int = 8301


@dataclass
class Config:
    keys: KeysConfig = field(default_factory=KeysConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    attestation: AttestationConfig = field(default_factory=AttestationConfig)
    api: APIConfig = field(default_factory=APIConfig)


def _apply_env_overrides(cfg: Config) -> None:
    """Override config values with OAP_<SECTION>_<KEY> env vars."""
    section_map = {
        "keys": cfg.keys,
        "database": cfg.database,
        "attestation": cfg.attestation,
        "api": cfg.api,
    }
    for section_name, section_obj in section_map.items():
        for f in fields(section_obj):
            env_key = f"OAP_{section_name.upper()}_{f.name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                setattr(section_obj, f.name, f.type(env_val))


def _build_section(dataclass_type: type, data: dict[str, Any]) -> Any:
    """Build a dataclass from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(dataclass_type)}
    return dataclass_type(**{k: v for k, v in data.items() if k in known})


def load_config(path: str | Path | None = None) -> Config:
    """Load config from YAML file (optional) then apply env var overrides."""
    cfg = Config()

    if path is not None:
        p = Path(path)
        if p.exists():
            with open(p) as f:
                raw = yaml.safe_load(f) or {}
            if "keys" in raw:
                cfg.keys = _build_section(KeysConfig, raw["keys"])
            if "database" in raw:
                cfg.database = _build_section(DatabaseConfig, raw["database"])
            if "attestation" in raw:
                cfg.attestation = _build_section(AttestationConfig, raw["attestation"])
            if "api" in raw:
                cfg.api = _build_section(APIConfig, raw["api"])

    _apply_env_overrides(cfg)
    return cfg
