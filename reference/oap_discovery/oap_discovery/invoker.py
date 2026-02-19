"""Manifest invocation engine — executes HTTP and stdio capabilities."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .experience_models import InvocationResult
from .models import InvokeSpec

log = logging.getLogger("oap.invoker")

# Truncate response bodies stored in experience records
MAX_RESPONSE_BYTES = 10 * 1024  # 10 KB


async def invoke_manifest(
    invoke_spec: InvokeSpec,
    params: dict[str, Any] | None = None,
    *,
    stdin_text: str | None = None,
    http_timeout: int = 30,
    stdio_timeout: int = 10,
) -> InvocationResult:
    """Execute a manifest invocation and capture the result.

    For HTTP manifests (GET/POST): sends params as query string or JSON body.
    For stdio manifests: runs the command with stdin or args.
    """
    method = invoke_spec.method.upper()

    if method == "STDIO":
        return await _invoke_stdio(
            invoke_spec.url, params, stdin_text, timeout=stdio_timeout
        )
    elif method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return await _invoke_http(
            invoke_spec, method, params, timeout=http_timeout
        )
    else:
        return InvocationResult(
            status="failure",
            latency_ms=0,
            error=f"Unsupported invoke method: {method}",
        )


async def _invoke_http(
    invoke_spec: InvokeSpec,
    method: str,
    params: dict[str, Any] | None,
    timeout: int,
) -> InvocationResult:
    """Execute an HTTP invocation."""
    start = time.monotonic()
    try:
        headers = dict(invoke_spec.headers or {})
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(
                    invoke_spec.url, params=params, headers=headers
                )
            else:
                resp = await client.request(
                    method, invoke_spec.url, json=params, headers=headers
                )

        latency = int((time.monotonic() - start) * 1000)
        body = resp.text[:MAX_RESPONSE_BYTES]

        return InvocationResult(
            status="success" if resp.is_success else "failure",
            http_code=resp.status_code,
            response_body=body,
            latency_ms=latency,
            error=None if resp.is_success else f"HTTP {resp.status_code}",
        )

    except httpx.TimeoutException:
        latency = int((time.monotonic() - start) * 1000)
        return InvocationResult(
            status="failure",
            latency_ms=latency,
            error=f"HTTP timeout after {timeout}s",
        )
    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)
        log.exception("HTTP invocation failed")
        return InvocationResult(
            status="failure",
            latency_ms=latency,
            error=str(e),
        )


async def _invoke_stdio(
    command: str,
    params: dict[str, Any] | None,
    stdin_text: str | None,
    timeout: int,
) -> InvocationResult:
    """Execute a stdio invocation via subprocess."""
    start = time.monotonic()

    # Build argv: command + any param values as positional args
    argv = [command]
    if params:
        for v in params.values():
            argv.append(str(v))

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdin_bytes = stdin_text.encode() if stdin_text else None
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes), timeout=timeout
        )

        latency = int((time.monotonic() - start) * 1000)
        output = stdout.decode(errors="replace")[:MAX_RESPONSE_BYTES]
        err_output = stderr.decode(errors="replace")[:MAX_RESPONSE_BYTES]
        success = proc.returncode == 0

        return InvocationResult(
            status="success" if success else "failure",
            http_code=proc.returncode,
            response_body=output,
            latency_ms=latency,
            error=err_output if not success else None,
        )

    except asyncio.TimeoutError:
        latency = int((time.monotonic() - start) * 1000)
        # Kill the timed-out process
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return InvocationResult(
            status="failure",
            latency_ms=latency,
            error=f"stdio timeout after {timeout}s",
        )
    except FileNotFoundError:
        latency = int((time.monotonic() - start) * 1000)
        return InvocationResult(
            status="failure",
            latency_ms=latency,
            error=f"Command not found: {command}",
        )
    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)
        log.exception("stdio invocation failed")
        return InvocationResult(
            status="failure",
            latency_ms=latency,
            error=str(e),
        )
