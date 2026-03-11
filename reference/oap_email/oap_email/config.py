"""Configuration loader for oap-email."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class IMAPConfig:
    host: str = ""
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    # Folders to scan (IMAP folder names)
    folders: list[str] = field(default_factory=lambda: ["INBOX"])


@dataclass
class ClassifierConfig:
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3.5:latest"
    timeout: int = 30

@dataclass
class Config:
    imap: IMAPConfig = field(default_factory=IMAPConfig)
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    db_path: str = "oap_email.db"
    host: str = "127.0.0.1"
    port: int = 8305
    # Max messages to cache per folder
    max_cached: int = 500
    # Default scan window (hours) when no 'since' provided
    default_scan_hours: int = 24


def load_config(path: str | None = None) -> Config:
    path = path or os.environ.get("OAP_EMAIL_CONFIG", "config.yaml")
    cfg = Config()
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}

        # IMAP settings
        imap = raw.get("imap", {})
        cfg.imap.host = imap.get("host", cfg.imap.host)
        cfg.imap.port = imap.get("port", cfg.imap.port)
        cfg.imap.username = imap.get("username", cfg.imap.username)
        cfg.imap.password = os.environ.get("OAP_EMAIL_PASSWORD", imap.get("password", ""))
        cfg.imap.use_ssl = imap.get("use_ssl", cfg.imap.use_ssl)
        if "folders" in imap:
            cfg.imap.folders = imap["folders"]

        # Database
        db = raw.get("database", {})
        if "path" in db:
            cfg.db_path = db["path"]

        # API
        api = raw.get("api", {})
        cfg.host = api.get("host", cfg.host)
        cfg.port = api.get("port", cfg.port)

        cfg.max_cached = raw.get("max_cached", cfg.max_cached)
        cfg.default_scan_hours = raw.get("default_scan_hours", cfg.default_scan_hours)

        # Classifier
        cl = raw.get("classifier", {})
        cfg.classifier.enabled = cl.get("enabled", cfg.classifier.enabled)
        cfg.classifier.ollama_url = cl.get("ollama_url", cfg.classifier.ollama_url)
        cfg.classifier.model = cl.get("model", cfg.classifier.model)
        cfg.classifier.timeout = cl.get("timeout", cfg.classifier.timeout)

        # Resolve relative DB path against config file directory
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(p.parent.resolve() / db_path)
    else:
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(Path(__file__).resolve().parent.parent / db_path)
    return cfg
