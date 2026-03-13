"""FastAPI agent API — chat + autonomous task execution."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import load_config
from .db import AgentDB
from .events import EventBus
from .executor import execute_chat, execute_conversational, execute_task
from .scheduler import TaskScheduler


log = logging.getLogger("oap.agent.api")

_db: AgentDB | None = None
_event_bus: EventBus | None = None
_scheduler: TaskScheduler | None = None
_discovery_url: str = "http://localhost:8300"
_discovery_model: str = "qwen3:14b"
_discovery_timeout: int = 300
_debug_mode: bool = False
_max_tasks: int = 20
_voice_cfg = None  # VoiceConfig, set in lifespan
_tts_enabled = False

def _validate_model(v: str | None) -> str | None:
    if v is not None and len(v) > 100:
        raise ValueError("model name too long")
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
    global _debug_mode, _max_tasks, _voice_cfg, _tts_enabled

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

    # Load Piper TTS model for voice output
    if cfg.voice.enabled and cfg.voice.tts_enabled and cfg.voice.tts_model_path:
        try:
            from . import tts as _tts_module
            _tts_module.init(cfg.voice.tts_model_path, cfg.voice.tts_models_dir, cfg.voice.tts_length_scale)
            _tts_enabled = True
            log.info("Piper TTS loaded — voice output ready")
        except Exception as exc:
            log.warning("Piper TTS failed to load — voice output disabled: %s", exc)
            _tts_enabled = False

    # Cleanup old task runs at startup
    pruned_runs = _db.cleanup_old_runs(max_per_task=100)
    if pruned_runs:
        log.info("Cleaned up %d old task run(s)", pruned_runs)

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
    incremental: bool = True

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
    model_config = ConfigDict(extra="allow")

    persona_name: str | None = Field(None, max_length=100)
    persona_description: str | None = Field(None, max_length=500)
    memory_enabled: bool | None = None
    voice_input_enabled: bool | None = None
    voice_auto_send: bool | None = None
    voice_auto_speak: bool | None = None
    voice_tts_voice: str | None = Field(None, max_length=200)
    voice_wake_word: str | None = Field(None, max_length=50)


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
    incremental: bool | None = None

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
# Chat classifier — route conversational turns away from tool bridge
# ---------------------------------------------------------------------------

# Short messages matching these patterns skip the tool bridge entirely.
# Conservative: false negatives (chat goes to tool bridge) are fine,
# false positives (factual question skips tools) are bad.
_CONVERSATIONAL_PATTERNS = re.compile(
    r"^("
    r"thanks?(\s+you)?|thank\s+you|thx|ty"
    r"|you'?re\s+welcome"
    r"|ok(ay)?|got\s+it|understood|perfect|great|nice|cool|awesome|sounds\s+good"
    r"|hi|hey|hello|yo|sup|howdy|good\s+(morning|afternoon|evening|night)"
    r"|bye|goodbye|see\s+you|later|good\s*night|take\s+care"
    r"|yes|no|yep|nope|yeah|nah|sure|absolutely|definitely"
    r"|please|sorry|my\s+bad|no\s+worries"
    r"|what\s+do\s+you\s+mean|what\s+did\s+you\s+mean|can\s+you\s+explain"
    r"|huh\??|really\??|seriously\??"
    r"|lol|haha|ha|wow"
    r"|never\s*mind|forget\s+it|nvm"
    r")[\s?!.,]*$",
    re.IGNORECASE,
)


def _is_conversational(message: str) -> bool:
    """Return True if message is a conversational turn that needs no tools."""
    stripped = message.strip()
    if len(stripped) > 100:
        return False
    return bool(_CONVERSATIONAL_PATTERNS.match(stripped))


_GREETING_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|howdy|good\s+(morning|afternoon|evening))[\s?!.,]*$",
    re.IGNORECASE,
)

_NOTIF_QUERY_RE = re.compile(
    r"^(what'?s\s+new|any\s+(notifications?|updates?|news)|"
    r"what\s+did\s+i\s+miss|catch\s+me\s+up|"
    r"(show|get|read|check)\s+(my\s+)?(notifications?|updates?)|"
    r"anything\s+new|briefing|brief\s+me)[\s?!.,]*$",
    re.IGNORECASE,
)


def _is_greeting(message: str) -> bool:
    return bool(_GREETING_RE.match(message.strip()))


def _is_notification_query(message: str) -> bool:
    return bool(_NOTIF_QUERY_RE.match(message.strip()))


def _build_briefing_context() -> str:
    """Build briefing from pending notifications."""
    if not _db:
        return ""

    notifications = _db.get_pending_notifications(limit=20)
    log.info("Briefing: %d pending notification(s)", len(notifications))

    if not notifications:
        return ""

    parts: list[str] = []
    for n in notifications:
        entry = f"- [{n['type']}] {n['title']}"
        if n.get("body"):
            entry += f": {n['body']}"
        parts.append(entry)

    log.info("Briefing context: %d notification(s), %d chars", len(parts), sum(len(p) for p in parts))
    return "\n".join(parts)


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
            pinned = [f for f in facts if f.get("pinned")]
            learned = [f for f in facts if not f.get("pinned")]
            memory_parts = []
            if pinned:
                memory_parts.append("Core facts:\n" + "\n".join(f"- {f['fact']}" for f in pinned))
            if learned:
                memory_parts.append("Learned:\n" + "\n".join(f"- {f['fact']}" for f in learned))
            if memory_parts:
                persona_parts.append("About the user:\n" + "\n".join(memory_parts))

    if persona_parts:
        llm_messages.insert(0, {"role": "system", "content": "\n\n".join(persona_parts)})

    # Greeting or notification query — inject pending notifications as context
    is_first_message = len(history) <= 1  # Only the greeting itself
    greeting = _is_greeting(req.message) and is_first_message
    notif_query = _is_notification_query(req.message)

    async def stream_response():
        nonlocal llm_messages
        # Emit user message saved event
        yield _sse_event("message_saved", {
            "conversation_id": conv_id,
            "message": user_msg,
        })

        # Inject pending notifications as context for greetings or direct queries.
        # Briefings are formatted directly — no LLM — because the notification
        # data is already ground truth (title + snippet).  Cloud models hallucinate
        # when asked to "summarize" short factual data.
        if greeting or notif_query:
            from datetime import date, datetime, timezone
            _db.set_setting("last_greeting_at", datetime.now(timezone.utc).isoformat())
            notifications = _db.get_pending_notifications(limit=20)
            log.info("Briefing: %d pending notification(s)", len(notifications))

            if notifications:
                # Build direct briefing — present ground truth, no LLM
                hour = datetime.now().hour
                if hour < 12:
                    time_greeting = "Good morning"
                elif hour < 17:
                    time_greeting = "Good afternoon"
                else:
                    time_greeting = "Good evening"

                lines: list[str] = []
                for n in notifications:
                    body = (n.get("body") or "").strip()
                    if "\n" in body:
                        # Multi-line: title as header, body as block
                        lines.append(f"**{n['title']}**:\n{body}")
                    elif body:
                        lines.append(f"- **{n['title']}**: {body}")
                    else:
                        lines.append(f"- **{n['title']}**")

                if greeting:
                    direct_briefing = (
                        f"{time_greeting}! You have {len(notifications)} update{'s' if len(notifications) != 1 else ''}:\n\n"
                        + "\n".join(lines)
                    )
                else:
                    direct_briefing = (
                        f"You have {len(notifications)} notification{'s' if len(notifications) != 1 else ''}:\n\n"
                        + "\n".join(lines)
                    )

                log.info("Briefing direct (%s, %d notification(s))", "greeting" if greeting else "query", len(notifications))
                assistant_msg = _db.add_message(conv_id, role="assistant", content=direct_briefing)
                yield _sse_event("assistant_message", {
                    "conversation_id": conv_id,
                    "message": assistant_msg,
                })
                yield _sse_event("done", {"conversation_id": conv_id})
                _db.dismiss_all_notifications()
                log.info("Dismissed %d notification(s) after delivery", len(notifications))
                return

            elif notif_query:
                # No notifications — tell the user directly
                assistant_msg = _db.add_message(conv_id, role="assistant", content="No pending notifications — you're all caught up!")
                yield _sse_event("assistant_message", {
                    "conversation_id": conv_id,
                    "message": assistant_msg,
                })
                yield _sse_event("done", {"conversation_id": conv_id})
                return

            elif greeting:
                # Greeting with no notifications — respond directly
                hour = datetime.now().hour
                if hour < 12:
                    time_greeting = "Good morning"
                elif hour < 17:
                    time_greeting = "Good afternoon"
                else:
                    time_greeting = "Good evening"
                direct_greeting = (
                    f"{time_greeting}! Nothing new to report right now. "
                    "What can I help you with?"
                )
                assistant_msg = _db.add_message(conv_id, role="assistant", content=direct_greeting)
                yield _sse_event("assistant_message", {
                    "conversation_id": conv_id,
                    "message": assistant_msg,
                })
                yield _sse_event("done", {"conversation_id": conv_id})
                return

        # Route: conversational turns skip the tool bridge entirely
        conversational = _is_conversational(req.message) or greeting or notif_query
        try:
            if conversational:
                log.info("Conversational route: %r", req.message[:80])
                result = await execute_conversational(
                    discovery_url=_discovery_url,
                    messages=llm_messages,
                    model=model,
                    timeout=_discovery_timeout,
                )
            else:
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

        # Log debug trace from tool bridge
        if not conversational:
            raw = result.get("raw", {})
            dbg = raw.get("oap_debug", {})
            if dbg:
                log.info(
                    "Tool bridge: fingerprint=%s cache=%s escalated=%s tools=%s",
                    dbg.get("experience_fingerprint"),
                    dbg.get("experience_cache"),
                    dbg.get("escalated"),
                    dbg.get("tools_discovered"),
                )
                for rd in dbg.get("rounds", []):
                    for te in rd.get("tool_executions", []):
                        log.info(
                            "  Round %d: %s(%s) → %s (%dms)",
                            rd.get("round", "?"),
                            te.get("tool"),
                            json.dumps(te.get("arguments", {}), default=str)[:200],
                            (te.get("result", "")[:200] or "(empty)"),
                            te.get("duration_ms", 0),
                        )
                    resp_msg = rd.get("ollama_response", {})
                    if resp_msg.get("content"):
                        log.info("  Round %d LLM: %s", rd.get("round", "?"), resp_msg["content"][:300])
            elif raw.get("oap_experience_cache"):
                log.info("Tool bridge: cache=%s (debug not enabled)", raw["oap_experience_cache"])

        # Emit each tool call
        for tc in result.get("tool_calls", []):
            yield _sse_event("tool_call", tc)

        # Save assistant message
        metadata: dict = {}
        if result.get("experience_cache"):
            metadata["experience_cache"] = result["experience_cache"]
        if result.get("escalation_usage"):
            metadata["escalation_usage"] = result["escalation_usage"]
        if result.get("chat_usage"):
            metadata["chat_usage"] = result["chat_usage"]

        assistant_msg = _db.add_message(
            conv_id,
            role="assistant",
            content=result["content"],
            tool_calls=result["tool_calls"] or None,
            metadata=metadata or None,
        )

        # Record LLM usage — chat model (Ollama) + escalation (big LLM)
        if result.get("chat_usage"):
            cu = result["chat_usage"]
            _db.record_llm_usage(
                provider="ollama",
                model=cu["model"],
                input_tokens=cu["tokens_in"],
                output_tokens=cu["tokens_out"],
                conversation_id=conv_id,
                message_id=assistant_msg["id"],
            )
        if result.get("escalation_usage"):
            eu = result["escalation_usage"]
            _db.record_llm_usage(
                provider=eu["provider"],
                model=eu["model"],
                input_tokens=eu["input_tokens"],
                output_tokens=eu["output_tokens"],
                conversation_id=conv_id,
                message_id=assistant_msg["id"],
            )

        # Fire-and-forget: extract user memory from this turn
        if settings.get("memory_enabled") == "true" and result["content"]:
            from .memory import extract_and_store_facts
            asyncio.create_task(
                extract_and_store_facts(_db, _discovery_url, req.message, result["content"], model=req.model)
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
        incremental=req.incremental,
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
        incremental=req.incremental,
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

    prompt = _build_task_prompt(task)
    run = _db.create_run(task_id, prompt)
    run_id = run["id"]

    asyncio.create_task(_run_task_background(task, run_id, prompt))
    return {"run_id": run_id, "status": "accepted"}


def _build_task_prompt(task: dict) -> str:
    """Prepend last-run timestamp to the task prompt for dedup."""
    prompt = task["prompt"]
    if _db is None:
        return prompt
    last_run = _db.get_last_successful_run(task["id"])
    if last_run and last_run.get("finished_at"):
        prompt = f"[Only include new information since {last_run['finished_at']}]\n{prompt}"
        log.debug("Injected last-run timestamp %s into task %s", last_run["finished_at"], task["id"])
    return prompt


async def _run_task_background(task: dict, run_id: str, prompt: str) -> None:
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
                prompt=prompt,
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
        # Cleanup old runs for this task after each execution
        try:
            _db.cleanup_old_runs(max_per_task=100)
        except Exception:
            log.warning("Failed to cleanup old runs for task %s", task_id, exc_info=True)


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
# Notification routes
# ---------------------------------------------------------------------------

@app.get("/v1/agent/notifications")
async def get_notifications(limit: int = 50):
    """Get pending (undismissed) notifications."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return {
        "notifications": _db.get_pending_notifications(min(max(1, limit), 200)),
        "count": _db.count_pending_notifications(),
    }


