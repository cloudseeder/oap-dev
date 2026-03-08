"""Pydantic models for the reminder API."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_RECURRING_VALUES = {"daily", "weekly", "monthly", "yearly"}


class ReminderCreate(BaseModel):
    title: str
    notes: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    recurring: str | None = None

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
        if v and not _DATE_RE.match(v):
            raise ValueError("due_date must be YYYY-MM-DD")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM")
        return v

    @field_validator("recurring")
    @classmethod
    def validate_recurring(cls, v: str | None) -> str | None:
        if v and v not in _RECURRING_VALUES:
            raise ValueError(f"recurring must be one of {_RECURRING_VALUES}")
        return v


class ReminderUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    recurring: str | None = None
    status: str | None = None

    @field_validator("due_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v and not _DATE_RE.match(v):
            raise ValueError("due_date must be YYYY-MM-DD")
        return v

    @field_validator("due_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        if v and not _TIME_RE.match(v):
            raise ValueError("due_time must be HH:MM")
        return v

    @field_validator("recurring")
    @classmethod
    def validate_recurring(cls, v: str | None) -> str | None:
        if v and v not in _RECURRING_VALUES:
            raise ValueError(f"recurring must be one of {_RECURRING_VALUES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v and v not in ("pending", "completed"):
            raise ValueError("status must be 'pending' or 'completed'")
        return v
