"""FastAPI agent API — chat + autonomous task execution."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .config import load_config
from .db import AgentDB
from .events import EventBus
from .executor import execute_chat, execute_task
from .scheduler import TaskScheduler


log = logging.getLogger("oap.agent.api")

_db: AgentDB | None = None
_event_bus: EventBus | None = None
_scheduler: TaskScheduler | None = None
_discovery_url: str = "http://localhost:8300"
_discovery_model: str = "qwen3:8b"
_discovery_timeout: int = 120
_debug_mode: bool = False
_max_tasks: int = 20

ALLOWED_MODELS = {"qwen3:8b", "qwen3:4b", "llama3.2:3b", "mistral:7b"}


def _validate_model(v: str | None) -> str | None:
    if v is not None and v not in ALLOWED_MODELS:
        raise ValueError(f"model must be one of: {', '.join(sorted(ALLOWED_MODELS))}")
    return v


def _validate_cron(schedule: str) -> None:
    """Validate cron expression. Raises ValueError if invalid or too frequent."""
    from croniter import croniter
    from datetime import datetime
    try:
        CronTrigger.from_crontab(schedule)
    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {exc}") from exc
    # Check actual interval between next two firings
    try:
        cron = croniter(schedule, datetime(2025, 1, 1))
        first = cron.get_next(datetime)
        second = cron.get_next(datetime)
        interval_seconds = (second - first).total_seconds()
        if interval_seconds < 300:  # less than 5 minutes
            raise ValueError("Schedules more frequent than every 5 minutes are not allowed")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {exc}") from exc


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _event_bus, _scheduler, _discovery_url, _discovery_model, _discovery_timeout
    global _debug_mode, _max_tasks

    config_path = getattr(app, "_config_path", "config.yaml")
    cfg = load_config(config_path)

    _db = AgentDB(cfg.database.path)
    _event_bus = EventBus()
    _discovery_url = cfg.discovery.url
    _discovery_model = cfg.discovery.model
    _discovery_timeout = cfg.discovery.timeout
    _debug_mode = cfg.debug
    _max_tasks = cfg.max_tasks

    _scheduler = TaskScheduler()
    _scheduler.start(_db, _event_bus, _discovery_url, debug=_debug_mode)

    conv_count = _db.list_conversations()["total"]
    task_count = len(_db.list_tasks())
    log.info("Agent API started — %d conversations, %d tasks", conv_count, task_count)

    yield

    _scheduler.stop()
    _db.close()
    log.info("Agent API stopped")


app = FastAPI(
    title="OAP Agent API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_event(event_type: str, data: Any) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    conversation_id: str | None = Field(None, max_length=64)
    message: str = Field(..., max_length=32_000)
    model: str | None = Field(None, max_length=100)

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str | None) -> str | None:
        return _validate_model(v)


class CreateConversationRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    model: str | None = Field(None, max_length=100)

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str | None) -> str | None:
        return _validate_model(v)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    model: str | None = Field(None, max_length=100)

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str | None) -> str | None:
        return _validate_model(v)


class CreateTaskRequest(BaseModel):
    name: str = Field(..., max_length=200)
    prompt: str = Field(..., max_length=32_000)
    schedule: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str | None) -> str | None:
        return _validate_model(v)

    @field_validator("schedule")
    @classmethod
    def check_schedule(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            _validate_cron(v.strip())
        return v


class UpdateTaskRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    prompt: str | None = Field(None, max_length=32_000)
    schedule: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    enabled: bool | None = None

    @field_validator("model")
    @classmethod
    def check_model(cls, v: str | None) -> str | None:
        return _validate_model(v)

    @field_validator("schedule")
    @classmethod
    def check_schedule(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            _validate_cron(v.strip())
        return v


# ---------------------------------------------------------------------------
# Chat routes
# ---------------------------------------------------------------------------

@app.post("/v1/agent/chat")
async def chat(req: ChatRequest):
    """Send a message to a conversation. Returns SSE stream."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")

    model = req.model or _discovery_model

    # Get or create conversation
    if req.conversation_id:
        conv = _db.get_conversation(req.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = req.message[:60] + ("..." if len(req.message) > 60 else "")
        conv = _db.create_conversation(title=title, model=model)

    conv_id = conv["id"]

    # Save user message
    user_msg = _db.add_message(conv_id, role="user", content=req.message)

    # Build message history for the LLM
    history = _db.get_messages(conv_id)
    llm_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    async def stream_response():
        # Emit user message saved event
        yield _sse_event("message_saved", {
            "conversation_id": conv_id,
            "message": user_msg,
        })

        # Call the OAP discovery service
        try:
            result = await execute_chat(
                discovery_url=_discovery_url,
                messages=llm_messages,
                model=model,
                timeout=_discovery_timeout,
                debug=_debug_mode,
            )
        except Exception as exc:
            log.error("Chat execution failed: %s", exc, exc_info=True)
            yield _sse_event("error", {"message": "Agent execution failed"})
            yield _sse_event("done", {"conversation_id": conv_id})
            return

        # Emit each tool call
        for tc in result.get("tool_calls", []):
            yield _sse_event("tool_call", tc)

        # Save assistant message
        metadata: dict = {}
        if result.get("experience_cache"):
            metadata["experience_cache"] = result["experience_cache"]

        assistant_msg = _db.add_message(
            conv_id,
            role="assistant",
            content=result["content"],
            tool_calls=result["tool_calls"] or None,
            metadata=metadata or None,
        )

        yield _sse_event("assistant_message", {
            "conversation_id": conv_id,
            "message": assistant_msg,
        })
        yield _sse_event("done", {"conversation_id": conv_id})

    return StreamingResponse(stream_response(), media_type="text/event-stream")


@app.get("/v1/agent/conversations")
async def list_conversations(page: int = 1, limit: int = 50):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return _db.list_conversations(page=page, limit=limit)


@app.post("/v1/agent/conversations", status_code=201)
async def create_conversation(req: CreateConversationRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    title = req.title or "New Conversation"
    model = req.model or _discovery_model
    return _db.create_conversation(title=title, model=model)


@app.get("/v1/agent/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    conv = _db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = _db.get_messages(conv_id)
    return conv


@app.delete("/v1/agent/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")


@app.patch("/v1/agent/conversations/{conv_id}")
async def update_conversation(conv_id: str, req: UpdateConversationRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    updated = _db.update_conversation(conv_id, title=req.title, model=req.model)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------

@app.get("/v1/agent/tasks")
async def list_tasks():
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return {"tasks": _db.list_tasks()}


@app.post("/v1/agent/tasks", status_code=201)
async def create_task(req: CreateTaskRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if len(_db.list_tasks()) >= _max_tasks:
        raise HTTPException(status_code=429, detail="Maximum task limit reached")
    model = req.model or _discovery_model
    task = _db.create_task(
        name=req.name,
        prompt=req.prompt,
        schedule=req.schedule,
        model=model,
    )
    if _scheduler and task.get("schedule"):
        _scheduler.schedule_task(task)
    return task


@app.get("/v1/agent/tasks/{task_id}")
async def get_task(task_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    runs = _db.list_runs(task_id, page=1, limit=10)
    task["recent_runs"] = runs["runs"]
    return task


@app.patch("/v1/agent/tasks/{task_id}")
async def update_task(task_id: str, req: UpdateTaskRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = _db.update_task(
        task_id,
        name=req.name,
        prompt=req.prompt,
        schedule=req.schedule,
        model=req.model,
        enabled=req.enabled,
    )
    if _scheduler:
        if updated.get("enabled") and updated.get("schedule"):
            _scheduler.schedule_task(updated)
        else:
            _scheduler.unschedule_task(task_id)
    return updated


@app.delete("/v1/agent/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if _scheduler:
        _scheduler.unschedule_task(task_id)
    if not _db.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@app.post("/v1/agent/tasks/{task_id}/run", status_code=202)
async def trigger_task(task_id: str):
    """Trigger an immediate task execution in the background."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    run = _db.create_run(task_id, task["prompt"])
    run_id = run["id"]

    asyncio.create_task(_run_task_background(task, run_id))
    return {"run_id": run_id, "status": "accepted"}


async def _run_task_background(task: dict, run_id: str) -> None:
    started = time.monotonic()
    task_id = task["id"]

    if _event_bus:
        await _event_bus.publish("task_run_started", {
            "task_id": task_id,
            "run_id": run_id,
            "task_name": task["name"],
        })

    try:
        result = await execute_task(
            discovery_url=_discovery_url,
            prompt=task["prompt"],
            model=task.get("model", _discovery_model),
            timeout=_discovery_timeout,
            debug=_debug_mode,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        _db.finish_run(
            run_id=run_id,
            status="success",
            response=result["content"],
            tool_calls=result["tool_calls"] or None,
            duration_ms=duration_ms,
        )
        if _event_bus:
            await _event_bus.publish("task_run_finished", {
                "task_id": task_id,
                "run_id": run_id,
                "status": "success",
                "duration_ms": duration_ms,
            })
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        log.error("Background task run %s failed: %s", run_id, exc, exc_info=True)
        _db.finish_run(
            run_id=run_id,
            status="error",
            error="Task execution failed",
            duration_ms=duration_ms,
        )
        if _event_bus:
            await _event_bus.publish("task_run_finished", {
                "task_id": task_id,
                "run_id": run_id,
                "status": "error",
                "error": "Task execution failed",
            })


@app.get("/v1/agent/tasks/{task_id}/runs")
async def list_runs(task_id: str, page: int = 1, limit: int = 20):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _db.list_runs(task_id, page=page, limit=limit)


# ---------------------------------------------------------------------------
# Events + Health
# ---------------------------------------------------------------------------

@app.get("/v1/agent/events")
async def sse_events():
    """SSE stream for real-time notifications from background tasks."""
    if _event_bus is None:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        sub_id, queue = _event_bus.subscribe()
    except RuntimeError:
        raise HTTPException(status_code=429, detail="Too many active event streams")

    async def stream():
        try:
            # Send a keepalive comment immediately
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield _sse_event(event["event"], event["data"])
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield ": ping\n\n"
        finally:
            _event_bus.unsubscribe(sub_id)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/v1/agent/health")
async def health():
    if _db is None:
        return {"status": "starting"}
    conversations = _db.list_conversations()["total"]
    tasks = len(_db.list_tasks())
    return {"status": "ok", "conversations": conversations, "tasks": tasks}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point for oap-agent-api command."""
    import argparse

    parser = argparse.ArgumentParser(description="OAP Agent API")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    app._config_path = args.config
    uvicorn.run(
        "oap_agent.api:app",
        host=cfg.api.host,
        port=cfg.api.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
