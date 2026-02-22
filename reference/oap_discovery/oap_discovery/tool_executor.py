"""Execute tool calls by mapping Ollama tool arguments to manifest invocations."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from .invoker import invoke_manifest
from .models import InvokeSpec
from .ollama_client import OllamaClient
from .tool_models import ToolRegistryEntry

log = logging.getLogger("oap.tool_executor")

_SUMMARIZE_SYSTEM = (
    "Summarize this data concisely. "
    "Preserve key facts, names, dates, numbers, and decisions. No preamble."
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _split_chunks(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks on newline boundaries.

    Walks forward chunk_size chars then backtracks to the last newline
    to avoid breaking records mid-line.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        # Backtrack to last newline within the chunk
        nl = text.rfind("\n", start, end)
        if nl > start:
            end = nl + 1  # include the newline
        chunks.append(text[start:end])
        start = end
    return chunks


async def summarize_result(
    result: str,
    task: str,
    ollama: OllamaClient,
    chunk_size: int,
    max_output: int,
) -> str:
    """Map-reduce summarization of a large tool result.

    Map: split into chunks, summarize each via ollama.generate().
    Reduce: concatenate summaries; if still over max_output, do one final pass.
    Falls back to truncation if any Ollama call fails.
    """
    chunks = _split_chunks(result, chunk_size)
    log.info(
        "Summarizing %d chars in %d chunks (task: %.60s...)",
        len(result), len(chunks), task,
    )

    # Process chunks sequentially.  Ollama serializes generation requests
    # internally, so parallel asyncio.gather provides no speed benefit — it
    # only creates timeout problems as later requests queue behind earlier
    # ones.  Sequential processing gives each chunk a clean 120s window.
    summaries: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = f"User task: {task}\n\nData:\n{chunk}"
        try:
            raw, metrics = await ollama.generate(
                prompt, system=_SUMMARIZE_SYSTEM, timeout=120.0,
            )
            summary = _THINK_RE.sub("", raw).strip()
            log.info(
                "Chunk %d/%d: %d chars -> %d chars (%.0fms)",
                i + 1, len(chunks), len(chunk), len(summary), metrics.total_ms,
            )
            summaries.append(summary)
        except Exception:
            log.warning("Summarize chunk %d/%d failed, falling back to truncation", i + 1, len(chunks), exc_info=True)
            return result[:max_output] + "\n...(truncated)"

    combined = "\n\n".join(summaries)

    # Reduce pass if combined summaries still exceed max_output
    if len(combined) > max_output:
        log.info("Reduce pass: %d chars -> target %d", len(combined), max_output)
        prompt = f"User task: {task}\n\nData:\n{combined}"
        try:
            raw, _ = await ollama.generate(
                prompt, system=_SUMMARIZE_SYSTEM, timeout=120.0,
            )
            combined = _THINK_RE.sub("", raw).strip()
        except Exception:
            log.warning("Reduce pass failed, truncating", exc_info=True)
            combined = combined[:max_output] + "\n...(truncated)"

    return combined


def _inject_credentials(
    invoke_spec: InvokeSpec,
    domain: str,
    credentials: dict[str, dict],
) -> InvokeSpec:
    """Return a copy of invoke_spec with auth headers injected from credentials.

    Supports auth types: api_key (uses auth_name header) and bearer.
    """
    cred = credentials.get(domain)
    if cred is None:
        return invoke_spec

    key = cred.get("key")
    if not key:
        return invoke_spec

    auth_type = (invoke_spec.auth or "").lower()
    extra_headers: dict[str, str] = {}

    if auth_type == "api_key":
        header_name = invoke_spec.auth_name or "X-API-Key"
        extra_headers[header_name] = key
    elif auth_type == "bearer":
        extra_headers["Authorization"] = f"Bearer {key}"
    else:
        # Unknown auth type — skip injection
        return invoke_spec

    merged_headers = dict(invoke_spec.headers or {})
    merged_headers.update(extra_headers)

    return invoke_spec.model_copy(update={"headers": merged_headers})


async def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    registry: dict[str, ToolRegistryEntry],
    *,
    task: str = "",
    http_timeout: int = 30,
    stdio_timeout: int = 10,
    credentials: dict[str, dict] | None = None,
    ollama: OllamaClient | None = None,
    summarize_threshold: int = 4000,
    chunk_size: int = 4000,
    max_output: int = 8000,
) -> str:
    """Execute a tool call by looking up its manifest and invoking it.

    Maps Ollama tool call arguments back to the invoker format:
    - stdio: splits 'args' string into positional arguments
    - HTTP JSON: passes arguments dict directly as body
    - HTTP text: wraps 'input' value for the invoker

    Returns the result as a string for the chat conversation.
    """
    entry = registry.get(tool_name)
    if entry is None:
        return f"Error: Unknown tool '{tool_name}'. Available tools: {', '.join(registry.keys())}"

    manifest = entry.manifest
    invoke_spec = InvokeSpec.model_validate(manifest["invoke"])

    # Inject credentials if available for this domain
    if credentials:
        invoke_spec = _inject_credentials(invoke_spec, entry.domain, credentials)

    method = invoke_spec.method.upper()

    try:
        if method == "STDIO":
            # stdin: piped to the process's standard input
            stdin_str = arguments.get("stdin", "") or ""
            # args: command-line flags and arguments
            # Fallback: small LLMs often invent descriptive key names
            # (e.g. "keyword" instead of "args"), so if "args" is missing
            # we grab the first non-stdin string value.
            args_val = arguments.get("args", "")
            if not args_val:
                for key, val in arguments.items():
                    if key != "stdin" and isinstance(val, str) and val:
                        args_val = val
                        break
            # Normalize: LLMs may pass args as a list or a string
            if isinstance(args_val, list):
                parts = [str(p) for p in args_val]
            elif isinstance(args_val, str):
                parts = args_val.split() if args_val else []
            else:
                parts = [str(args_val)] if args_val else []
            params = {f"arg{i}": part for i, part in enumerate(parts)}
            result = await invoke_manifest(
                invoke_spec,
                params=params,
                stdin_text=stdin_str if stdin_str else None,
                stdio_timeout=stdio_timeout,
            )
        elif "json" in (manifest.get("input", {}) or {}).get("format", ""):
            # JSON input: pass arguments directly
            result = await invoke_manifest(
                invoke_spec,
                params=arguments,
                http_timeout=http_timeout,
            )
        else:
            # Text input: use 'input' argument as stdin/body
            input_text = arguments.get("input", str(arguments))
            result = await invoke_manifest(
                invoke_spec,
                params={"input": input_text},
                stdin_text=input_text,
                http_timeout=http_timeout,
            )

        if result.status == "success":
            body = result.response_body or "Success (no output)"
            if len(body) > summarize_threshold and ollama is not None and task:
                body = await summarize_result(body, task, ollama, chunk_size, max_output)
            return body
        else:
            return f"Error: {result.error or 'Unknown error'}"

    except Exception as e:
        log.exception("Tool execution failed: %s", tool_name)
        return f"Error executing {tool_name}: {e}"
