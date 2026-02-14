"""FastAPI discovery API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException

from .config import Config, load_config
from .db import ManifestStore
from .discovery import DiscoveryEngine
from .models import (
    DiscoverRequest,
    DiscoverResponse,
    HealthResponse,
    ManifestEntry,
)
from .ollama_client import OllamaClient

log = logging.getLogger("oap.api")

# Module-level state, initialized during lifespan
_store: ManifestStore | None = None
_ollama: OllamaClient | None = None
_engine: DiscoveryEngine | None = None
_cfg: Config | None = None


def _find_config() -> str:
    """Find config.yaml relative to package location."""
    candidates = [
        Path("config.yaml"),
        Path(__file__).parent.parent / "config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _ollama, _engine, _cfg

    config_path = _find_config()
    _cfg = load_config(config_path)

    _store = ManifestStore(_cfg.chromadb)
    _ollama = OllamaClient(_cfg.ollama)
    _engine = DiscoveryEngine(_store, _ollama)

    log.info("API started — %d manifests indexed", _store.count())
    yield

    await _ollama.close()


app = FastAPI(
    title="OAP Discovery API",
    description="Reference discovery service for Open Application Protocol manifests",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/v1/discover", response_model=DiscoverResponse)
async def discover(req: DiscoverRequest) -> DiscoverResponse:
    """Discover the best manifest for a natural language task."""
    return await _engine.discover(req.task, top_k=req.top_k)


@app.get("/v1/manifests", response_model=list[ManifestEntry])
async def list_manifests() -> list[ManifestEntry]:
    """List all indexed manifests."""
    entries = _store.list_domains()
    return [ManifestEntry(**e) for e in entries]


@app.get("/v1/manifests/{domain}")
async def get_manifest(domain: str) -> dict:
    """Get a specific manifest by domain."""
    manifest = _store.get_manifest(domain)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest not found: {domain}")
    return manifest


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check — Ollama status and index count."""
    ollama_ok = await _ollama.healthy()
    count = _store.count()
    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        ollama=ollama_ok,
        index_count=count,
    )


def main() -> None:
    """Entry point for oap-api command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config_path = _find_config()
    cfg = load_config(config_path)
    uvicorn.run(
        "oap_discovery.api:app",
        host=cfg.api.host,
        port=cfg.api.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
