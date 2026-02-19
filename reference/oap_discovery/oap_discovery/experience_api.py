"""FastAPI router for procedural memory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .experience_engine import ExperienceEngine
from .experience_models import (
    ExperienceInvokeRequest,
    ExperienceInvokeResponse,
    ExperienceRecord,
)
from .experience_store import ExperienceStore

router = APIRouter(prefix="/v1/experience", tags=["procedural-memory"])

# Set by api.py during lifespan initialization
_experience_engine: ExperienceEngine | None = None
_experience_store: ExperienceStore | None = None


def _require_enabled() -> tuple[ExperienceEngine, ExperienceStore]:
    """Raise 503 if the experience system is not enabled."""
    if _experience_engine is None or _experience_store is None:
        raise HTTPException(
            status_code=503,
            detail="Procedural memory is not enabled. Set experience.enabled: true in config.",
        )
    return _experience_engine, _experience_store


@router.post("/invoke", response_model=ExperienceInvokeResponse)
async def experience_invoke(
    req: ExperienceInvokeRequest,
) -> ExperienceInvokeResponse:
    """Experience-augmented discovery: discover + invoke + learn."""
    engine, _ = _require_enabled()
    return await engine.process(req)


@router.get("/records")
async def list_records(page: int = 1, limit: int = 50) -> dict:
    """List experience records (paginated)."""
    _, store = _require_enabled()
    page = max(1, page)
    limit = min(max(1, limit), 100)
    result = store.list_all(page=page, limit=limit)
    # Serialize records for JSON response
    result["records"] = [r.model_dump(mode="json") for r in result["records"]]
    return result


@router.get("/records/{experience_id}")
async def get_record(experience_id: str) -> dict:
    """Get a specific experience record."""
    _, store = _require_enabled()
    record = store.get(experience_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record not found: {experience_id}")
    return record.model_dump(mode="json")


@router.delete("/records/{experience_id}")
async def delete_record(experience_id: str) -> dict:
    """Delete an experience record."""
    _, store = _require_enabled()
    deleted = store.delete(experience_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Record not found: {experience_id}")
    return {"deleted": experience_id}


@router.get("/stats")
async def experience_stats() -> dict:
    """Experience store statistics."""
    _, store = _require_enabled()
    return store.stats()
