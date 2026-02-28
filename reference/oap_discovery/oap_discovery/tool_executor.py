"""Execute tool calls by mapping Ollama tool arguments to manifest invocations."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from typing import Any

from .invoker import _validate_stdio_command, invoke_manifest
from .sandbox import wrap_argv
from .models import InvokeSpec
from .ollama_client import OllamaClient
from .tool_models import ToolRegistryEntry

log = logging.getLogger("oap.tool_executor")

_SUMMARIZE_SYSTEM = (
    "Condense this data while preserving its meaning and structure. "
    "For structured data (JSON, tables): keep item names and key values, drop boilerplate. "
    "For prose or markdown: keep all headings, key facts, names, and numbers. "
    "Preserve the document's logical structure. "
    "Maximum 15 lines. No preamble, no commentary."
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
                prompt, system=_SUMMARIZE_SYSTEM, timeout=120.0, think=False,
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
                prompt, system=_SUMMARIZE_SYSTEM, timeout=120.0, think=False,
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
) -> tuple[InvokeSpec, dict[str, str]]:
    """Inject credentials into invoke_spec and/or return extra query params.

    Returns (invoke_spec, extra_query_params). For auth_in="query", the
    credential is returned as extra_query_params to be merged into the
    request params dict. For header-based auth, headers are added to
    invoke_spec and extra_query_params is empty.
    """
    from urllib.parse import urlparse

    cred = credentials.get(domain)
    if cred is None:
        # Fall back to the invoke URL hostname (e.g. "www.alphavantage.co")
        # so credentials.yaml can use real domain names for local/* manifests.
        url_host = urlparse(invoke_spec.url).hostname
        log.debug("Credential lookup: domain=%s miss, trying hostname=%s",
                  domain, url_host)
        if url_host:
            cred = credentials.get(url_host)
    if cred is None:
        log.debug("No credentials found for domain=%s", domain)
        return invoke_spec, {}

    key = cred.get("key")
    if not key:
        return invoke_spec, {}

    auth_type = (invoke_spec.auth or "").lower()
    auth_in = (invoke_spec.auth_in or "header").lower()
    log.debug("Injecting credentials for %s: auth=%s, auth_in=%s", domain, auth_type, auth_in)

    if auth_type == "api_key":
        param_name = invoke_spec.auth_name or "apikey"
        if auth_in == "query":
            # Return as extra query params — caller merges into request params
            return invoke_spec, {param_name: key}
        else:
            header_name = invoke_spec.auth_name or "X-API-Key"
            extra_headers = {header_name: key}
    elif auth_type == "bearer":
        extra_headers = {"Authorization": f"Bearer {key}"}
    else:
        return invoke_spec, {}

    merged_headers = dict(invoke_spec.headers or {})
    merged_headers.update(extra_headers)

    return invoke_spec.model_copy(update={"headers": merged_headers}), {}


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
    summarize_threshold: int = 16000,
    chunk_size: int = 6000,
    max_output: int = 16000,
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
    extra_query_params: dict[str, str] = {}
    if credentials:
        invoke_spec, extra_query_params = _inject_credentials(invoke_spec, entry.domain, credentials)

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
            # Normalize: LLMs may pass args as a list or a string.
            # When stdin is provided, args is typically a single logical
            # argument (e.g. a grep pattern like "connection refused") —
            # naive .split() would break it into multiple argv entries.
            # Use shlex.split() to respect shell quoting conventions,
            # and when stdin is present, treat an unquoted string as one arg.
            if isinstance(args_val, list):
                parts = [str(p) for p in args_val]
            elif isinstance(args_val, str) and args_val:
                if stdin_str:
                    # With stdin, split off leading flags but preserve the
                    # rest as-is to maintain quoting (e.g. jq's
                    # '.status == "active"' must keep inner quotes).
                    stripped = args_val.strip()
                    parts = []
                    rest = stripped
                    while rest and rest[0] == '-':
                        end = rest.find(' ')
                        if end == -1:
                            parts.append(rest)
                            rest = ""
                        else:
                            parts.append(rest[:end])
                            rest = rest[end:].lstrip()
                    if rest:
                        parts.append(rest)
                else:
                    parts = shlex.split(args_val)
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
            # JSON input: pass arguments directly (merge any credential query params)
            merged_params = {**arguments, **extra_query_params} if extra_query_params else arguments
            result = await invoke_manifest(
                invoke_spec,
                params=merged_params,
                http_timeout=http_timeout,
            )
        else:
            # Text input: use 'input' argument as stdin/body
            input_text = arguments.get("input", str(arguments))
            if method == "GET" and invoke_spec.url.endswith("/"):
                # REST path pattern: append input to URL path
                invoke_spec = invoke_spec.model_copy(update={"url": invoke_spec.url + input_text})
                text_params = extra_query_params if extra_query_params else None
            else:
                text_params = {"input": input_text, **extra_query_params} if extra_query_params else {"input": input_text}
            result = await invoke_manifest(
                invoke_spec,
                params=text_params,
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


# Max response bytes — same as invoker.MAX_RESPONSE_BYTES
_MAX_EXEC_OUTPUT = 100 * 1024


def _split_pipeline(parts: list[str]) -> list[list[str]]:
    """Split shlex-tokenized command into pipeline stages at '|' tokens.

    Returns a list of stages, each a list of tokens.  Single-command
    invocations return a one-element list (no behavior change).
    """
    stages: list[list[str]] = [[]]
    for token in parts:
        if token == "|":
            if stages[-1]:  # skip empty stages from leading/double pipes
                stages.append([])
        else:
            stages[-1].append(token)
    # Drop any trailing empty stage
    return [s for s in stages if s]


def _raw_pipe_split(cmd: str) -> list[str]:
    """Split a raw command string at unquoted '|' characters.

    Used as a fallback when shlex.split() fails on the full command due to
    quoting that only makes sense per-stage (e.g. ``cut -d" -f2``).
    Respects single and double quotes to avoid splitting inside them.
    """
    stages: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    for ch in cmd:
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
        elif ch == "|" and not in_single and not in_double:
            stages.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        stages.append("".join(current))
    return [s.strip() for s in stages if s.strip()]


def _tokenize_stage(stage_str: str) -> list[str]:
    """Tokenize a single pipeline stage, with shlex fallback.

    Tries shlex.split() first for proper quote handling.  Falls back to
    simple whitespace splitting when shlex can't parse the quoting
    (e.g. ``cut -d" -f2`` where " is a literal delimiter character).
    """
    try:
        return shlex.split(stage_str)
    except ValueError:
        return stage_str.split()


async def _run_single(
    argv: list[str],
    stdin_bytes: bytes | None,
    stdio_timeout: int,
) -> tuple[bytes, bytes, int]:
    """Run a single subprocess, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        *wrap_argv(argv),
        stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=stdin_bytes), timeout=stdio_timeout,
    )
    return stdout, stderr, proc.returncode


