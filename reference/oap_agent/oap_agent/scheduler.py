"""Task scheduler using APScheduler 3.x for cron-based task execution."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .executor import execute_task

if TYPE_CHECKING:
    from .db import AgentDB
    from .events import EventBus


log = logging.getLogger("oap.agent.scheduler")


class TaskScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._db: AgentDB | None = None
        self._event_bus: EventBus | None = None
        self._discovery_url: str = "http://localhost:8300"
        self._debug: bool = False

    def start(self, db: AgentDB, event_bus: EventBus, discovery_url: str, debug: bool = False) -> None:
        """Load all enabled tasks from DB and start the scheduler."""
        self._db = db
        self._event_bus = event_bus
        self._discovery_url = discovery_url
        self._debug = debug

        tasks = db.list_tasks()
        scheduled = 0
        for task in tasks:
            if task["enabled"] and task.get("schedule"):
                try:
                    self._add_job(task)
                    scheduled += 1
                except Exception as exc:
                    log.warning("Could not schedule task %s: %s", task["id"], exc)

        self._scheduler.start()
        log.info("Scheduler started — %d tasks scheduled", scheduled)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def schedule_task(self, task: dict) -> None:
        """Add or replace a job for the given task."""
        self.unschedule_task(task["id"])
        if task.get("enabled") and task.get("schedule"):
            self._add_job(task)

    def unschedule_task(self, task_id: str) -> None:
        """Remove the job for the given task, if it exists."""
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass

    def _add_job(self, task: dict) -> None:
        trigger = CronTrigger.from_crontab(task["schedule"])
        self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task["id"],
            args=[task["id"]],
            replace_existing=True,
            misfire_grace_time=60,
        )
        log.debug("Scheduled task %s (%s) with cron %s", task["id"], task["name"], task["schedule"])

    async def _execute_task(self, task_id: str) -> None:
        """Called by the scheduler to run a task."""
        if self._db is None:
            return

        task = self._db.get_task(task_id)
        if not task:
            log.warning("Scheduled task %s not found in DB", task_id)
            return

        run = self._db.create_run(task_id, task["prompt"])
        run_id = run["id"]
        started = time.monotonic()

        log.info("Running task %s (%s) run=%s", task_id, task["name"], run_id)

        if self._event_bus:
            await self._event_bus.publish("task_run_started", {
                "task_id": task_id,
                "run_id": run_id,
                "task_name": task["name"],
            })

        try:
            result = await execute_task(
                discovery_url=self._discovery_url,
                prompt=task["prompt"],
                model=task.get("model", "qwen3:8b"),
                timeout=120,
                debug=self._debug,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            finished = self._db.finish_run(
                run_id=run_id,
                status="success",
                response=result["content"],
                tool_calls=result["tool_calls"] or None,
                duration_ms=duration_ms,
            )
            log.info("Task run %s completed in %dms", run_id, duration_ms)

            if self._event_bus:
                await self._event_bus.publish("task_run_finished", {
                    "task_id": task_id,
                    "run_id": run_id,
                    "status": "success",
                    "duration_ms": duration_ms,
                })

        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.error("Task run %s failed: %s", run_id, exc, exc_info=True)
            error_msg = f"Task execution failed: {exc}"
            self._db.finish_run(
                run_id=run_id,
                status="error",
                error=error_msg,
                duration_ms=duration_ms,
            )

            if self._event_bus:
                await self._event_bus.publish("task_run_finished", {
                    "task_id": task_id,
                    "run_id": run_id,
                    "status": "error",
                    "error": error_msg,
                    "task_name": task["name"],
                })