@app.post("/v1/agent/notifications/{notif_id}/dismiss")
async def dismiss_notification(notif_id: str):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.dismiss_notification(notif_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"dismissed": True}


@app.post("/v1/agent/notifications/dismiss-all")
async def dismiss_all_notifications():
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    count = _db.dismiss_all_notifications()
    return {"dismissed": count}


@app.get("/v1/agent/notifications/count")
async def notification_count():
    """Lightweight endpoint for badge polling."""
    if _db is None:
        return {"count": 0}
    return {"count": _db.count_pending_notifications()}


@app.get("/v1/agent/models")
async def list_models():
    """Fetch available models from Ollama via the discovery service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_discovery_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        models = sorted(
            m["name"] for m in data.get("models", []) if "name" in m
        )
        return {"models": models, "default": _discovery_model}
    except Exception as exc:
        log.warning("Failed to fetch models from Ollama: %s", exc)
        return {"models": [_discovery_model], "default": _discovery_model}


# ---------------------------------------------------------------------------
# Usage routes
# ---------------------------------------------------------------------------

@app.get("/v1/agent/usage")
async def get_usage(days: int = 30):
    """Get LLM usage summary."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return _db.get_usage_summary(min(max(1, days), 365))


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
    if req.voice_tts_voice is not None:
        _db.set_setting("voice_tts_voice", req.voice_tts_voice)
    if req.voice_wake_word is not None:
        _db.set_setting("voice_wake_word", req.voice_wake_word)
    # Persist extra keys (e.g. persona_voice_kai, persona_voice_marvin)
    for key, value in (req.model_extra or {}).items():
        if re.fullmatch(r"persona_voice_[a-z0-9_]+", key) and isinstance(value, str) and len(value) <= 200:
            _db.set_setting(key, value)
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


