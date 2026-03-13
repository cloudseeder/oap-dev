"""IMAP scanner — fetch and parse messages from IMAP server."""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
import hashlib
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.message import Message
from typing import Any

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
    """Parse email date header to ISO 8601 UTC.

    Always normalizes to UTC so SQLite string comparison works correctly
    across messages with different timezone offsets.
    """
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
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


def _scan_folder_sync(
    cfg: IMAPConfig,
    folder: str = "INBOX",
    since_uid: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Connect to IMAP, fetch messages newer than since_uid (sync version)."""
    if cfg.use_ssl:
        conn = imaplib.IMAP4_SSL(cfg.host, cfg.port)
    else:
        conn = imaplib.IMAP4(cfg.host, cfg.port)

    try:
        conn.login(cfg.username, cfg.password)
        status, select_data = conn.select(folder, readonly=True)
        if status != "OK":
            log.error("IMAP SELECT %s failed: %s", folder, select_data)
            return []

        msg_count = int(select_data[0])
        log.info("IMAP %s: %d total messages", folder, msg_count)

        if msg_count == 0:
            return []

        # Search for all messages (or by UID range for incremental)
        if since_uid > 0:
            status, data = conn.uid("SEARCH", None, f"UID {since_uid + 1}:*")
        else:
            status, data = conn.uid("SEARCH", None, "ALL")

        if status != "OK" or not data or not data[0]:
            log.warning("IMAP SEARCH returned %s: %s", status, data)
            return []

        uid_list = data[0].split()
        log.info("IMAP SEARCH found %d UID(s)", len(uid_list))

        if not uid_list:
            return []

        # Initial scan (no cached UIDs): fetch all messages
        # Incremental scan: limit to most recent N new messages
        if since_uid > 0:
            uid_list = uid_list[-limit:]

        messages = []
        for uid_bytes in uid_list:
            uid_str = uid_bytes.decode() if isinstance(uid_bytes, bytes) else str(uid_bytes)
            uid_val = int(uid_str)

            if uid_val <= since_uid:
                continue

            # Fetch message
            status, msg_data = conn.uid("FETCH", uid_str, "(RFC822 FLAGS)")
            if status != "OK" or not msg_data:
                continue

            # Find the RFC822 body in the response
            raw_bytes = None
            flags_str = ""
            for part in msg_data:
                if isinstance(part, tuple) and len(part) == 2:
                    header_line = part[0].decode("ascii", errors="ignore") if isinstance(part[0], bytes) else str(part[0])
                    if b"RFC822" in part[0] if isinstance(part[0], bytes) else "RFC822" in header_line:
                        raw_bytes = part[1]
                        flags_str = header_line
                        break

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
            conn.logout()
        except Exception:
            pass


async def scan_folder(
    cfg: IMAPConfig,
    folder: str = "INBOX",
    since_uid: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Async wrapper — runs sync IMAP in a thread to avoid blocking."""
    return await asyncio.to_thread(_scan_folder_sync, cfg, folder, since_uid, limit)


def _move_messages_sync(
    cfg: IMAPConfig,
    moves: list[tuple[str, int, str]],
) -> set[int]:
    """Move messages to target IMAP folders. Each move is (source_folder, uid, target_folder).

    Creates target folders if they don't exist. Returns set of UIDs successfully moved.
    """
    if not moves:
        return set()

    if cfg.use_ssl:
        conn = imaplib.IMAP4_SSL(cfg.host, cfg.port)
    else:
        conn = imaplib.IMAP4(cfg.host, cfg.port)

    try:
        conn.login(cfg.username, cfg.password)
        moved_uids: set[int] = set()
        created_folders: set[str] = set()

        # Detect IMAP namespace prefix (e.g. "INBOX." for Dovecot/cPanel)
        prefix = ""
        try:
            status, ns_data = conn.namespace()
            if status == "OK" and ns_data and ns_data[0]:
                raw = ns_data[0].decode() if isinstance(ns_data[0], bytes) else str(ns_data[0])
                import re as _re
                m = _re.search(r'\(\("([^"]*)"', raw)
                if m:
                    prefix = m.group(1)
        except Exception:
            pass
        # Fallback: if source folder is INBOX, assume "INBOX." prefix
        # (standard for Dovecot, cPanel, and most IMAP servers)
        if not prefix:
            for source in by_source:
                if source.upper() == "INBOX":
                    prefix = "INBOX."
                    break
        if prefix:
            log.info("IMAP namespace prefix: %r", prefix)

        # Group by source folder to minimize SELECT calls
        by_source: dict[str, list[tuple[int, str]]] = {}
        for source, uid, target in moves:
            by_source.setdefault(source, []).append((uid, target))

        for source_folder, uid_targets in by_source.items():
            status, _ = conn.select(source_folder)
            if status != "OK":
                log.error("IMAP SELECT %s failed", source_folder)
                continue

            for uid, target_folder in uid_targets:
                # Apply namespace prefix if needed (e.g. "Personal" → "INBOX.Personal")
                full_target = target_folder
                if prefix and not target_folder.startswith(prefix):
                    full_target = prefix + target_folder

                # Create target folder if needed (once per folder)
                if full_target not in created_folders:
                    cs, cd = conn.create(full_target)
                    log.info("IMAP CREATE %s: %s %s", full_target, cs, cd)
                    conn.subscribe(full_target)
                    created_folders.add(full_target)

                uid_str = str(uid)
                status, data = conn.uid("COPY", uid_str, full_target)
                if status == "OK":
                    conn.uid("STORE", uid_str, "+FLAGS", "(\\Deleted)")
                    moved_uids.add(uid)
                else:
                    log.warning("IMAP COPY UID %s → %s failed: %s %s", uid_str, full_target, status, data)

            # Expunge deleted messages from source folder
            conn.expunge()

        log.info("IMAP filed %d/%d message(s)", len(moved_uids), len(moves))
        return moved_uids

    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def move_messages(
    cfg: IMAPConfig,
    moves: list[tuple[str, int, str]],
) -> set[int]:
    """Async wrapper for IMAP move. Returns set of UIDs successfully moved."""
    return await asyncio.to_thread(_move_messages_sync, cfg, moves)