async def _run_pipeline(
    pipeline: list[list[str]],
    stdin_bytes: bytes | None,
    stdio_timeout: int,
) -> tuple[bytes, bytes, int]:
    """Execute a multi-stage pipeline, piping stdout→stdin between stages.

    Returns (final_stdout, combined_stderr, last_returncode).
    Uses the same timeout for the entire pipeline.
    """
    current_input = stdin_bytes
    all_stderr: list[bytes] = []

    for i, argv in enumerate(pipeline):
        is_last = i == len(pipeline) - 1
        proc = await asyncio.create_subprocess_exec(
            *wrap_argv(argv),
            stdin=asyncio.subprocess.PIPE if current_input is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=current_input), timeout=stdio_timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise

        if stderr:
            all_stderr.append(stderr)

        # Exit code 1 with no stderr = "no results" convention — but only
        # treat it as fatal for non-last stages (last stage is checked by caller)
        if not is_last and proc.returncode not in (0, 1):
            return stdout, b"".join(all_stderr) + stderr, proc.returncode

        current_input = stdout

    return stdout, b"".join(all_stderr), proc.returncode  # type: ignore[possibly-undefined]


def _resolve_stage(stage: list[str]) -> list[str]:
    """Validate the command and expand ~ in arguments for a pipeline stage."""
    cmd_name = stage[0]
    resolved_cmd = _validate_stdio_command(cmd_name)  # raises ValueError
    return [resolved_cmd] + [os.path.expanduser(a) for a in stage[1:]]


