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


_DEFAULT_CATEGORIES: dict[str, str] = {
    "personal": (
        "written by or about a real person you know: colleagues, friends, "
        "family, clients, neighbors, community members. Includes social media "
        "notifications about people you know (Facebook comments, tags, replies). "
        "HOA/community group emails where a real person is writing also count"
    ),
    "machine": (
        "automated/system-generated with no human author: server alerts, "
        "cron output, cPanel, disk space warnings, security scans, WordPress updates, "
        "CI/CD, monitoring, settlement reports, auth codes"
    ),
    "mailing-list": (
        "informational newsletters, news digests, editorial content, "
        "industry bulletins (CISA advisories, tech newsletters, curated content). "
        "NOT social notifications about people you know (those are personal). "
        "NOT promotional offers (those are offers)"
    ),
    "spam": "junk, phishing, unsolicited bulk email, adult content",
    "offers": (
        "selling something: sales, promotions, deals, coupons, discounts, "
        "event tickets, subscription renewals, product launches, service upgrades"
    ),
}


@dataclass
class ClassifierConfig:
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3.5:latest"
    timeout: int = 30
    categories: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_CATEGORIES))


@dataclass
class AutoFileConfig:
    enabled: bool = False
    # Map category → IMAP folder name (created if missing)
    folders: dict[str, str] = field(default_factory=lambda: {
        "personal": "INBOX",
        "machine": "Machine",
        "mailing-list": "Mailing-List",
        "spam": "Spam",
        "offers": "Offers",
    })


@dataclass
class Config:
    imap: IMAPConfig = field(default_factory=IMAPConfig)
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    auto_file: AutoFileConfig = field(default_factory=AutoFileConfig)
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
        if "categories" in cl:
            # Merge user categories into defaults — user can override or add
            cfg.classifier.categories.update(cl["categories"])

        # Auto-file
        af = raw.get("auto_file", {})
        cfg.auto_file.enabled = af.get("enabled", cfg.auto_file.enabled)
        if "folders" in af:
            cfg.auto_file.folders.update(af["folders"])

        # Resolve relative DB path against config file directory
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(p.parent.resolve() / db_path)
    else:
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(Path(__file__).resolve().parent.parent / db_path)
    return cfg
