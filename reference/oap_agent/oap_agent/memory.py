"""LLM-based user fact extraction via discovery's Ollama pass-through."""

from __future__ import annotations

import json
import logging
import re

import httpx

from .db import AgentDB

log = logging.getLogger("oap.agent.memory")

EXTRACTION_SYSTEM = (
    "You extract short factual statements about the user from a conversation. "
    "Return a JSON object with a single key \"facts\" containing an array of strings. "
    "Each fact should be 3-10 words, third person (e.g. \"lives in Portland\", "
    "\"prefers Python over JavaScript\", \"works on robotics\"). "
    "Only extract facts that reveal the user's identity, preferences, expertise, "
    "location, or interests. Do NOT extract facts about the assistant, the tool "
    "results, or generic knowledge. If there is nothing to extract, return "
    "{\"facts\": []}."
)


async def embed_texts(
    discovery_url: str,
    texts: list[str],
    prefix: str = "search_document: ",
    timeout: int = 30,
) -> list[list[float]] | None:
    """Batch embed texts via discovery's Ollama pass-through.

    Uses nomic-embed-text with task-type prefixes per its documentation.
    Returns list of embedding vectors, or None on failure.
    """
    if not texts:
        return []
    prefixed = [f"{prefix}{t}" for t in texts]
    url = f"{discovery_url.rstrip('/')}/api/embed"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json={
                "model": "nomic-embed-text",
                "input": prefixed,
            })
            resp.raise_for_status()
            data = resp.json()
        return data.get("embeddings")
    except Exception:
        log.warning("Embedding request failed", exc_info=True)
        return None


async def embed_query(
    discovery_url: str,
    text: str,
    timeout: int = 30,
) -> list[float] | None:
    """Embed a single query text with the search_query prefix.

    Returns the embedding vector, or None on failure.
    """
    result = await embed_texts(discovery_url, [text], prefix="search_query: ", timeout=timeout)
    if result and len(result) > 0:
        return result[0]
    return None


async def embed_missing_facts(db: "AgentDB", discovery_url: str) -> int:
    """Embed all facts that lack embeddings. Returns count embedded."""
    missing = db.get_facts_without_embeddings()
    if not missing:
        return 0

    total = 0
    # Batch in groups of 50
    for i in range(0, len(missing), 50):
        batch = missing[i : i + 50]
        texts = [f["fact"] for f in batch]
        embeddings = await embed_texts(discovery_url, texts)
        if not embeddings or len(embeddings) != len(batch):
            log.warning("Embedding batch failed (got %s for %d texts)", len(embeddings) if embeddings else "None", len(batch))
            continue
        pairs = [(batch[j]["id"], embeddings[j]) for j in range(len(batch))]
        total += db.set_embeddings_batch(pairs)

    if total:
        log.info("Embedded %d user fact(s)", total)
    return total


async def extract_facts_from_text(
    discovery_url: str,
    text: str,
    existing_facts: list[dict],
    *,
    model: str = "qwen3:8b",
    timeout: int = 30,
) -> list[str]:
    """Extract user facts from freeform text. Returns list of fact strings."""
    existing_block = ""
    if existing_facts:
        existing_block = (
            "\n\nAlready known about the user (do NOT repeat these):\n"
            + "\n".join(f"- {f['fact']}" for f in existing_facts)
        )

    prompt = (
        f"The user describes themselves:\n{text[:2000]}"
        f"{existing_block}\n\n"
        "Extract facts about the user."
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "system": EXTRACTION_SYSTEM,
        "stream": False,
        "format": "json",
        "options": {"num_predict": 200},
    }

    url = f"{discovery_url.rstrip('/')}/api/generate"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("response", "")
    # Strip qwen3 thinking tags if present
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    parsed = json.loads(raw)
    facts = parsed.get("facts", [])
    if not isinstance(facts, list):
        return []
    return [str(f) for f in facts if f and isinstance(f, str) and len(str(f)) < 200]


async def extract_and_store_facts(
    db: AgentDB,
    discovery_url: str,
    user_message: str,
    assistant_response: str,
    *,
    model: str = "qwen3:8b",
    timeout: int = 30,
    max_facts: int = 500,
) -> None:
    """Extract user facts from a conversation turn and store them.

    Calls discovery's /api/generate (Ollama pass-through) for LLM extraction.
    After storing, embeds any facts that lack embeddings.
    Fire-and-forget — errors are logged, never raised.
    """
    try:
        existing = db.get_all_facts()
        existing_block = ""
        if existing:
            existing_block = (
                "\n\nAlready known about the user (do NOT repeat these):\n"
                + "\n".join(f"- {f['fact']}" for f in existing)
            )

        prompt = (
            f"User message: {user_message[:1000]}\n"
            f"Assistant response: {assistant_response[:1000]}"
            f"{existing_block}\n\n"
            "Extract new facts about the user."
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "system": EXTRACTION_SYSTEM,
            "stream": False,
            "format": "json",
            "options": {"num_predict": 400},
        }

        url = f"{discovery_url.rstrip('/')}/api/generate"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data.get("response", "")
        # Strip qwen3 thinking tags if present
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # LLM output was truncated by num_predict — try to salvage
            # by closing any open strings/arrays/objects
            for suffix in ['"}', '"]', '"]}', '"}]', '"}]}']:
                try:
                    parsed = json.loads(text + suffix)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return
        facts = parsed.get("facts", [])
        if not isinstance(facts, list):
            return

        clean = [str(f) for f in facts if f and isinstance(f, str) and len(str(f)) < 200]
        if clean:
            added = db.add_facts(clean, user_message, max_facts)
            if added:
                log.info("Extracted %d new user fact(s): %s", added, clean)
                await embed_missing_facts(db, discovery_url)
    except Exception:
        log.warning("User fact extraction failed", exc_info=True)
