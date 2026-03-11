"""Task scheduler using APScheduler 3.x for cron-based task execution."""

from __future__ import annotations

import asyncio
import logging
import re
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
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def semaphore(self) -> asyncio.Semaphore | None:
        return self._semaphore

    def start(self, db: AgentDB, event_bus: EventBus, discovery_url: str, debug: bool = False, max_concurrent: int = 1) -> None:
        """Load all enabled tasks from DB and start the scheduler."""
        self._db = db
        self._event_bus = event_bus
        self._discovery_url = discovery_url
        self._debug = debug
        self._semaphore = asyncio.Semaphore(max_concurrent)

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

    def _build_prompt(self, task: dict) -> str:
        """Prepend last-run timestamp to the task prompt for dedup."""
        prompt = task["prompt"]
        last_run = self._db.get_last_successful_run(task["id"])
        if last_run and last_run.get("finished_at"):
            prompt = f"[Only include new information since {last_run['finished_at']}]\n{prompt}"
            log.debug("Injected last-run timestamp %s into task %s", last_run["finished_at"], task["id"])
        return prompt

    _NO_NEWS_RE = re.compile(
        r"(no\s+new\s+(email|message|notification|update|result|item)|"
        r"nothing\s+new|no\s+updates?|no\s+results?\s+found|"
        r"all\s+caught\s+up|no\s+changes?|"
        r"0\s+(new\s+)?(email|message|notification|unread))",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_snippet(content: str, max_len: int = 120) -> str:
        """Extract a concise one-line summary from task output."""
        text = content.strip()
        # Take the first sentence (period, exclamation, or question mark followed by space/end)
        m = re.match(r"(.+?[.!?])(?:\s|$)", text, re.DOTALL)
        line = m.group(1).strip() if m else text
        # Collapse whitespace
        line = re.sub(r"\s+", " ", line)
        if len(line) <= max_len:
            return line
        # Truncate at last word boundary before max_len
        truncated = line[:max_len].rsplit(" ", 1)[0]
        return truncated + "…"

    def _is_empty_result(self, content: str) -> bool:
        """Return True if the task output indicates nothing new/actionable."""
        text = content.strip()
        # Long responses have substantive content even if they mention
        # "no new X" in passing — only filter short ones.
        if len(text) > 300:
            return False
        return bool(self._NO_NEWS_RE.search(text))

    async def _execute_task(self, task_id: str) -> None:
        """Called by the scheduler to run a task."""
        if self._db is None:
            return

        task = self._db.get_task(task_id)
        if not task:
            log.warning("Scheduled task %s not found in DB", task_id)
            return

        prompt = self._build_prompt(task)
        run = self._db.create_run(task_id, prompt)
        run_id = run["id"]

        if self._semaphore:
            log.info("Task %s (%s) run=%s queued (waiting for slot)", task_id, task["name"], run_id)
            await self._semaphore.acquire()

        try:
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
                    prompt=prompt,
                    model=task.get("model", "qwen3:8b"),
                    timeout=120,
                    debug=True,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                self._db.finish_run(
                    run_id=run_id,
                    status="success",
                    response=result["content"],
                    tool_calls=result["tool_calls"] or None,
                    duration_ms=duration_ms,
                )
                log.info("Task run %s completed in %dms", run_id, duration_ms)

                # Create notification from task result — skip empty/no-news results
                content = result.get("content", "")
                has_news = content.strip() and not self._is_empty_result(content)
                if has_news:
                    snippet = self._extract_snippet(content)
                    self._db.add_notification(
                        type="task_result",
                        title=task["name"],
                        body=snippet,
                        source="scheduler",
                        task_id=task_id,
                        run_id=run_id,
                    )
                else:
                    log.info("Task %s produced no-news result — skipping notification", task["name"])

                if self._event_bus:
                    await self._event_bus.publish("task_run_finished", {
                        "task_id": task_id,
                        "run_id": run_id,
                        "status": "success",
                        "duration_ms": duration_ms,
                        "task_name": task["name"],
                    })
                    if has_news:
                        await self._event_bus.publish("notification_new", {
                            "task_name": task["name"],
                            "count": self._db.count_pending_notifications(),
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
        finally:
            if self._semaphore:
                self._semaphore.release()
