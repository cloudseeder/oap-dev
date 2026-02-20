"""Manifest invocation engine — executes HTTP and stdio capabilities."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import shutil
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .experience_models import InvocationResult
from .models import InvokeSpec

log = logging.getLogger("oap.invoker")

# Truncate response bodies stored in experience records
MAX_RESPONSE_BYTES = 10 * 1024  # 10 KB

# Stdio commands must resolve to one of these directories
ALLOWED_STDIO_PREFIXES = ("/usr/bin/", "/usr/local/bin/", "/bin/", "/opt/homebrew/bin/")


def _validate_http_url(url: str) -> None:
    """Check that an HTTP URL doesn't resolve to a private/loopback IP (SSRF protection)."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL: {url}")
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")
    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"URL resolves to private IP: {ip}")


def _validate_stdio_command(command: str) -> str:
    """Validate and resolve a stdio command to its full path.

    Returns the resolved absolute path. Raises ValueError if the command
    is not found or not in an allowed directory.
    """
    # Reject absolute paths outside the allowlist
    if command.startswith("/"):
        if not any(command.startswith(p) for p in ALLOWED_STDIO_PREFIXES):
            raise ValueError(
                f"stdio command not in allowed directories: {command}"
            )
        return command

    # Resolve bare command names via PATH
    resolved = shutil.which(command)
    if resolved is None:
        raise ValueError(f"Command not found: {command}")
    if not any(resolved.startswith(p) for p in ALLOWED_STDIO_PREFIXES):
        raise ValueError(
            f"Resolved command not in allowed directories: {resolved}"
        )
    return resolved


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

    Both paths include security validation:
    - HTTP: SSRF protection (private IP blocking)
    - stdio: command allowlist (must resolve to known directories)
    """
    method = invoke_spec.method.upper()

    if method == "STDIO":
        try:
            resolved_cmd = _validate_stdio_command(invoke_spec.url)
        except ValueError as e:
            return InvocationResult(
                status="failure", latency_ms=0, error=f"Blocked: {e}"
            )
        return await _invoke_stdio(
            resolved_cmd, params, stdin_text, timeout=stdio_timeout
        )
    elif method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        try:
            _validate_http_url(invoke_spec.url)
        except ValueError as e:
            return InvocationResult(
                status="failure", latency_ms=0, error=f"SSRF blocked: {e}"
            )
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
    """Execute an HTTP invocation.

    Follows redirects manually (up to 5 hops) so that auth headers
    are preserved across cross-host redirects like example.com →
    www.example.com.  httpx's built-in follow_redirects strips
    sensitive headers on host changes, which breaks API key auth.
    """
    max_redirects = 5
    start = time.monotonic()
    try:
        headers = dict(invoke_spec.headers or {})
        url = invoke_spec.url
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(max_redirects + 1):
                if method == "GET":
                    resp = await client.get(url, params=params, headers=headers)
                    # Only send params on the first request
                    params = None
                else:
                    resp = await client.request(
                        method, url, json=params, headers=headers
                    )

                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        break
                    url = str(resp.url.join(location))
                    _validate_http_url(url)
                    log.debug("Following redirect to %s", url)
                    continue
                break

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
