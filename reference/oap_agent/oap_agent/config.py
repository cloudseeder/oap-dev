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
    timeout: int = 300


@dataclass
class VoiceConfig:
    enabled: bool = True
    whisper_model: str = "base"       # tiny, base, small
    device: str = "auto"              # auto, cpu, cuda
    compute_type: str = "auto"        # auto, int8, float16, float32
    language: str | None = None       # None = auto-detect
    tts_enabled: bool = True
    tts_model_path: str = ""          # path to .onnx voice file
    tts_models_dir: str = "piper-voices"  # dir to scan for available voices
    tts_length_scale: float = 1.0     # speech speed: <1.0 = faster, >1.0 = slower


@dataclass
class EscalationConfig:
    enabled: bool = False
    provider: str = "anthropic"  # "openai", "anthropic", or "googleai"
    base_url: str = ""
    model: str = ""
    api_key: str = ""  # or OAP_ESCALATION_API_KEY / provider-specific env var
    timeout: int = 120
    max_tokens: int = 4096


@dataclass
class AgentConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    debug: bool = True
    max_tasks: int = 20
    max_concurrent_tasks: int = 1


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

    # Resolve relative DB path against config file directory, not CWD
    db_path = Path(cfg.database.path)
    if not db_path.is_absolute():
        cfg.database.path = str(p.parent.resolve() / db_path)

    if "discovery" in raw:
        disc = raw["discovery"]
        cfg.discovery.url = _validate_url(disc.get("url", cfg.discovery.url))
        cfg.discovery.model = disc.get("model", cfg.discovery.model)
        cfg.discovery.timeout = disc.get("timeout", cfg.discovery.timeout)

    if "voice" in raw:
        v = raw["voice"]
        cfg.voice.enabled = v.get("enabled", cfg.voice.enabled)
        cfg.voice.whisper_model = v.get("whisper_model", cfg.voice.whisper_model)
        cfg.voice.device = v.get("device", cfg.voice.device)
        cfg.voice.compute_type = v.get("compute_type", cfg.voice.compute_type)
        cfg.voice.language = v.get("language", cfg.voice.language)
        cfg.voice.tts_enabled = v.get("tts_enabled", cfg.voice.tts_enabled)
        cfg.voice.tts_model_path = v.get("tts_model_path", cfg.voice.tts_model_path)
        cfg.voice.tts_models_dir = v.get("tts_models_dir", cfg.voice.tts_models_dir)

    if "escalation" in raw:
        esc = raw["escalation"]
        cfg.escalation.enabled = esc.get("enabled", cfg.escalation.enabled)
        cfg.escalation.provider = esc.get("provider", cfg.escalation.provider)
        cfg.escalation.base_url = esc.get("base_url", cfg.escalation.base_url)
        cfg.escalation.model = esc.get("model", cfg.escalation.model)
        cfg.escalation.api_key = esc.get("api_key", cfg.escalation.api_key)
        cfg.escalation.timeout = esc.get("timeout", cfg.escalation.timeout)
        cfg.escalation.max_tokens = esc.get("max_tokens", cfg.escalation.max_tokens)

    # Env var overrides for escalation
    import os
    if os.environ.get("OAP_ESCALATION_ENABLED", "").lower() in ("true", "1"):
        cfg.escalation.enabled = True
    if os.environ.get("OAP_ESCALATION_PROVIDER"):
        cfg.escalation.provider = os.environ["OAP_ESCALATION_PROVIDER"]
    if os.environ.get("OAP_ESCALATION_MODEL"):
        cfg.escalation.model = os.environ["OAP_ESCALATION_MODEL"]

    cfg.debug = raw.get("debug", cfg.debug)
    cfg.max_tasks = raw.get("max_tasks", cfg.max_tasks)
    cfg.max_concurrent_tasks = raw.get("max_concurrent_tasks", cfg.max_concurrent_tasks)

    return cfg
