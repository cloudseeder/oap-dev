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
from fastapi import FastAPI, File, HTTPException, UploadFile
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
_voice_cfg = None  # VoiceConfig, set in lifespan

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
    global _debug_mode, _max_tasks, _voice_cfg

    config_path = getattr(app, "_config_path", "config.yaml")
    cfg = load_config(config_path)

    _db = AgentDB(cfg.database.path)
    _event_bus = EventBus()
    _discovery_url = cfg.discovery.url
    _discovery_model = cfg.discovery.model
    _discovery_timeout = cfg.discovery.timeout
    _debug_mode = cfg.debug
    _max_tasks = cfg.max_tasks

    _voice_cfg = cfg.voice

    _scheduler = TaskScheduler()
    _scheduler.start(_db, _event_bus, _discovery_url, debug=_debug_mode, max_concurrent=cfg.max_concurrent_tasks)

    # Load Whisper model for voice input
    if cfg.voice.enabled:
        try:
            from . import transcribe as _tx
            _tx.init(cfg.voice.whisper_model, cfg.voice.device, cfg.voice.compute_type)
            log.info("Whisper %s loaded — voice input ready", cfg.voice.whisper_model)
        except Exception as exc:
            log.warning("Whisper model failed to load — voice input disabled: %s", exc)
            _voice_cfg = cfg.voice
            _voice_cfg.enabled = False

    conv_count = _db.list_conversations()["total"]
    task_count = len(_db.list_tasks())
    log.info("Manifest started — %d conversations, %d tasks", conv_count, task_count)

    yield

    _event_bus.shutdown()
    _scheduler.stop()
    _db.close()
    log.info("Manifest stopped")


app = FastAPI(
    title="Manifest API",
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


class UpdateSettingsRequest(BaseModel):
    persona_name: str | None = Field(None, max_length=100)
    persona_description: str | None = Field(None, max_length=500)
    memory_enabled: bool | None = None
    voice_input_enabled: bool | None = None
    voice_auto_send: bool | None = None
    voice_auto_speak: bool | None = None


class CreateFactRequest(BaseModel):
    fact: str = Field(..., min_length=1, max_length=200)


class UpdateFactRequest(BaseModel):
    fact: str = Field(..., min_length=1, max_length=200)


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

    # Prepend persona + user facts as a system message
    settings = _db.get_settings()
    persona_parts: list[str] = []
    if settings.get("persona_name"):
        intro = f"You are {settings['persona_name']}"
        if settings.get("persona_description"):
            intro += f", {settings['persona_description']}"
        intro += "."
        persona_parts.append(intro)

    if settings.get("memory_enabled") == "true":
        facts = _db.get_all_facts()
        if facts:
            _db.touch_facts([f["id"] for f in facts])
            fact_lines = "\n".join(f"- {f['fact']}" for f in facts)
            persona_parts.append(f"About the user:\n{fact_lines}")

    if persona_parts:
        llm_messages.insert(0, {"role": "system", "content": "\n\n".join(persona_parts)})

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
            yield _sse_event("error", {"message": "Execution failed"})
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

        # Fire-and-forget: extract user memory from this turn
        if settings.get("memory_enabled") == "true" and result["content"]:
            from .memory import extract_and_store_facts
            asyncio.create_task(
                extract_and_store_facts(_db, _discovery_url, req.message, result["content"])
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
    task_id = task["id"]
    semaphore = _scheduler.semaphore if _scheduler else None

    if semaphore:
        log.info("Task %s (%s) run=%s queued (waiting for slot)", task_id, task["name"], run_id)
        await semaphore.acquire()

    try:
        started = time.monotonic()
        log.info("Running task %s (%s) run=%s", task_id, task["name"], run_id)

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
                debug=True,
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
                    "task_name": task["name"],
                })
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.error("Background task run %s failed: %s", run_id, exc, exc_info=True)
            error_msg = f"Task execution failed: {exc}"
            _db.finish_run(
                run_id=run_id,
                status="error",
                error=error_msg,
                duration_ms=duration_ms,
            )
            if _event_bus:
                await _event_bus.publish("task_run_finished", {
                    "task_id": task_id,
                    "run_id": run_id,
                    "status": "error",
                    "error": error_msg,
                    "task_name": task["name"],
                })
    finally:
        if semaphore:
            semaphore.release()


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
    if _event_bus.shutting_down:
        raise HTTPException(status_code=503, detail="Server is shutting down")

    try:
        sub_id, queue = _event_bus.subscribe()
    except RuntimeError:
        raise HTTPException(status_code=429, detail="Too many active event streams")

    async def stream():
        try:
            # Send a keepalive comment immediately
            yield ": connected\n\n"
            while not _event_bus.shutting_down:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if event is None:
                        break  # shutdown sentinel
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
# Settings + Memory routes
# ---------------------------------------------------------------------------

