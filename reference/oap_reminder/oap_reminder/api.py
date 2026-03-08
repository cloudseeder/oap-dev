"""FastAPI application for the OAP reminder service."""

from __future__ import annotations

import argparse
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from .config import load_config
from .db import ReminderDB
from .models import ReminderCreate, ReminderUpdate

log = logging.getLogger("oap.reminder")

_db: ReminderDB | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db
    cfg = load_config()
    _db = ReminderDB(cfg.db_path)
    log.info("Reminder service started (db=%s)", cfg.db_path)
    yield
    if _db:
        _db.close()


app = FastAPI(title="OAP Reminder Service", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request, call_next):
    if request.method == "POST" and "/reminders" in request.url.path:
        body = await request.body()
        log.info("POST %s body=%s", request.url.path, body.decode(errors="replace")[:500])
        # Reconstruct request with body (consumed by reading)
        from starlette.requests import Request
        from io import BytesIO

        async def receive():
            return {"type": "http.request", "body": body}
        request = Request(request.scope, receive)
    response = await call_next(request)
    if request.method == "POST" and "/reminders" in request.url.path and response.status_code >= 400:
        log.warning("POST %s → %d", request.url.path, response.status_code)
    return response


@app.get("/health")
async def health():
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    _, total = _db.list_all(limit=0)
    return {"status": "ok", "total": total}


@app.get("/feed.ics")
async def ical_feed():
    """iCalendar feed of pending reminders for Apple/Google Calendar subscription."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")

    reminders, _ = _db.list_all(status="pending", limit=500)
    now = datetime.now().strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OAP//Reminder Service//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:OAP Reminders",
    ]

    for r in reminders:
        uid = hashlib.md5(f"oap-reminder-{r['id']}".encode()).hexdigest()
        # Build DTSTART from due_date + due_time
        if r.get("due_date"):
            date_str = r["due_date"].replace("-", "")
            if r.get("due_time"):
                time_str = r["due_time"].replace(":", "") + "00"
                dtstart = f"DTSTART:{date_str}T{time_str}"
                # 1-hour default duration for timed events
                dtend_h = int(r["due_time"][:2]) + 1
                dtend = f"DTEND:{date_str}T{dtend_h:02d}{r['due_time'][3:5]}00"
            else:
                dtstart = f"DTSTART;VALUE=DATE:{date_str}"
                dtend = f"DTEND;VALUE=DATE:{date_str}"
        else:
            # No due date — use created_at
            created = r.get("created_at", "").replace("-", "").replace(":", "").replace("T", "T")[:15]
            dtstart = f"DTSTART:{created or now}"
            dtend = f"DTEND:{created or now}"

        summary = (r.get("title") or "Reminder").replace(",", "\\,").replace("\n", "\\n")
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}@oap-reminder")
        lines.append(f"DTSTAMP:{now}")
        lines.append(dtstart)
        lines.append(dtend)
        lines.append(f"SUMMARY:{summary}")
        if r.get("notes"):
            desc = r["notes"].replace(",", "\\,").replace("\n", "\\n")
            lines.append(f"DESCRIPTION:{desc}")
        if r.get("recurring"):
            freq = r["recurring"].upper()
            lines.append(f"RRULE:FREQ={freq}")
        lines.append("BEGIN:VALARM")
        lines.append("TRIGGER:-PT15M")
        lines.append("ACTION:DISPLAY")
        lines.append(f"DESCRIPTION:{summary}")
        lines.append("END:VALARM")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    ical = "\r\n".join(lines) + "\r\n"

    return Response(
        content=ical,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": "inline; filename=oap-reminders.ics"},
    )


@app.post("/api")
async def dispatch(body: dict):
    """Single-endpoint dispatcher for LLM tool calls.

    Accepts {"action": "...", ...params} and routes to the right operation.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")

    action = (body.pop("action", None) or body.pop("function", None) or "create").lower().strip()
    log.info("Dispatch action=%r params=%r", action, {k: v for k, v in body.items() if k != "notes"})

    if action in ("create", "add", "set", "new"):
        validated = ReminderCreate(**body)
        return _db.create(
            title=validated.title,
            notes=validated.notes,
            due_date=validated.due_date,
            due_time=validated.due_time,
            recurring=validated.recurring,
        )
    elif action in ("list", "list_all", "show", "all"):
        reminders, total = _db.list_all(
            status=body.get("status"),
            limit=int(body.get("limit", 50)),
        )
        return {"reminders": reminders, "total": total}
    elif action in ("due", "due_today", "overdue", "upcoming", "today"):
        reminders = _db.list_due(before=body.get("before"))
        return {"reminders": reminders, "total": len(reminders)}
    elif action in ("complete", "done", "finish"):
        rid = body.get("id") or body.get("reminder_id")
        if not rid:
            raise HTTPException(status_code=400, detail="'id' required for complete")
        result = _db.complete(int(rid))
        if not result:
            raise HTTPException(status_code=404, detail="Reminder not found")
        return result
    elif action in ("delete", "remove", "cancel"):
        rid = body.get("id") or body.get("reminder_id")
        if not rid:
            raise HTTPException(status_code=400, detail="'id' required for delete")
        if not _db.delete(int(rid)):
            raise HTTPException(status_code=404, detail="Reminder not found")
        return {"deleted": int(rid)}
    elif action in ("get", "fetch", "find"):
        rid = body.get("id") or body.get("reminder_id")
        if not rid:
            raise HTTPException(status_code=400, detail="'id' required for get")
        reminder = _db.get(int(rid))
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        return reminder
    elif action in ("cleanup", "purge"):
        days = int(body.get("older_than_days", 30))
        deleted = _db.cleanup_completed(days)
        return {"deleted": deleted, "older_than_days": days}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}. Use: create, list, due, complete, delete, get, cleanup")


