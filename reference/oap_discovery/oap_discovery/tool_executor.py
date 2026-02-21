"""Execute tool calls by mapping Ollama tool arguments to manifest invocations."""

from __future__ import annotations

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

    summaries: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = f"User task: {task}\n\nData:\n{chunk}"
        try:
            raw, metrics = await ollama.generate(prompt, system=_SUMMARIZE_SYSTEM)
            # Strip <think> blocks from qwen3 responses
            summary = _THINK_RE.sub("", raw).strip()
            summaries.append(summary)
            log.debug(
                "Chunk %d/%d: %d chars -> %d chars (%.0fms)",
                i + 1, len(chunks), len(chunk), len(summary), metrics.total_ms,
            )
        except Exception:
            log.warning("Summarize chunk %d failed, falling back to truncation", i + 1, exc_info=True)
            return result[:max_output] + "\n...(truncated)"

    combined = "\n\n".join(summaries)

    # Reduce pass if combined summaries still exceed max_output
    if len(combined) > max_output:
        log.info("Reduce pass: %d chars -> target %d", len(combined), max_output)
        prompt = f"User task: {task}\n\nData:\n{combined}"
        try:
            raw, _ = await ollama.generate(prompt, system=_SUMMARIZE_SYSTEM)
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
            # Split args string into positional parameters
            args_str = arguments.get("args", "")
            params = {}
            if args_str:
                for i, part in enumerate(args_str.split()):
                    params[f"arg{i}"] = part
            result = await invoke_manifest(
                invoke_spec,
                params=params,
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
