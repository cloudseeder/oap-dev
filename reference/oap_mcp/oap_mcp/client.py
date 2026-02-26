"""Async HTTP client for the OAP discovery service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("oap.mcp.client")


class OAPClient:
    """Thin async wrapper around the OAP discovery API.

    Auth token is sent only on protected routes (/v1/discover, /v1/manifests, /health).
    Tool execution routes (/v1/tools/call/*) are unprotected (local-only).
    """

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 120):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"X-Backend-Token": self._token}
        return {}

    async def health(self) -> dict[str, Any]:
        """GET /health — check service status."""
        client = await self._get_client()
        resp = await client.get("/health", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def discover(self, task: str, top_k: int = 5) -> dict[str, Any]:
        """POST /v1/discover — natural language task-to-manifest matching."""
        client = await self._get_client()
        resp = await client.post(
            "/v1/discover",
            json={"task": task, "top_k": top_k},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def list_manifests(self) -> list[dict[str, Any]]:
        """GET /v1/manifests — list all indexed manifests."""
        client = await self._get_client()
        resp = await client.get("/v1/manifests", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/tools/call/{tool_name} — execute a tool. No auth (local-only)."""
        client = await self._get_client()
        resp = await client.post(
            f"/v1/tools/call/{tool_name}",
            json=arguments,
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
