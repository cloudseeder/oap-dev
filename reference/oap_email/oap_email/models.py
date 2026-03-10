"""Pydantic models for oap-email."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmailAddress(BaseModel):
    name: str = ""
    email: str


class Attachment(BaseModel):
    filename: str
    size_bytes: int = 0
    content_type: str = "application/octet-stream"


class EmailMessage(BaseModel):
    id: str
    message_id: str = ""  # RFC Message-ID header
    thread_id: str = ""
    folder: str = "INBOX"
    from_addr: EmailAddress = Field(alias="from")
    to: list[EmailAddress] = []
    cc: list[EmailAddress] = []
    subject: str = ""
    snippet: str = ""  # First 200 chars
    body_text: str = ""  # Full sanitized plain text
    received_at: str = ""
    is_read: bool = True
    is_flagged: bool = False
    has_attachments: bool = False
    attachments: list[Attachment] = []
    thread_length: int = 1

    model_config = {"populate_by_name": True}


class EmailThread(BaseModel):
    thread_id: str
    subject: str = ""
    participants: list[EmailAddress] = []
    messages: list[EmailMessage] = []
    message_count: int = 0


class EmailSummary(BaseModel):
    period_from: str
    period_to: str
    total_received: int = 0
    unread_count: int = 0
    senders: list[str] = []  # Unique sender names
    subjects: list[str] = []  # Recent subjects for context


class DispatchRequest(BaseModel):
    """Single-endpoint dispatcher for OAP tool bridge."""
    action: str = Field(..., description="Operation: list, get, thread, summary")
    id: str | None = None
    thread_id: str | None = None
    since: str | None = None
    limit: int = Field(20, ge=1, le=100)
    unread: bool = False
    folder: str = "INBOX"
    query: str | None = None
