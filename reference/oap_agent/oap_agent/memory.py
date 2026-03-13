"""LLM-based user fact extraction via discovery's Ollama pass-through."""

from __future__ import annotations

import json
import logging
import re

import httpx

from .db import AgentDB

log = logging.getLogger("oap.agent.memory")

EXTRACTION_SYSTEM = (
    "You extract short factual statements about the user and their world from a conversation. "
    "Return a JSON object with a single key \"facts\" containing an array of strings. "
    "Each fact should be 3-15 words. Always preserve full names (first and last) "
    "and include the subject's relationship when the fact is about someone other than the user. "
    "Examples: \"lives in Portland\", \"wife Amy works as video editor at KGW\", "
    "\"son Kai born in 1996\", \"grandparents Hellen and Jack Schwieger lived in Cherry Creek NY\". "
    "Only extract DURABLE facts: identity, relationships, family, preferences, expertise, "
    "location, health, birthdays, or interests. "
    "Do NOT extract: "
    "(1) facts about the assistant or tool results, "
    "(2) ephemeral actions (\"ran a script\", \"asked a question\"), "
    "(3) meta-observations about the conversation itself "
    "(\"wants to share info\", \"is being friendly\"), "
    "(4) generic knowledge. "
    "If a new fact is essentially the same as an existing one, do NOT include it. "
    "If there is nothing to extract, return {\"facts\": []}."
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
        "think": False,
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


async def _semantic_dedup(
    db: AgentDB,
    discovery_url: str,
    candidates: list[str],
    threshold: float = 0.85,
) -> tuple[list[str], list[list[float]] | None, list[dict] | None, list[list[float]] | None]:
    """Filter out candidate facts that are semantically similar to existing facts.

    Embeds candidates and compares against existing fact embeddings using
    cosine similarity. Returns only candidates below the similarity threshold.
    Falls back to returning all candidates if embedding fails.

    Also returns intermediate data for reuse by supersession check:
    (kept_candidates, candidate_vecs, existing_rows, existing_vecs)
    """
    from .db import _unpack_embedding, _cosine_similarity

    # Get existing active facts that have embeddings
    rows = db.conn.execute(
        "SELECT id, fact, embedding, pinned FROM user_facts "
        "WHERE embedding IS NOT NULL AND superseded_by IS NULL"
    ).fetchall()
    if not rows:
        return candidates, None, None, None

    existing_rows = [dict(r) for r in rows]
    existing_vecs = [_unpack_embedding(r["embedding"]) for r in rows]
    existing_texts = [r["fact"] for r in rows]

    # Embed candidates
    candidate_vecs = await embed_texts(discovery_url, candidates)
    if not candidate_vecs or len(candidate_vecs) != len(candidates):
        return candidates, None, existing_rows, existing_vecs

    kept: list[str] = []
    kept_vecs: list[list[float]] = []
    for i, (cand, cvec) in enumerate(zip(candidates, candidate_vecs)):
        max_sim = 0.0
        best_match = ""
        for j, evec in enumerate(existing_vecs):
            sim = _cosine_similarity(cvec, evec)
            if sim > max_sim:
                max_sim = sim
                best_match = existing_texts[j]
        if max_sim >= threshold:
            log.info("Semantic dedup: '%.60s' ≈ '%.60s' (sim=%.3f), skipping", cand, best_match, max_sim)
        else:
            kept.append(cand)
            kept_vecs.append(cvec)

    if len(kept) < len(candidates):
        log.info("Semantic dedup: %d/%d candidates kept", len(kept), len(candidates))
    return kept, kept_vecs, existing_rows, existing_vecs


SUPERSESSION_SYSTEM = (
    "You determine if a new fact REPLACES an existing fact about the same "
    "specific subject AND topic but with updated details. "
    "A replacement means the old fact is no longer true because the new fact "
    "corrects or updates it (e.g. moved to a new city, changed jobs). "
    "NOT a replacement: facts about different subjects, different topics, "
    "or complementary facts that can both be true at once. "
    'Return JSON: {"replacements": [{"new": 0, "old": 2}]} '
    "where numbers are the indices shown. "
    'If no replacements, return {"replacements": []}.'
)


async def _check_supersession(
    db: AgentDB,
    discovery_url: str,
    candidates: list[str],
    candidate_vecs: list[list[float]] | None,
    existing_rows: list[dict] | None,
    existing_vecs: list[list[float]] | None,
    *,
    sim_low: float = 0.50,
    sim_high: float = 0.84,
    model: str = "qwen3:8b",
    timeout: int = 30,
) -> list[tuple[str, str]]:
    """Detect if candidate facts supersede existing facts.

    Uses embedding similarity to find "related but different" existing facts
    (sim_low to sim_high), then asks the LLM to confirm replacements.

    Returns list of (existing_fact_id, candidate_text) pairs to supersede
    after the new facts are inserted.
    """
    from .db import _unpack_embedding, _cosine_similarity

    if not candidates or existing_rows is None or existing_vecs is None:
        return []

    # If candidate embeddings weren't provided, embed them now
    if candidate_vecs is None:
        candidate_vecs = await embed_texts(discovery_url, candidates)
        if not candidate_vecs or len(candidate_vecs) != len(candidates):
            return []

    # For each candidate, find existing facts in the "related but different" band
    # Skip pinned facts — they are immune to supersession
    matches: dict[int, list[tuple[int, str, str]]] = {}  # cand_idx → [(existing_idx, id, fact)]
    for ci, cvec in enumerate(candidate_vecs):
        for ei, evec in enumerate(existing_vecs):
            if existing_rows[ei].get("pinned"):
                continue
            sim = _cosine_similarity(cvec, evec)
            if sim_low <= sim < sim_high:
                matches.setdefault(ci, []).append((ei, existing_rows[ei]["id"], existing_rows[ei]["fact"]))

    if not matches:
        return []

    # Build LLM prompt with indexed candidates and their matches
    new_lines = []
    old_lines = []
    old_idx_map: dict[int, tuple[str, str]] = {}  # prompt_idx → (fact_id, fact_text)
    old_counter = 0

    for ci in sorted(matches.keys()):
        new_lines.append(f"[{ci}] {candidates[ci]}")
        for _, fid, ftxt in matches[ci]:
            old_lines.append(f"[{old_counter}] {ftxt}")
            old_idx_map[old_counter] = (fid, ftxt)
            old_counter += 1

    prompt = (
        "New facts:\n" + "\n".join(new_lines) +
        "\n\nExisting facts:\n" + "\n".join(old_lines) +
        "\n\nWhich new facts REPLACE (not complement) existing facts?"
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "system": SUPERSESSION_SYSTEM,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"num_predict": 200},
    }

    try:
        url = f"{discovery_url.rstrip('/')}/api/generate"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        text = data.get("response", "")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        parsed = json.loads(text)
        replacements_raw = parsed.get("replacements", [])
        if not isinstance(replacements_raw, list):
            return []

        supersessions: list[tuple[str, str]] = []
        for r in replacements_raw:
            if not isinstance(r, dict):
                continue
            new_idx = r.get("new")
            old_idx = r.get("old")
            if not isinstance(new_idx, int) or not isinstance(old_idx, int):
                continue
            if new_idx < 0 or new_idx >= len(candidates):
                continue
            if old_idx not in old_idx_map:
                continue
            old_id, old_text = old_idx_map[old_idx]
            log.info(
                "Supersession: '%s' replaces '%s' (id=%s)",
                candidates[new_idx], old_text, old_id,
            )
            supersessions.append((old_id, candidates[new_idx]))

        return supersessions

    except Exception:
        log.warning("Supersession check failed", exc_info=True)
        return []