@app.post("/reminders", status_code=201)
async def create_reminder(body: ReminderCreate):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    log.info("Create reminder: title=%r due_date=%r due_time=%r recurring=%r",
             body.title, body.due_date, body.due_time, body.recurring)
    reminder = _db.create(
        title=body.title,
        notes=body.notes,
        due_date=body.due_date,
        due_time=body.due_time,
        recurring=body.recurring,
    )
    return reminder


@app.get("/reminders")
async def list_reminders(
    status: str | None = Query(None, pattern="^(pending|completed)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    reminders, total = _db.list_all(status=status, limit=limit, offset=offset)
    return {"reminders": reminders, "total": total}


@app.get("/reminders/due")
async def list_due(before: str | None = Query(None)):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    reminders = _db.list_due(before=before)
    return {"reminders": reminders, "total": len(reminders)}


@app.post("/reminders/cleanup")
async def cleanup_reminders(older_than_days: int = Query(30, ge=1)):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    deleted = _db.cleanup_completed(older_than_days)
    return {"deleted": deleted, "older_than_days": older_than_days}


@app.get("/reminders/{reminder_id}")
async def get_reminder(reminder_id: int):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    reminder = _db.get(reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder


@app.patch("/reminders/{reminder_id}")
async def update_reminder(reminder_id: int, body: ReminderUpdate):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    reminder = _db.update(reminder_id, **fields)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder


@app.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: int):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    result = _db.complete(reminder_id)
    if not result:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return result


@app.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(reminder_id: int):
    if _db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    if not _db.delete(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")


def main():
    parser = argparse.ArgumentParser(description="OAP Reminder API")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--cleanup", type=int, metavar="DAYS", nargs="?", const=30,
                        help="Delete completed reminders older than DAYS (default 30) and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)

    if args.cleanup is not None:
        db = ReminderDB(cfg.db_path)
        deleted = db.cleanup_completed(args.cleanup)
        print(f"Deleted {deleted} completed reminders older than {args.cleanup} days")
        db.close()
        return

    host = args.host or cfg.host
    port = args.port or cfg.port
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
