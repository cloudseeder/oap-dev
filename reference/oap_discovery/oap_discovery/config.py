"""YAML + environment variable configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    generate_model: str = "qwen3:4b"
    timeout: int = 30
    num_ctx: int = 4096
    keep_alive: str = "-1m"


@dataclass
class ChromaDBConfig:
    path: str = "./oap_data"
    collection: str = "manifests"


@dataclass
class CrawlerConfig:
    seeds_file: str = "seeds.txt"
    seeds_dir: str = "seeds"
    interval: int = 3600
    concurrency: int = 5
    user_agent: str = "oap-crawler/0.1"
    request_timeout: int = 10


@dataclass
class APIConfig:
    host: str = "127.0.0.1"
    port: int = 8300


@dataclass
class ExperienceConfig:
    enabled: bool = False
    db_path: str = "./oap_experience.db"
    confidence_threshold: float = 0.85
    max_records: int = 10000
    invoke_timeout: int = 30
    stdio_timeout: int = 10


@dataclass
class ToolBridgeConfig:
    enabled: bool = True
    default_top_k: int = 5
    max_rounds: int = 3
    ollama_timeout: int = 300
    http_timeout: int = 30
    stdio_timeout: int = 10
    credentials_file: str = "credentials.yaml"
    max_tool_result: int = 8000
    summarize_threshold: int = 4000
    chunk_size: int = 4000


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    api: APIConfig = field(default_factory=APIConfig)
    experience: ExperienceConfig = field(default_factory=ExperienceConfig)
    tool_bridge: ToolBridgeConfig = field(default_factory=ToolBridgeConfig)


def load_credentials(path: str | Path) -> dict[str, dict]:
    """Load domain-keyed credentials from a YAML file.

    Returns an empty dict if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        raw = yaml.safe_load(f) or {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _apply_env_overrides(cfg: Config) -> None:
    """Override config values with OAP_<SECTION>_<KEY> env vars."""
    section_map = {
        "ollama": cfg.ollama,
        "chromadb": cfg.chromadb,
        "crawler": cfg.crawler,
        "api": cfg.api,
        "experience": cfg.experience,
        "tool_bridge": cfg.tool_bridge,
    }
    for section_name, section_obj in section_map.items():
        for f in fields(section_obj):
            env_key = f"OAP_{section_name.upper()}_{f.name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                # bool("false") is True in Python — handle explicitly
                if f.type is bool:
                    setattr(section_obj, f.name, env_val.lower() in ("true", "1", "yes"))
                else:
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
            if "ollama" in raw:
                cfg.ollama = _build_section(OllamaConfig, raw["ollama"])
            if "chromadb" in raw:
                cfg.chromadb = _build_section(ChromaDBConfig, raw["chromadb"])
            if "crawler" in raw:
                cfg.crawler = _build_section(CrawlerConfig, raw["crawler"])
            if "api" in raw:
                cfg.api = _build_section(APIConfig, raw["api"])
            if "experience" in raw:
                cfg.experience = _build_section(ExperienceConfig, raw["experience"])
            if "tool_bridge" in raw:
                cfg.tool_bridge = _build_section(ToolBridgeConfig, raw["tool_bridge"])

    _apply_env_overrides(cfg)
    return cfg