async def extract_and_store_facts(
    db: AgentDB,
    discovery_url: str,
    user_message: str,
    assistant_response: str,
    *,
    model: str = "qwen3:8b",
    timeout: int = 120,
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
            "think": False,
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
        log.info("Extraction raw output: %s", text[:500])
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
                log.warning("Extraction output not valid JSON, discarding")
                return
        facts = parsed.get("facts", [])
        if not isinstance(facts, list):
            log.warning("Extraction returned non-list facts: %s", type(facts))
            return

        clean = [str(f) for f in facts if f and isinstance(f, str) and len(str(f)) < 200]
        log.info("Extraction candidates: %s", clean)
        if clean:
            # Semantic dedup: filter out candidates that are too similar to existing facts
            clean, clean_vecs, existing_rows, existing_vecs = await _semantic_dedup(
                db, discovery_url, clean
            )
            if not clean:
                return

            # Supersession: check if any new fact replaces an existing one
            supersessions = await _check_supersession(
                db, discovery_url, clean, clean_vecs, existing_rows, existing_vecs,
                model=model, timeout=timeout,
            )

            added = db.add_facts(clean, user_message, max_facts)
            if added:
                log.info("Extracted %d new user fact(s): %s", added, clean)

                # Execute supersessions now that new facts have IDs
                for old_id, new_text in supersessions:
                    row = db.conn.execute(
                        "SELECT id FROM user_facts WHERE fact = ? AND superseded_by IS NULL",
                        (new_text,),
                    ).fetchone()
                    if row:
                        if db.supersede_fact(old_id, row["id"]):
                            log.info("Superseded fact %s with %s (%s)", old_id, row["id"], new_text)

                await embed_missing_facts(db, discovery_url)
    except Exception:
        log.warning("User fact extraction failed", exc_info=True)
