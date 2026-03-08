"""Configuration loader for oap-reminder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    db_path: str = "oap_reminder.db"
    host: str = "127.0.0.1"
    port: int = 8304


def load_config(path: str | None = None) -> Config:
    path = path or os.environ.get("OAP_REMINDER_CONFIG", "config.yaml")
    cfg = Config()
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
        db = raw.get("database", {})
        api = raw.get("api", {})
        if "path" in db:
            cfg.db_path = db["path"]
        if "host" in api:
            cfg.host = api["host"]
        if "port" in api:
            cfg.port = api["port"]
        # Resolve relative DB path against config file directory, not CWD
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(p.parent.resolve() / db_path)
    else:
        # No config file — resolve against package directory
        db_path = Path(cfg.db_path)
        if not db_path.is_absolute():
            cfg.db_path = str(Path(__file__).resolve().parent.parent / db_path)
    return cfg
