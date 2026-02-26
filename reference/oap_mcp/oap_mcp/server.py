"""OAP MCP server — exposes manifest discovery to Claude Desktop and MCP clients.

Three tools:
  oap_discover  — natural language → best matching manifests
  oap_call      — execute any discovered tool by name
  oap_exec      — direct CLI execution (fast path)

All logging goes to stderr (stdout is the MCP JSON-RPC stream).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import OAPClient

# Logging to stderr only — stdout is the MCP transport
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("oap.mcp")

mcp = FastMCP("oap")

# Module-level client — initialized in main() before mcp.run()
_client: OAPClient | None = None


def _tool_name_from_manifest(name: str) -> str:
    """Convert a manifest name to an oap_ tool name.

    Same logic as tool_converter.manifest_to_tool_name() — inlined
    to avoid depending on oap_discovery.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"oap_{slug}"


def _format_discover_result(data: dict[str, Any]) -> str:
    """Format a /v1/discover response for Claude to read.

    Shows the best match and candidates with tool names, invoke methods,
    and descriptions so Claude can pick the right tool and construct arguments.
    """
    match = data.get("match")
    candidates = data.get("candidates", [])

    if not match and not candidates:
        return f"No manifests found for task: {data.get('task', '?')}"

    lines: list[str] = []

    if match:
        tool_name = _tool_name_from_manifest(match["name"])
        method = match.get("invoke", {}).get("method", "?").upper()
        lines.append(f"Best match: {tool_name}")
        lines.append(f"  Name: {match['name']}")
        lines.append(f"  Method: {method}")
        lines.append(f"  Description: {match['description']}")
        if match.get("reason"):
            lines.append(f"  Reason: {match['reason']}")
        lines.append("")

    if candidates:
        lines.append(f"Candidates ({len(candidates)}):")
        for c in candidates:
            tool_name = _tool_name_from_manifest(c["name"])
            method = c.get("invoke", {}).get("method", "?").upper()
            score = c.get("score", 0)
            lines.append(f"  - {tool_name} [{method}] (score: {score:.3f})")
            lines.append(f"    {c['description'][:200]}")

    return "\n".join(lines)


@mcp.tool()
async def oap_discover(task: str, top_k: int = 5) -> str:
    """Discover OAP tool manifests matching a natural language task.

    Returns tool names, descriptions, and invoke methods. Use the tool names
    with oap_call() to execute them, or use oap_exec() for direct CLI commands.
    """
    if _client is None:
        return "Error: OAP client not initialized"
    try:
        data = await _client.discover(task, top_k=top_k)
        return _format_discover_result(data)
    except Exception as e:
        log.error("discover failed: %s", e)
        return f"Error: {e}"


@mcp.tool()
async def oap_call(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    """Execute an OAP tool by name. Use oap_discover() first to find available tools.

    Arguments depend on the tool:
      - stdio tools: {"stdin": "input text", "args": "-flags pattern"}
      - HTTP tools: {"field": "value", ...} matching the API schema
    """
    if _client is None:
        return "Error: OAP client not initialized"
    try:
        data = await _client.call_tool(tool_name, arguments or {})
        if data.get("error"):
            return f"Error: {data['error']}"
        return data.get("result", "Success (no output)")
    except Exception as e:
        log.error("call_tool failed: %s", e)
        return f"Error: {e}"


@mcp.tool()
async def oap_exec(command: str, stdin: str | None = None) -> str:
    """Execute a CLI command directly via OAP's exec bridge.

    Fast path when you already know the command. Supports pipes.
    Examples:
      oap_exec("grep -E 'error|warn' /var/log/app.log")
      oap_exec("jq '.users[] | .name'", stdin='{"users":[{"name":"Alice"}]}')
      oap_exec("wc -l", stdin="line1\\nline2\\nline3")
    """
    if _client is None:
        return "Error: OAP client not initialized"
    try:
        args: dict[str, Any] = {"command": command}
        if stdin is not None:
            args["stdin"] = stdin
        data = await _client.call_tool("oap_exec", args)
        if data.get("error"):
            return f"Error: {data['error']}"
        return data.get("result", "Success (no output)")
    except Exception as e:
        log.error("exec failed: %s", e)
        return f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(
        prog="oap-mcp",
        description="OAP MCP server — expose manifest discovery to MCP clients",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("OAP_URL", "http://localhost:8300"),
        help="OAP discovery service URL (default: $OAP_URL or http://localhost:8300)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("OAP_TOKEN"),
        help="Backend auth token (default: $OAP_TOKEN)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("OAP_TIMEOUT", "120")),
        help="HTTP timeout in seconds (default: $OAP_TIMEOUT or 120)",
    )
    args = parser.parse_args()

    global _client
    _client = OAPClient(
        base_url=args.url,
        token=args.token,
        timeout=args.timeout,
    )

    log.info("Starting OAP MCP server (url=%s)", args.url)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
