"""Manifest fetching and Layer 0 verification."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse

import httpx

from .config import AttestationConfig
from .models import Layer0Result

log = logging.getLogger("oap.trust.manifest")

REQUIRED_FIELDS = {"oap", "name", "description", "invoke"}
KNOWN_VERSIONS = {"1.0"}
USER_AGENT = "OAP-Trust/0.1"
MAX_MANIFEST_SIZE = 1_048_576  # 1MB


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/reserved (SSRF protection)."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        return True  # Can't parse = block it


def _validate_url(url: str, *, allow_http: bool = False) -> str:
    """Validate a URL for safety. Returns the validated URL."""
    parsed = urlparse(url)

    if not allow_http and parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are allowed")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP(S) URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")

    # Block direct private IPs
    hostname = parsed.hostname
    try:
        ipaddress.ip_address(hostname)
        if _is_private_ip(hostname):
            raise ValueError("Private IP addresses are not allowed")
        return url
    except ValueError as e:
        if "Private IP" in str(e):
            raise
        # Not an IP literal — resolve DNS
        pass

    # Resolve hostname and check all addresses
    try:
        addrs = socket.getaddrinfo(hostname, None)
        ips = {addr[4][0] for addr in addrs}
        if not ips:
            raise ValueError(f"Could not resolve hostname: {hostname}")
        for ip in ips:
            if _is_private_ip(ip):
                raise ValueError("Private IP addresses are not allowed")
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    return url


def hash_manifest(manifest_json: dict) -> str:
    """SHA-256 hash of a manifest with sha256: prefix."""
    raw = json.dumps(manifest_json, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"sha256:{digest}"


async def fetch_manifest(
    domain: str,
    cfg: AttestationConfig,
    *,
    allow_http: bool = False,
) -> tuple[dict, str]:
    """Fetch /.well-known/oap.json from a domain. Returns (manifest_dict, url)."""
    scheme = "http" if allow_http else "https"
    url = f"{scheme}://{domain}/.well-known/oap.json"

    _validate_url(url, allow_http=allow_http)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            timeout=cfg.request_timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        resp.raise_for_status()

        if len(resp.content) > MAX_MANIFEST_SIZE:
            raise ValueError("Manifest too large")

        return resp.json(), url


async def check_layer0(
    domain: str,
    cfg: AttestationConfig,
    *,
    allow_http: bool = False,
) -> Layer0Result:
    """Run Layer 0 checks: HTTPS, valid JSON, required fields, version."""
    errors: list[str] = []
    result = Layer0Result(
        domain=domain,
        https=not allow_http,
        valid_json=False,
        has_required_fields=False,
        valid_version=False,
        passed=False,
    )

    # Fetch manifest
    try:
        manifest, url = await fetch_manifest(domain, cfg, allow_http=allow_http)
    except httpx.HTTPStatusError as e:
        errors.append(f"HTTP {e.response.status_code} fetching manifest")
        result.errors = errors
        return result
    except (httpx.RequestError, ValueError) as e:
        errors.append(f"Failed to fetch manifest: {e}")
        result.errors = errors
        return result

    result.valid_json = True

    # Check HTTPS
    if not allow_http and not url.startswith("https://"):
        errors.append("Manifest not served over HTTPS")
        result.https = False

    # Required fields
    missing = REQUIRED_FIELDS - set(manifest.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")
    else:
        result.has_required_fields = True

    # Version
    version = manifest.get("oap")
    if version in KNOWN_VERSIONS:
        result.valid_version = True
    else:
        errors.append(f"Unrecognized OAP version: {version}")

    # Hash
    result.manifest_hash = hash_manifest(manifest)

    # Overall pass
    result.passed = (
        result.https
        and result.valid_json
        and result.has_required_fields
        and result.valid_version
    )
    result.errors = errors
    return result
