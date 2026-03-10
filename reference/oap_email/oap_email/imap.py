"""Async IMAP scanner — fetch and parse messages from IMAP server."""

from __future__ import annotations

import email
import email.header
import email.utils
import hashlib
import logging
import re
from datetime import datetime, timezone
from email.message import Message
from typing import Any

import aioimaplib

from .config import IMAPConfig
from .sanitize import sanitize_email_body

log = logging.getLogger("oap.email.imap")


def _decode_header(raw: str | None) -> str:
    """Decode RFC 2047 encoded header value."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _parse_address(raw: str | None) -> dict:
    """Parse 'Name <email>' into {name, email}."""
    if not raw:
        return {"name": "", "email": ""}
    name, addr = email.utils.parseaddr(raw)
    return {"name": _decode_header(name), "email": addr}


def _parse_address_list(raw: str | None) -> list[dict]:
    """Parse comma-separated address list."""
    if not raw:
        return []
    addrs = email.utils.getaddresses([raw])
    return [{"name": _decode_header(name), "email": addr} for name, addr in addrs if addr]


def _parse_date(raw: str | None) -> str:
    """Parse email date header to ISO 8601."""
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except Exception:
        return raw


def _extract_thread_id(msg: Message) -> str:
    """Derive thread ID from References/In-Reply-To headers."""
    refs = msg.get("References", "") or ""
    in_reply = msg.get("In-Reply-To", "") or ""

    # Use the first message-id in the References chain (thread root)
    all_ids = re.findall(r"<[^>]+>", refs)
    if all_ids:
        root = all_ids[0]
    elif in_reply.strip():
        root = in_reply.strip()
    else:
        # Standalone message — use its own Message-ID as thread root
        root = msg.get("Message-ID", "") or ""

    if root:
        return "thr_" + hashlib.sha256(root.encode()).hexdigest()[:12]
    return ""


def _extract_body(msg: Message) -> tuple[str | None, str | None]:
    """Extract plain text and HTML body parts from a MIME message."""
    text_body = None
    html_body = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            if ct == "text/plain" and text_body is None:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_body = payload.decode(charset, errors="replace")
            elif ct == "text/html" and html_body is None:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ct == "text/html":
                html_body = text
            else:
                text_body = text

    return text_body, html_body


def _extract_attachments(msg: Message) -> list[dict]:
    """Extract attachment metadata (no content)."""
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        disp = str(part.get("Content-Disposition", ""))
        if "attachment" not in disp and "inline" not in disp:
            continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header(filename)
        payload = part.get_payload(decode=True)
        attachments.append({
            "filename": filename,
            "size_bytes": len(payload) if payload else 0,
            "content_type": part.get_content_type(),
        })
    return attachments


def parse_message(uid: int, folder: str, raw_bytes: bytes) -> dict[str, Any]:
    """Parse raw email bytes into a clean message dict."""
    msg = email.message_from_bytes(raw_bytes)

    message_id = msg.get("Message-ID", "") or ""
    thread_id = _extract_thread_id(msg)
    from_addr = _parse_address(msg.get("From"))
    to_addrs = _parse_address_list(msg.get("To"))
    cc_addrs = _parse_address_list(msg.get("Cc"))
    subject = _decode_header(msg.get("Subject"))
    received_at = _parse_date(msg.get("Date"))
    attachments = _extract_attachments(msg)

    text_body, html_body = _extract_body(msg)
    body_text = sanitize_email_body(text_body, html_body)
    snippet = body_text[:200] if body_text else ""

    # Stable ID from folder + UID
    stable_id = f"{folder}_{uid}"

    return {
        "id": stable_id,
        "message_id": message_id.strip("<>"),
        "thread_id": thread_id,
        "folder": folder,
        "from_name": from_addr["name"],
        "from_email": from_addr["email"],
        "to_addrs": to_addrs,
        "cc_addrs": cc_addrs,
        "subject": subject,
        "snippet": snippet,
        "body_text": body_text,
        "received_at": received_at,
        "has_attachments": len(attachments) > 0,
        "attachments": attachments,
        "uid": uid,
    }


async def scan_folder(
    cfg: IMAPConfig,
    folder: str = "INBOX",
    since_uid: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Connect to IMAP, fetch messages newer than since_uid.

    Returns parsed message dicts ready for DB upsert.
    """
    if cfg.use_ssl:
        client = aioimaplib.IMAP4_SSL(host=cfg.host, port=cfg.port)
    else:
        client = aioimaplib.IMAP4(host=cfg.host, port=cfg.port)

    try:
        await client.wait_hello_from_server()
        await client.login(cfg.username, cfg.password)
        await client.select(folder)

        # Search for messages with UID > since_uid
        if since_uid > 0:
            search_criteria = f"UID {since_uid + 1}:*"
        else:
            search_criteria = "ALL"

        result = await client.uid_search(search_criteria)
        # aioimaplib returns (status, [lines]) — UIDs are in the second element
        if result.result != "OK" or not result.lines:
            log.warning("IMAP search returned %s: %s", result.result, result.lines)
            return []

        # UIDs come as a space-separated string in the first line
        uid_line = result.lines[0] if result.lines else ""
        if not uid_line or not uid_line.strip():
            return []

        uids = uid_line.strip().split()
        if not uids:
            return []

        # Take the most recent ones
        uids = uids[-limit:]

        messages = []
        for uid_bytes in uids:
            uid_str = uid_bytes.decode() if isinstance(uid_bytes, bytes) else str(uid_bytes)
            uid_val = int(uid_str)

            # Skip UIDs we already have
            if uid_val <= since_uid:
                continue

            fetch_result = await client.uid("fetch", uid_str, "(RFC822 FLAGS)")
            if fetch_result.result != "OK" or not fetch_result.lines:
                continue

            # aioimaplib returns lines as a list — find the one with message bytes
            raw_bytes = None
            flags_str = ""
            for item in fetch_result.lines:
                if isinstance(item, bytes) and len(item) > 100:
                    raw_bytes = item
                elif isinstance(item, str) and "FLAGS" in item:
                    flags_str = item
                elif isinstance(item, bytes):
                    try:
                        decoded = item.decode("ascii", errors="ignore")
                        if "FLAGS" in decoded:
                            flags_str = decoded
                    except Exception:
                        pass

            if not raw_bytes:
                continue

            try:
                parsed = parse_message(uid_val, folder, raw_bytes)
                parsed["is_read"] = r"\Seen" in flags_str
                parsed["is_flagged"] = r"\Flagged" in flags_str
                messages.append(parsed)
            except Exception as exc:
                log.warning("Failed to parse UID %s in %s: %s", uid_str, folder, exc)
                continue

        log.info("Scanned %s: %d new message(s) (since UID %d)", folder, len(messages), since_uid)
        return messages

    finally:
        try:
            await client.logout()
        except Exception:
            pass