class PinFactRequest(BaseModel):
    pinned: bool


@app.patch("/v1/agent/memory/{fact_id}/pin")
async def pin_memory(fact_id: str, req: PinFactRequest):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.pin_fact(fact_id, req.pinned):
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
        # Lightly bias Whisper toward the wake word spelling
        prompt = None
        if _db:
            settings = _db.get_settings()
            wake = settings.get("voice_wake_word") or settings.get("persona_name") or ""
            if wake:
                prompt = f"{wake},"
        text = tx.transcribe(tmp_path, language=_voice_cfg.language, initial_prompt=prompt)
        return {"text": text}
    finally:
        os.unlink(tmp_path)


@app.get("/v1/agent/voice/status")
async def voice_status():
    """Check if voice input/output is available."""
    stt_enabled = _voice_cfg is not None and _voice_cfg.enabled
    return {"enabled": stt_enabled, "tts_enabled": _tts_enabled}


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=10_000)
    voice: str | None = Field(None, max_length=200)


@app.post("/v1/agent/tts")
async def text_to_speech(req: TTSRequest):
    """Synthesize text to WAV audio via Piper TTS."""
    if not _tts_enabled:
        raise HTTPException(status_code=501, detail="TTS not enabled")
    from functools import partial
    from . import tts

    loop = asyncio.get_running_loop()
    wav_bytes = await loop.run_in_executor(None, partial(tts.synthesize, req.text, req.voice))
    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={"Content-Length": str(len(wav_bytes))},
    )


