"""Email classifier — categorizes messages using a local LLM."""

from __future__ import annotations

import logging

import httpx

from .config import ClassifierConfig

log = logging.getLogger("oap.email.classifier")

CATEGORIES = ("personal", "machine", "mailing-list", "spam", "offers")

_SYSTEM_PROMPT = (
    "Classify this email into exactly one category.\n\n"
    "personal — written by a real human (colleague, friend, family, client)\n"
    "machine — automated/system-generated (server alerts, cron output, cPanel, "
    "disk space warnings, security scans, WordPress updates, CI/CD, monitoring)\n"
    "mailing-list — newsletters, digests, mailing list posts, group emails\n"
    "spam — junk, phishing, unsolicited bulk email\n"
    "offers — sales, promotions, deals, coupons, limited-time discounts\n\n"
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
    # Normalize variations: "mailing list" → "mailing-list"
    content = content.replace("mailing list", "mailing-list")
    # Extract category — handle models that add extra text
    for cat in CATEGORIES:
        if cat in content:
            return cat
    # Legacy category mapping for pre-existing cached responses
    _LEGACY = {"inbox": "personal", "transactional": "machine", "marketing": "mailing-list"}
    for old, new in _LEGACY.items():
        if old in content:
            return new

    log.warning("Unrecognized category %r — defaulting to personal", content)
    return "personal"


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
            log.info("%-13s  %s — %s", category, row.get("from_email", "?"), row.get("subject", "")[:60])

    log.info("Classified %d/%d message(s)", classified, len(rows))
    return classified
