"""Email classifier — categorizes messages using a local LLM."""

from __future__ import annotations

import logging

import httpx

from .config import ClassifierConfig

log = logging.getLogger("oap.email.classifier")

_client: httpx.AsyncClient | None = None
_client_timeout: int = 0


def _get_client(cfg) -> httpx.AsyncClient:
    """Return a reusable async HTTP client, creating one if needed."""
    global _client, _client_timeout
    if _client is None or _client.is_closed or _client_timeout != cfg.timeout:
        if _client and not _client.is_closed:
            # Can't await close here, just let it GC
            pass
        _client = httpx.AsyncClient(timeout=cfg.timeout)
        _client_timeout = cfg.timeout
    return _client


# Legacy category mapping for pre-existing cached responses
_LEGACY = {"inbox": "personal", "transactional": "machine", "marketing": "mailing-list"}


def _build_system_prompt(categories: dict[str, str]) -> str:
    """Build classifier system prompt from category definitions."""
    lines = ["Classify this email into exactly one category.\n"]
    for name, description in categories.items():
        lines.append(f"{name} — {description}")
    lines.append("\nRespond with ONLY the category name, nothing else.")
    return "\n".join(lines)


async def classify_message(
    cfg: ClassifierConfig,
    from_name: str,
    from_email: str,
    subject: str,
    snippet: str,
) -> str | None:
    """Classify a single email message. Returns category or None on failure."""
    user_msg = f"From: {from_name} <{from_email}>\nSubject: {subject}\n\n{snippet}"
    system_prompt = _build_system_prompt(cfg.categories)

    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {"num_ctx": 2048},
        "think": False,
    }

    try:
        client = _get_client(cfg)
        resp = await client.post(
            f"{cfg.ollama_url.rstrip('/')}/api/chat",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Classification failed for %s <%s> subject=%r: %s: %s",
                     from_name, from_email, subject[:60], type(exc).__name__, exc)
        return None

    content = data.get("message", {}).get("content", "").strip().lower()
    # Normalize variations: "mailing list" → "mailing-list"
    content = content.replace(" ", "-") if "-" in "".join(cfg.categories) else content
    content = content.replace("mailing list", "mailing-list")
    # Extract category — handle models that add extra text
    for cat in cfg.categories:
        if cat in content:
            return cat
    # Legacy category mapping
    for old, new in _LEGACY.items():
        if old in content and new in cfg.categories:
            return new

    # Default to first category
    default = next(iter(cfg.categories))
    log.warning("Unrecognized category %r — defaulting to %s", content, default)
    return default


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
