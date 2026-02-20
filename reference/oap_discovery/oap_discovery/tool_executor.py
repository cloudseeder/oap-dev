"""Execute tool calls by mapping Ollama tool arguments to manifest invocations."""

from __future__ import annotations

import logging
from typing import Any

from .invoker import invoke_manifest
from .models import InvokeSpec
from .tool_models import ToolRegistryEntry

log = logging.getLogger("oap.tool_executor")


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
    http_timeout: int = 30,
    stdio_timeout: int = 10,
    credentials: dict[str, dict] | None = None,
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
            return result.response_body or "Success (no output)"
        else:
            return f"Error: {result.error or 'Unknown error'}"

    except Exception as e:
        log.exception("Tool execution failed: %s", tool_name)
        return f"Error executing {tool_name}: {e}"