@app.post("/v1/agent/tts/stream")
async def text_to_speech_stream(req: TTSRequest):
    """Stream sentence-level WAV chunks as they are synthesized."""
    if not _tts_enabled:
        raise HTTPException(status_code=501, detail="TTS not enabled")
    from . import tts

    async def generate():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        def _produce():
            try:
                for wav_chunk in tts.synthesize_stream(req.text, req.voice):
                    loop.call_soon_threadsafe(queue.put_nowait, wav_chunk)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Run the blocking generator in a thread
        fut = loop.run_in_executor(None, _produce)
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                # Length-prefix: 4-byte big-endian uint32
                yield len(chunk).to_bytes(4, "big") + chunk
        finally:
            await fut  # ensure thread finishes

    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"X-TTS-Stream": "chunked-wav"},
    )


@app.get("/v1/agent/tts/voices")
async def tts_voices():
    """List available Piper voice models."""
    from . import tts

    models_dir = _voice_cfg.tts_models_dir if _voice_cfg else "piper-voices"
    voices = tts.list_voices(models_dir)
    current = tts.get_loaded_voice()
    return {"voices": voices, "current": current}


# ---------------------------------------------------------------------------
# Static files (Vite SPA) — catch-all for SPA client-side routing
# ---------------------------------------------------------------------------

from pathlib import Path
from fastapi.responses import FileResponse

_static_dir = Path(__file__).parent / "static"

if _static_dir.is_dir():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve static files or fall back to index.html for SPA routes."""
        if full_path:
            file_path = _static_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)
        return FileResponse(_static_dir / "index.html")


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
    # Ensure oap.agent loggers survive uvicorn's log reconfiguration
    oap_logger = logging.getLogger("oap.agent")
    oap_logger.setLevel(logging.INFO)
    oap_logger.propagate = False
    if not oap_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        oap_logger.addHandler(handler)

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
