"""Pydantic models for the reminder API."""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, field_validator, model_validator


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_RECURRING_VALUES = {"daily", "weekly", "monthly", "yearly"}

# Common time patterns LLMs produce
_TIME_12H = re.compile(r"^(\d{1,2}):?(\d{2})?\s*(am|pm)$", re.IGNORECASE)
_TIME_24H_SECS = re.compile(r"^(\d{2}):(\d{2}):\d{2}$")


def _normalize_time(v: str | None) -> str | None:
    """Normalize various time formats to HH:MM."""
    if not v:
        return v
    v = v.strip()
    if _TIME_RE.match(v):
        return v
    # 24h with seconds: "17:00:00" → "17:00"
    m = _TIME_24H_SECS.match(v)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    # 12h: "5 PM", "5:00 PM", "5:00pm" → "17:00"
    m = _TIME_12H.match(v)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        is_pm = m.group(3).lower() == "pm"
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    return v


def _normalize_date(v: str | None) -> str | None:
    """Normalize date strings to YYYY-MM-DD."""
    if not v:
        return v
    v = v.strip()
    if _DATE_RE.match(v):
        return v
    # Try "today", "tomorrow"
    low = v.lower()
    if low == "today":
        return date.today().isoformat()
    if low == "tomorrow":
        from datetime import timedelta
        return (date.today() + timedelta(days=1)).isoformat()
    # Try "tonight" → today
    if low == "tonight":
        return date.today().isoformat()
    # Try parsing common formats
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return v


class ReminderCreate(BaseModel):
    model_config = {"extra": "allow"}

    title: str
    notes: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    recurring: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: dict) -> dict:
        """Accept common field name aliases that LLMs produce."""
        if isinstance(data, dict):
            # date/time aliases
            for alias in ("date", "reminder_date", "day"):
                if alias in data and "due_date" not in data:
                    data["due_date"] = data.pop(alias)
            for alias in ("time", "reminder_time"):
                if alias in data and "due_time" not in data:
                    data["due_time"] = data.pop(alias)
            for alias in ("description", "body", "message", "detail", "details"):
                if alias in data and "notes" not in data:
                    data["notes"] = data.pop(alias)
            for alias in ("repeat", "recurrence", "frequency"):
                if alias in data and "recurring" not in data:
                    data["recurring"] = data.pop(alias)
            for alias in ("name", "reminder", "task", "subject"):
                if alias in data and "title" not in data:
                    data["title"] = data.pop(alias)
        return data

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        return v

    @field_validator("due_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        v = _normalize_date(v)
        if v and not _DATE_RE.match(v):
            raise ValueError("due_date must be YYYY-MM-DD (or 'today', 'tomorrow')")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        v = _normalize_time(v)
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM (or '5 PM', '5:00 PM')")
        return v

    @field_validator("recurring")
    @classmethod
    def validate_recurring(cls, v: str | None) -> str | None:
        if v and v.lower() in ("none", "null", ""):
            return None
        if v and v not in _RECURRING_VALUES:
            raise ValueError(f"recurring must be one of {_RECURRING_VALUES}")
        return v


class ReminderUpdate(BaseModel):
    model_config = {"extra": "allow"}

    title: str | None = None
    notes: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    recurring: str | None = None
    status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: dict) -> dict:
        if isinstance(data, dict):
            for alias in ("date", "reminder_date", "day"):
                if alias in data and "due_date" not in data:
                    data["due_date"] = data.pop(alias)
            for alias in ("time", "reminder_time"):
                if alias in data and "due_time" not in data:
                    data["due_time"] = data.pop(alias)
            for alias in ("description", "body", "message", "detail", "details"):
                if alias in data and "notes" not in data:
                    data["notes"] = data.pop(alias)
            for alias in ("repeat", "recurrence", "frequency"):
                if alias in data and "recurring" not in data:
                    data["recurring"] = data.pop(alias)
            for alias in ("name", "reminder", "task", "subject"):
                if alias in data and "title" not in data:
                    data["title"] = data.pop(alias)
        return data

    @field_validator("due_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        v = _normalize_date(v)
        if v and not _DATE_RE.match(v):
            raise ValueError("due_date must be YYYY-MM-DD (or 'today', 'tomorrow')")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        v = _normalize_time(v)
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM (or '5 PM', '5:00 PM')")
        return v

    @field_validator("recurring")
    @classmethod
    def validate_recurring(cls, v: str | None) -> str | None:
        if v and v.lower() in ("none", "null", ""):
            return None
        if v and v not in _RECURRING_VALUES:
            raise ValueError(f"recurring must be one of {_RECURRING_VALUES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v and v not in ("pending", "completed"):
            raise ValueError("status must be 'pending' or 'completed'")
        return v
