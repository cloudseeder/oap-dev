"""FastAPI router for Ollama tool bridge endpoints."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from .config import ExperienceConfig, OllamaConfig, ToolBridgeConfig, load_credentials
from .discovery import DiscoveryEngine
from .db import ManifestStore
from .experience_engine import ExperienceEngine, _make_experience_id
from .experience_models import (
    CorrectionEntry,
    DiscoveryRecord,
    ExperienceRecord,
    IntentRecord,
    InvocationRecord,
    OutcomeRecord,
)
from .experience_store import ExperienceStore
from .ollama_client import OllamaClient
from .tool_converter import manifest_to_tool
from .tool_executor import execute_tool_call
from .tool_models import (
    ChatMessage,
    ChatRequest,
    Tool,
    ToolRegistryEntry,
    ToolsRequest,
    ToolsResponse,
)

log = logging.getLogger("oap.tool_api")

router = APIRouter(tags=["tool-bridge"])

# Set by api.py during lifespan initialization
_engine: DiscoveryEngine | None = None
_store: ManifestStore | None = None
_ollama_cfg: OllamaConfig | None = None
_tool_bridge_cfg: ToolBridgeConfig | None = None
_ollama: OllamaClient | None = None

# Experience cache — set by api.py when both experience and tool bridge are enabled
_experience_engine: ExperienceEngine | None = None
_experience_store: ExperienceStore | None = None
_experience_cfg: ExperienceConfig | None = None


def _require_enabled() -> tuple[DiscoveryEngine, ManifestStore, OllamaConfig, ToolBridgeConfig]:
    """Raise 503 if the tool bridge is not initialized."""
    if _engine is None or _store is None or _ollama_cfg is None or _tool_bridge_cfg is None:
        raise HTTPException(
            status_code=503,
            detail="Tool bridge is not enabled. Set tool_bridge.enabled: true in config.",
        )
    if not _tool_bridge_cfg.enabled:
        raise HTTPException(
            status_code=503,
            detail="Tool bridge is disabled in configuration.",
        )
    return _engine, _store, _ollama_cfg, _tool_bridge_cfg


MAX_INJECTED_TOOLS = 3


async def _discover_tools(
    engine: DiscoveryEngine,
    store: ManifestStore,
    task: str,
    top_k: int,
) -> tuple[list[Tool], dict[str, ToolRegistryEntry]]:
    """Run discovery and convert the top matches to Ollama tools.

    Injects up to MAX_INJECTED_TOOLS from the LLM's top pick plus
    highest-scoring candidates.  This gives the chat model options
    when vector search ranks the wrong manifest first (e.g. "email"
    pulling spfquery above grep).
    """
    result = await engine.discover(task, top_k=top_k)

    tools: list[Tool] = []
    registry: dict[str, ToolRegistryEntry] = {}
    seen_domains: set[str] = set()

    # Start with the LLM's top pick
    if result.match:
        seen_domains.add(result.match.domain)
        manifest = store.get_manifest(result.match.domain)
        if manifest is not None:
            entry = manifest_to_tool(result.match.domain, manifest)
            tools.append(entry.tool)
            registry[entry.tool.function.name] = entry

    # Fill remaining slots from candidates (by vector score order)
    for candidate in result.candidates:
        if len(tools) >= MAX_INJECTED_TOOLS:
            break
        if candidate.domain in seen_domains:
            continue
        seen_domains.add(candidate.domain)
        manifest = store.get_manifest(candidate.domain)
        if manifest is not None:
            entry = manifest_to_tool(candidate.domain, manifest)
            tools.append(entry.tool)
            registry[entry.tool.function.name] = entry

    return tools, registry


async def _check_experience_cache(
    task: str,
    store: ManifestStore,
    fingerprint: str | None = None,
    intent_domain: str | None = None,
) -> tuple[list[Tool], dict[str, ToolRegistryEntry], str | None, str | None, str | None]:
    """Check experience cache for a matching tool.

    Returns (tools, registry, fingerprint, intent_domain, experience_id).
    On cache miss, tools/registry are empty but fingerprint is still returned
    for caching after successful execution.

    If fingerprint/intent_domain are provided, skips re-fingerprinting.
    """
    if _experience_engine is None or _experience_store is None or _experience_cfg is None:
        return [], {}, None, None, None

    if fingerprint is None:
        fingerprint, intent_domain = await _experience_engine.fingerprint_intent(task)
    if fingerprint is None:
        return [], {}, None, None, None

    matches = _experience_store.find_by_fingerprint(fingerprint)
    threshold = _experience_cfg.confidence_threshold

    for exp in matches:
        if exp.discovery.confidence >= threshold and exp.outcome.status == "success":
            # Cache hit — load manifest and convert to tool
            manifest = store.get_manifest(exp.discovery.manifest_matched)
            if manifest is None:
                continue
            entry = manifest_to_tool(exp.discovery.manifest_matched, manifest)
            log.info(
                "Experience cache hit: %s → %s (confidence=%.2f, used %d times)",
                fingerprint,
                exp.discovery.manifest_matched,
                exp.discovery.confidence,
                exp.use_count,
            )
            _experience_store.touch(exp.id)
            return [entry.tool], {entry.tool.function.name: entry}, fingerprint, intent_domain, exp.id

    # Cache miss — return fingerprint for later caching
    log.info("Experience cache miss for fingerprint=%s", fingerprint)
    return [], {}, fingerprint, intent_domain, None


async def _save_experience(
    fingerprint: str,
    intent_domain: str,
    task: str,
    registry: dict[str, ToolRegistryEntry],
    tools_called: set[str],
) -> None:
    """Save a new experience record after successful tool execution."""
    if _experience_store is None:
        return

    if not registry:
        return

    # Prefer the tool the LLM actually called over arbitrary registry order
    entry: ToolRegistryEntry | None = None
    for name in tools_called:
        if name in registry:
            entry = registry[name]
            break
    if entry is None:
        entry = next(iter(registry.values()))
    first_entry = entry
    manifest_domain = first_entry.domain
    invoke_data = first_entry.manifest.get("invoke", {})

    now = datetime.now(timezone.utc)
    exp_id = _make_experience_id(fingerprint, manifest_domain)

    record = ExperienceRecord(
        id=exp_id,
        timestamp=now,
        use_count=1,
        last_used=now,
        intent=IntentRecord(
            raw=task,
            fingerprint=fingerprint,
            domain=intent_domain,
        ),
        discovery=DiscoveryRecord(
            query_used=task,
            manifest_matched=manifest_domain,
            manifest_version=None,
            confidence=0.9,
        ),
        invocation=InvocationRecord(
            endpoint=invoke_data.get("url", ""),
            method=invoke_data.get("method", ""),
        ),
        outcome=OutcomeRecord(
            status="success",
            response_summary="Cached from tool bridge chat",
        ),
    )
    _experience_store.save(record)
    log.info("Cached experience: %s → %s (fingerprint=%s)", exp_id, manifest_domain, fingerprint)


async def _save_failure_experience(
    fingerprint: str,
    intent_domain: str,
    task: str,
    registry: dict[str, ToolRegistryEntry],
    failed_calls: list[dict[str, Any]],
) -> None:
    """Save a failure experience record so future requests can avoid the same mistakes."""
    if _experience_store is None or not failed_calls:
        return

    # Build correction entries from failed tool calls
    corrections = []
    for fc in failed_calls:
        corrections.append(CorrectionEntry(
            attempted=f"{fc['tool']}({json.dumps(fc['arguments'], default=str)})",
            error=fc["error"],
            fix="",
        ))

    # Use the first failed tool's registry entry for manifest info
    first_tool = failed_calls[0]["tool"]
    entry = registry.get(first_tool)
    manifest_domain = entry.domain if entry else "unknown"
    invoke_data = entry.manifest.get("invoke", {}) if entry else {}

    now = datetime.now(timezone.utc)
    exp_id = f"fail_{_make_experience_id(fingerprint, manifest_domain)}"

    record = ExperienceRecord(
        id=exp_id,
        timestamp=now,
        use_count=1,
        last_used=now,
        intent=IntentRecord(
            raw=task,
            fingerprint=fingerprint,
            domain=intent_domain,
        ),
        discovery=DiscoveryRecord(
            query_used=task,
            manifest_matched=manifest_domain,
            manifest_version=None,
            confidence=0.0,
        ),
        invocation=InvocationRecord(
            endpoint=invoke_data.get("url", ""),
            method=invoke_data.get("method", ""),
        ),
        outcome=OutcomeRecord(
            status="failure",
            response_summary=corrections[0].error[:200] if corrections else "Unknown error",
        ),
        corrections=corrections,
    )
    _experience_store.save(record)
    log.info(
        "Cached failure experience: %s → %s (%d corrections, fingerprint=%s)",
        exp_id, manifest_domain, len(corrections), fingerprint,
    )


def _build_failure_hints(fingerprint: str) -> str:
    """Build a compact failure hint string from past failures with this fingerprint."""
    if _experience_store is None:
        return ""

    failures = _experience_store.find_failures_by_fingerprint(fingerprint, limit=5)
    if not failures:
        return ""

    lines: list[str] = []
    for exp in failures:
        for c in exp.corrections:
            lines.append(f"- {c.attempted} → {c.error}")
    return "\n".join(lines) if lines else ""


@router.post("/v1/tools", response_model=ToolsResponse)
async def discover_tools(req: ToolsRequest) -> ToolsResponse:
    """Discover manifests for a task and return as Ollama tool definitions."""
    engine, store, _, _ = _require_enabled()
    tools, registry = await _discover_tools(engine, store, req.task, req.top_k)
    return ToolsResponse(tools=tools, registry=registry)


@router.post("/v1/chat")
async def chat_proxy(req: ChatRequest) -> dict[str, Any]:
    """Transparent Ollama proxy with OAP tool discovery.

    1. Extract task from the last user message
    2. Discover tools via OAP
    3. Merge with any client-provided tools
    4. Forward to Ollama /api/chat
    5. If tool_calls, execute via invoker and loop
    6. Return final response with metadata
    """
    engine, store, ollama_cfg, bridge_cfg = _require_enabled()

    max_rounds = min(req.oap_max_rounds, bridge_cfg.max_rounds)
    tools: list[Tool] = []
    registry: dict[str, ToolRegistryEntry] = {}
    debug = req.oap_debug
    debug_rounds: list[dict[str, Any]] = []

    # Experience cache tracking
    exp_fingerprint: str | None = None
    exp_intent_domain: str | None = None
    exp_cache_hit = False
    exp_id: str | None = None
    tools_executed = False
    tools_had_errors = False
    tools_called: set[str] = set()
    failed_calls: list[dict[str, Any]] = []
    exp_cache_status: str | None = None  # "hit", "miss", "degraded", or None

    # Extract last user message (used for discovery and summarization)
    last_user_msg = ""
    for msg in reversed(req.messages):
        if msg.role == "user" and msg.content:
            last_user_msg = msg.content
            break

    # Always fingerprint when experience engine is available (needed for failure hints
    # even with --no-cache)
    if _experience_engine and last_user_msg:
        exp_fingerprint, exp_intent_domain = await _experience_engine.fingerprint_intent(last_user_msg)

    # Discover tools from the last user message
    if req.oap_discover and last_user_msg:
        # Try experience cache first (unless oap_no_cache is set)
        if not req.oap_no_cache and exp_fingerprint:
            cached_tools, cached_registry, _, _, exp_id = (
                await _check_experience_cache(last_user_msg, store, exp_fingerprint, exp_intent_domain)
            )
            if cached_tools:
                tools, registry = cached_tools, cached_registry
                exp_cache_hit = True
        if not exp_cache_hit:
            tools, registry = await _discover_tools(
                engine, store, last_user_msg, req.oap_top_k,
            )

    # Merge client-provided tools
    client_tools = list(req.tools) if req.tools else []
    if client_tools:
        tools.extend(client_tools)

    # Build failure hints from past failures with this fingerprint
    failure_hints = ""
    if exp_fingerprint and _experience_store:
        failure_hints = _build_failure_hints(exp_fingerprint)

    # Build Ollama request — prepend a system message to keep qwen3 concise
    original_messages = [m.model_dump(exclude_none=True) for m in req.messages]
    system_content = (
        "You are a tool-calling assistant. Be brief. "
        "Use function calls to invoke tools — never write JSON in your response. "
        "Always include both 'args' and 'stdin' parameters for text-processing tools. "
        "After a tool result, reply in 1-2 sentences."
    )
    if failure_hints:
        system_content += (
            f"\n\nWARNING — previous attempts at this type of task failed:\n"
            f"{failure_hints}\nAvoid these approaches."
        )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        *original_messages,
    ]

    for _attempt in range(2):
        for round_num in range(max_rounds):
            ollama_payload: dict[str, Any] = {
                "model": req.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {"num_ctx": ollama_cfg.num_ctx},
                "keep_alive": ollama_cfg.keep_alive,
            }
            if tools:
                ollama_payload["tools"] = [t.model_dump() for t in tools]

            # Forward to Ollama
            try:
                async with httpx.AsyncClient(timeout=bridge_cfg.ollama_timeout) as client:
                    resp = await client.post(
                        f"{ollama_cfg.base_url.rstrip('/')}/api/chat",
                        json=ollama_payload,
                    )
                    resp.raise_for_status()
                    ollama_resp = resp.json()
            except httpx.HTTPStatusError as e:
                log.error("Ollama HTTP %d: %s", e.response.status_code, e.response.text[:500])
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama returned HTTP {e.response.status_code}",
                )
            except httpx.HTTPError as e:
                log.exception("Ollama request failed")
                raise HTTPException(status_code=502, detail=f"Ollama request failed: {type(e).__name__}: {e}")

            # Check for tool calls
            resp_message = ollama_resp.get("message", {})
            tool_calls = resp_message.get("tool_calls")

            if not tool_calls or not req.oap_auto_execute:
                # If cache hit produced errors and LLM gave up, break to let
                # degradation logic fire instead of returning early.
                if exp_cache_hit and tools_had_errors and _attempt == 0:
                    if debug:
                        debug_rounds.append({
                            "round": round_num + 1,
                            "ollama_response": resp_message,
                            "tool_executions": [],
                        })
                    break

                # No tool calls or auto-execute disabled — return as-is
                ollama_resp["oap_tools_injected"] = len(registry)
                ollama_resp["oap_round"] = round_num + 1
                cache_label = exp_cache_status or ("hit" if exp_cache_hit else "miss" if exp_fingerprint else None)
                if cache_label:
                    ollama_resp["oap_experience_cache"] = cache_label
                if debug:
                    debug_rounds.append({
                        "round": round_num + 1,
                        "ollama_response": resp_message,
                        "tool_executions": [],
                    })
                    ollama_resp["oap_debug"] = {
                        "tools_discovered": list(registry.keys()),
                        "experience_cache": cache_label or "disabled",
                        "experience_fingerprint": exp_fingerprint,
                        "failure_hints": failure_hints or None,
                        "rounds": debug_rounds,
                    }
                # Cache new experience on successful tool execution (only if no errors)
                if tools_executed and not tools_had_errors and not exp_cache_hit and exp_fingerprint and exp_intent_domain:
                    await _save_experience(
                        exp_fingerprint, exp_intent_domain, last_user_msg, registry, tools_called,
                    )
                # Cache failure experience when tools had errors
                if tools_executed and tools_had_errors and exp_fingerprint and exp_intent_domain:
                    await _save_failure_experience(
                        exp_fingerprint, exp_intent_domain, last_user_msg, registry, failed_calls,
                    )
                return ollama_resp

            # Execute tool calls
            tools_executed = True
            log.info("Round %d: executing %d tool call(s)", round_num + 1, len(tool_calls))

            # Append assistant message with tool calls
            messages.append(resp_message)

            debug_executions: list[dict[str, Any]] = []

            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})
                tools_called.add(tool_name)

                t0 = time.monotonic()
                result_str = await execute_tool_call(
                    tool_name,
                    tool_args,
                    registry,
                    task=last_user_msg,
                    http_timeout=bridge_cfg.http_timeout,
                    stdio_timeout=bridge_cfg.stdio_timeout,
                    credentials=load_credentials(bridge_cfg.credentials_file),
                    ollama=_ollama,
                    summarize_threshold=bridge_cfg.summarize_threshold,
                    chunk_size=bridge_cfg.chunk_size,
                    max_output=bridge_cfg.max_tool_result,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                if result_str.startswith("Error"):
                    tools_had_errors = True
                    failed_calls.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "error": result_str,
                    })

                if debug:
                    debug_executions.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": result_str,
                        "duration_ms": duration_ms,
                    })

                # Truncate large tool results to fit model context
                if len(result_str) > bridge_cfg.max_tool_result:
                    result_str = result_str[:bridge_cfg.max_tool_result] + "\n...(truncated)"

                # Append tool result message
                messages.append({
                    "role": "tool",
                    "content": result_str,
                })

            if debug:
                debug_rounds.append({
                    "round": round_num + 1,
                    "ollama_response": resp_message,
                    "tool_executions": debug_executions,
                })

        # Inner loop finished (max rounds reached or broke out).
        # If this was a cache hit and tools had errors, degrade and retry.
        if exp_cache_hit and tools_had_errors and _attempt == 0 and _experience_store and exp_id:
            new_conf = _experience_store.degrade_confidence(exp_id)
            log.warning(
                "Cache hit produced errors — degraded %s confidence to %.2f, retrying with full discovery",
                exp_id,
                new_conf or 0.0,
            )
            # Reset state for retry with full discovery
            exp_cache_hit = False
            exp_cache_status = "degraded"
            tools_had_errors = False
            tools_executed = False
            tools_called = set()
            failed_calls = []
            debug_rounds = []
            messages = [messages[0], *original_messages]  # preserve system prompt
            tools, registry = await _discover_tools(
                engine, store, last_user_msg, req.oap_top_k,
            )
            if client_tools:
                tools.extend(client_tools)
            continue  # retry the outer loop

        # No retry needed — break out
        break

    # Max rounds exceeded — return last response
    ollama_resp["oap_tools_injected"] = len(registry)
    ollama_resp["oap_round"] = max_rounds
    cache_label = exp_cache_status or ("hit" if exp_cache_hit else "miss" if exp_fingerprint else None)
    if cache_label:
        ollama_resp["oap_experience_cache"] = cache_label
    if debug:
        ollama_resp["oap_debug"] = {
            "tools_discovered": list(registry.keys()),
            "experience_cache": cache_label or "disabled",
            "experience_fingerprint": exp_fingerprint,
            "failure_hints": failure_hints or None,
            "rounds": debug_rounds,
        }
    # Cache new experience on successful tool execution (only if no errors)
    if tools_executed and not tools_had_errors and not exp_cache_hit and exp_fingerprint and exp_intent_domain:
        await _save_experience(
            exp_fingerprint, exp_intent_domain, last_user_msg, registry, tools_called,
        )
    # Cache failure experience when tools had errors
    if tools_executed and tools_had_errors and exp_fingerprint and exp_intent_domain:
        await _save_failure_experience(
            exp_fingerprint, exp_intent_domain, last_user_msg, registry, failed_calls,
        )
    return ollama_resp
