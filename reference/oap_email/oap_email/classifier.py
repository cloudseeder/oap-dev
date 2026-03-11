"""Email classifier — categorizes messages using a local LLM."""

from __future__ import annotations

import logging

import httpx

from .config import ClassifierConfig

log = logging.getLogger("oap.email.classifier")

CATEGORIES = ("spam", "marketing", "transactional", "inbox")

_SYSTEM_PROMPT = (
    "Classify this email into exactly one category.\n\n"
    "spam — junk, phishing, unsolicited\n"
    "marketing — newsletters, offers, sales, subscriptions\n"
    "transactional — receipts, shipping, account alerts, auth codes\n"
    "inbox — real human correspondence, anything that doesn't clearly fit above\n\n"
    "Respond with ONLY the category name, nothing else."
)


async def classify_message(
    cfg: ClassifierConfig,
    from_name: str,
    from_email: str,
    subject: str,
    snippet: str,
) -> str | None:
    """Classify a single email message. Returns category or None on failure."""
    user_msg = f"From: {from_name} <{from_email}>\nSubject: {subject}\n\n{snippet}"

    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {"num_ctx": 2048},
        "think": False,
    }

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(
                f"{cfg.ollama_url.rstrip('/')}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("Classification failed: %s", exc)
        return None

    content = data.get("message", {}).get("content", "").strip().lower()
    # Extract category — handle models that add extra text
    for cat in CATEGORIES:
        if cat in content:
            return cat

    log.warning("Unrecognized category %r — defaulting to inbox", content)
    return "inbox"


async def classify_uncategorized(cfg: ClassifierConfig, db) -> int:
    """Classify all uncategorized messages in the database. Returns count."""
    rows = db.get_uncategorized(limit=50)
    if not rows:
        return 0

    classified = 0
    for row in rows:
        category = await classify_message(
            cfg,
            from_name=row.get("from_name", ""),
            from_email=row.get("from_email", ""),
            subject=row.get("subject", ""),
            snippet=row.get("snippet", ""),
        )
        if category:
            db.set_category(row["id"], category)
            classified += 1

    log.info("Classified %d/%d message(s)", classified, len(rows))
    return classified