async def execute_exec_call(
    command_str: str,
    *,
    stdin_text: str | None = None,
    stdio_timeout: int = 10,
    max_output: int = 102400,
    ollama: OllamaClient | None = None,
    task: str = "",
    summarize_threshold: int = 16000,
    chunk_size: int = 6000,
    escalation_available: bool = False,
    blocked_commands: list[str] | None = None,
) -> str:
    """Execute a raw CLI command string with the same security as stdio tools.

    Parses the command with shlex, validates the binary against the PATH
    allowlist, expands ~ in arguments, and runs via create_subprocess_exec
    (no shell).  Optional stdin_text is piped to the process.

    Supports shell-style pipelines (cmd1 | cmd2 | cmd3) — each command in
    the pipeline is validated against the allowlist independently.
    """
    if not command_str or not command_str.strip():
        return "Error: empty command"

    try:
        parts = shlex.split(command_str)
        stages = _split_pipeline(parts)
    except ValueError:
        # shlex can't handle the quoting — common with LLM-generated
        # commands mixing quote styles across pipe stages (e.g.
        # grep -oE '"[^"]+"' file | cut -d" -f2).  Fall back to
        # splitting at raw | first, then tokenize each stage.
        stages = [_tokenize_stage(s) for s in _raw_pipe_split(command_str)]

    if not stages:
        return "Error: empty command"

    # Check for blocked commands
    if blocked_commands:
        blocked_set = set(blocked_commands)
        for stage in stages:
            bare_name = os.path.basename(stage[0])
            if bare_name in blocked_set:
                return f"Error: command '{bare_name}' is blocked by configuration"

    # Validate and resolve every command in the pipeline
    try:
        pipeline = [_resolve_stage(s) for s in stages]
    except ValueError as e:
        return f"Error: {e}"

    # Ensure stdin ends with newline (matches _invoke_stdio behavior)
    if stdin_text and not stdin_text.endswith('\n'):
        stdin_text += '\n'
    stdin_bytes = stdin_text.encode() if stdin_text else None

    try:
        if len(pipeline) == 1:
            stdout, stderr_bytes, returncode = await _run_single(
                pipeline[0], stdin_bytes, stdio_timeout,
            )
        else:
            stdout, stderr_bytes, returncode = await _run_pipeline(
                pipeline, stdin_bytes, stdio_timeout,
            )
    except asyncio.TimeoutError:
        return f"Error: command timed out after {stdio_timeout}s"
    except FileNotFoundError as e:
        return f"Error: command not found — {e}"
    except Exception as e:
        log.exception("exec invocation failed: %s", command_str)
        return f"Error: {e}"

    output = stdout.decode(errors="replace")[:_MAX_EXEC_OUTPUT]
    err_output = stderr_bytes.decode(errors="replace")[:_MAX_EXEC_OUTPUT]

    # Exit code 1 with no stderr = "no results" (grep, diff, cmp convention)
    success = returncode == 0 or (
        returncode == 1 and not err_output.strip()
    )

    if not success:
        return f"Error: {err_output.strip() or f'exit code {returncode}'}"

    body = output or "Success (no output)"

    # Large output handling: prefer big LLM escalation over lossy map-reduce
    if len(body) > summarize_threshold:
        if escalation_available:
            # Skip summarization — big LLM will process the raw output.
            # Don't truncate to max_output here; the big LLM has a large
            # context window.  _MAX_EXEC_OUTPUT (100KB) already caps it.
            log.info("Large output (%d chars) — deferring to big LLM escalation", len(body))
        elif ollama is not None and task:
            body = await summarize_result(body, task, ollama, chunk_size, max_output)

    return body
