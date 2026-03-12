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
    max_facts: int = 50,
) -> None:
    """Extract user facts from a conversation turn and store them.

    Calls discovery's /api/generate (Ollama pass-through) for LLM extraction.
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
    except Exception:
        log.warning("User fact extraction failed", exc_info=True)
