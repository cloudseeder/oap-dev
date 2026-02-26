"""Configuration for the OAP Agent service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8303


@dataclass
class DatabaseConfig:
    path: str = "oap_agent.db"


@dataclass
class DiscoveryConfig:
    url: str = "http://localhost:8300"
    model: str = "qwen3:8b"
    timeout: int = 120


@dataclass
class AgentConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    debug: bool = False
    max_tasks: int = 20


def _validate_url(url: str) -> str:
    """Validate discovery URL scheme and hostname."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid discovery URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError(f"Invalid discovery URL (no hostname): {url}")
    return url


def load_config(config_path: str = "config.yaml") -> AgentConfig:
    cfg = AgentConfig()
    p = Path(config_path)
    if not p.exists():
        return cfg

    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    if "api" in raw:
        api = raw["api"]
        cfg.api.host = api.get("host", cfg.api.host)
        cfg.api.port = api.get("port", cfg.api.port)

    if "database" in raw:
        db = raw["database"]
        cfg.database.path = db.get("path", cfg.database.path)

    if "discovery" in raw:
        disc = raw["discovery"]
        cfg.discovery.url = _validate_url(disc.get("url", cfg.discovery.url))
        cfg.discovery.model = disc.get("model", cfg.discovery.model)
        cfg.discovery.timeout = disc.get("timeout", cfg.discovery.timeout)

    cfg.debug = raw.get("debug", cfg.debug)
    cfg.max_tasks = raw.get("max_tasks", cfg.max_tasks)

    return cfg