@app.get("/v1/agent/settings")
async def get_settings():
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return _db.get_settings()


@app.patch("/v1/agent/settings")
async def update_settings(req: UpdateSettingsRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if req.persona_name is not None:
        _db.set_setting("persona_name", req.persona_name)
    if req.persona_description is not None:
        _db.set_setting("persona_description", req.persona_description)
    if req.memory_enabled is not None:
        _db.set_setting("memory_enabled", "true" if req.memory_enabled else "false")
    if req.voice_input_enabled is not None:
        _db.set_setting("voice_input_enabled", "true" if req.voice_input_enabled else "false")
    if req.voice_auto_send is not None:
        _db.set_setting("voice_auto_send", "true" if req.voice_auto_send else "false")
    if req.voice_auto_speak is not None:
        _db.set_setting("voice_auto_speak", "true" if req.voice_auto_speak else "false")
    return _db.get_settings()


@app.get("/v1/agent/memory")
async def list_memory():
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    facts = _db.get_all_facts()
    return {"facts": facts, "total": len(facts)}


@app.post("/v1/agent/memory", status_code=201)
async def create_memory(req: CreateFactRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    added = _db.add_facts([req.fact], "manual entry")
    if added == 0:
        raise HTTPException(status_code=409, detail="Fact already exists")
    facts = _db.get_all_facts()
    return {"facts": facts, "total": len(facts)}


@app.patch("/v1/agent/memory/{fact_id}")
async def update_memory(fact_id: str, req: UpdateFactRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.update_fact(fact_id, req.fact):
        raise HTTPException(status_code=404, detail="Fact not found")
    facts = _db.get_all_facts()
    return {"facts": facts, "total": len(facts)}


@app.delete("/v1/agent/memory/{fact_id}", status_code=204)
async def delete_memory(fact_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")


# ---------------------------------------------------------------------------
# Voice routes
# ---------------------------------------------------------------------------

@app.post("/v1/agent/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio to text via faster-whisper."""
    if _voice_cfg is None or not _voice_cfg.enabled:
        raise HTTPException(status_code=501, detail="Voice input not enabled")

    import os
    import tempfile
    from . import transcribe as tx

    data = await file.read()
    if len(data) > 25 * 1024 * 1024:  # 25MB limit
        raise HTTPException(status_code=413, detail="Audio file too large (max 25MB)")

    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        text = tx.transcribe(tmp_path, language=_voice_cfg.language)
        return {"text": text}
    finally:
        os.unlink(tmp_path)


@app.get("/v1/agent/voice/status")
async def voice_status():
    """Check if voice input is available (Whisper model loaded)."""
    enabled = _voice_cfg is not None and _voice_cfg.enabled
    return {"enabled": enabled}


# ---------------------------------------------------------------------------
# Static files (Vite SPA)
# ---------------------------------------------------------------------------

from fastapi.staticfiles import StaticFiles
from pathlib import Path

_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point for oap-agent-api command."""
    import argparse

    parser = argparse.ArgumentParser(description="Manifest API")
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
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
