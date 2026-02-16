"""FastAPI dashboard API serving adoption stats and manifest list."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, Header

from .db import DashboardDB

log = logging.getLogger("oap.dashboard.api")

_db: DashboardDB | None = None

DEFAULT_CONFIG = {
    "database": {"path": "dashboard.db"},
    "api": {"host": "127.0.0.1", "port": 8302},
}


def verify_backend_token(x_backend_token: str | None = Header(None)) -> None:
    """Verify X-Backend-Token header matches OAP_BACKEND_SECRET env var.

    Skip validation if OAP_BACKEND_SECRET is not set (local dev mode).
    """
    secret = os.environ.get("OAP_BACKEND_SECRET")
    if secret and x_backend_token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")


def load_config(config_path: str = "config.yaml") -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = Path(config_path)
    if p.exists():
        with open(p) as f:
            file_cfg = yaml.safe_load(f) or {}
        for section in ("database", "api"):
            if section in file_cfg:
                cfg[section] = {**cfg[section], **file_cfg[section]}
    return cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db
    config_path = getattr(app, "_config_path", "config.yaml")
    cfg = load_config(config_path)
    _db = DashboardDB(cfg["database"]["path"])
    count = _db.get_stats().get("total", 0)
    log.info("Dashboard API started — %d manifests tracked", count)
    yield
    _db.close()


app = FastAPI(
    title="OAP Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_backend_token)],
)


@app.get("/stats")
async def get_stats():
    """Current adoption stats."""
    return _db.get_stats()


@app.get("/stats/history")
async def get_stats_history(days: int = 30):
    """Daily stats for the last N days."""
    return _db.get_stats_history(days)


@app.get("/manifests")
async def get_manifests(page: int = 1, limit: int = 50):
    """Paginated list of tracked manifests."""
    return _db.get_manifests(page, limit)


@app.get("/health")
async def health():
    stats = _db.get_stats()
    return {"status": "ok", "total_manifests": stats.get("total", 0)}


def main():
    """Entry point for oap-dashboard-api command."""
    import argparse

    parser = argparse.ArgumentParser(description="OAP Dashboard API")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    app._config_path = args.config
    uvicorn.run(
        "oap_dashboard.api:app",
        host=cfg["api"]["host"],
        port=cfg["api"]["port"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
