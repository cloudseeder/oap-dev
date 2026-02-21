"""FastAPI discovery API."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Header

from .config import Config, load_config
from .db import ManifestStore
from .discovery import DiscoveryEngine
from . import experience_api
from . import tool_api
from .experience_engine import ExperienceEngine
from .experience_store import ExperienceStore
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
_experience_store: ExperienceStore | None = None


def verify_backend_token(x_backend_token: str | None = Header(None)) -> None:
    """Verify X-Backend-Token header matches OAP_BACKEND_SECRET env var.

    Skip validation if OAP_BACKEND_SECRET is not set (local dev mode).
    Uses hmac.compare_digest for timing-safe comparison.
    """
    import hmac

    secret = os.environ.get("OAP_BACKEND_SECRET")
    if secret:
        if x_backend_token is None or not hmac.compare_digest(secret, x_backend_token):
            raise HTTPException(status_code=403, detail="Forbidden")


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


async def _index_local_manifests() -> None:
    """Index manifest files from the manifests/ directory next to the package."""
    from .validate import validate_manifest

    manifests_dir = Path(__file__).parent.parent / "manifests"
    if not manifests_dir.exists():
        return

    count = 0
    for path in sorted(manifests_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to read %s: %s", path, e)
            continue
        result = validate_manifest(data)
        if not result.valid:
            log.error("Invalid manifest %s: %s", path.name, result.errors)
            continue
        domain = f"local/{path.stem}"
        embedding, _ = await _ollama.embed_document(data["description"])
        _store.upsert_manifest(domain, data, embedding)
        count += 1

    if count:
        log.info("Indexed %d local manifest(s)", count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _ollama, _engine, _cfg, _experience_store

    config_path = _find_config()
    _cfg = load_config(config_path)

    _store = ManifestStore(_cfg.chromadb)
    _ollama = OllamaClient(_cfg.ollama)
    _engine = DiscoveryEngine(_store, _ollama)

    # Index local manifests (e.g. Unix tools in manifests/)
    await _index_local_manifests()

    log.info("API started — %d manifests indexed", _store.count())

    # Ollama tool bridge
    if _cfg.tool_bridge.enabled:
        tool_api._engine = _engine
        tool_api._store = _store
        tool_api._ollama_cfg = _cfg.ollama
        tool_api._tool_bridge_cfg = _cfg.tool_bridge
        tool_api._ollama = _ollama
        log.info("Tool bridge enabled — /v1/tools and /v1/chat active")

    # Procedural memory (experimental)
    if _cfg.experience.enabled:
        _experience_store = ExperienceStore(_cfg.experience.db_path)
        exp_engine = ExperienceEngine(_engine, _ollama, _experience_store, _cfg.experience)
        experience_api._experience_engine = exp_engine
        experience_api._experience_store = _experience_store
        log.info(
            "Procedural memory enabled — %d experience records",
            _experience_store.count(),
        )
        # Wire experience cache into tool bridge chat flow
        if _cfg.tool_bridge.enabled:
            tool_api._experience_engine = exp_engine
            tool_api._experience_store = _experience_store
            tool_api._experience_cfg = _cfg.experience
            log.info("Experience cache wired into tool bridge")

    yield

    if _experience_store is not None:
        _experience_store.close()
    await _ollama.close()


app = FastAPI(
    title="OAP Discovery API",
    description="Reference discovery service for Open Application Protocol manifests",
    version="0.1.0",
    lifespan=lifespan,
)
# Tool bridge routes — no auth (local-only, secured by Cloudflare Tunnel path filtering)
app.include_router(tool_api.router)
# Experience routes — auth required
app.include_router(experience_api.router, dependencies=[Depends(verify_backend_token)])


_auth = [Depends(verify_backend_token)]


@app.post("/v1/discover", response_model=DiscoverResponse, dependencies=_auth)
async def discover(req: DiscoverRequest) -> DiscoverResponse:
    """Discover the best manifest for a natural language task."""
    return await _engine.discover(req.task, top_k=req.top_k)


@app.get("/v1/manifests", response_model=list[ManifestEntry], dependencies=_auth)
async def list_manifests() -> list[ManifestEntry]:
    """List all indexed manifests."""
    entries = _store.list_domains()
    return [ManifestEntry(**e) for e in entries]


@app.get("/v1/manifests/{domain}", dependencies=_auth)
async def get_manifest(domain: str) -> dict:
    """Get a specific manifest by domain."""
    manifest = _store.get_manifest(domain)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest not found: {domain}")
    return manifest


@app.get("/health", response_model=HealthResponse, dependencies=_auth)
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
