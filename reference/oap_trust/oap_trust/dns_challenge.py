"""DNS and HTTP challenge generation and verification for Layer 1."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import dns.resolver
import httpx

from .config import AttestationConfig

log = logging.getLogger("oap.trust.dns")

DNS_PREFIX = "_oap-verify"
HTTP_PATH = "/.well-known/oap-challenge"


def generate_token() -> str:
    """Generate a cryptographically random challenge token."""
    return secrets.token_urlsafe(32)


def challenge_instructions(domain: str, token: str, method: str) -> str:
    """Return human-readable instructions for completing a challenge."""
    if method == "dns":
        return (
            f"Add a DNS TXT record:\n"
            f"  Name:  {DNS_PREFIX}.{domain}\n"
            f"  Value: oap-challenge={token}\n\n"
            f"Then check status at: GET /v1/attest/domain/{domain}/status"
        )
    elif method == "http":
        return (
            f"Serve the following content at:\n"
            f"  https://{domain}{HTTP_PATH}/{token}\n\n"
            f"Response body must be exactly: {token}\n\n"
            f"Then check status at: GET /v1/attest/domain/{domain}/status"
        )
    else:
        raise ValueError(f"Unknown challenge method: {method}")


def challenge_expiry(cfg: AttestationConfig) -> datetime:
    """Calculate when a challenge expires."""
    return datetime.now(timezone.utc) + timedelta(seconds=cfg.challenge_ttl_seconds)


async def verify_dns_challenge(domain: str, token: str) -> bool:
    """Verify a DNS TXT challenge. Returns True if the token is found."""
    record_name = f"{DNS_PREFIX}.{domain}"
    log.info("Checking DNS TXT record: %s", record_name)

    try:
        answers = dns.resolver.resolve(record_name, "TXT")
        for rdata in answers:
            txt_value = rdata.to_text().strip('"')
            if txt_value == f"oap-challenge={token}":
                log.info("DNS challenge verified for %s", domain)
                return True
        log.info("DNS record found but token not matched for %s", domain)
        return False
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        log.info("No DNS TXT record found for %s", record_name)
        return False
    except Exception as e:
        log.warning("DNS resolution error for %s: %s", record_name, e)
        return False


async def verify_http_challenge(
    domain: str,
    token: str,
    cfg: AttestationConfig,
) -> bool:
    """Verify an HTTP challenge. Returns True if the token is found at the expected URL."""
    url = f"https://{domain}{HTTP_PATH}/{token}"
    log.info("Checking HTTP challenge: %s", url)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                timeout=cfg.request_timeout,
                headers={"User-Agent": "OAP-Trust/0.1"},
                follow_redirects=True,
            )
            if resp.status_code == 200 and resp.text.strip() == token:
                log.info("HTTP challenge verified for %s", domain)
                return True
            log.info("HTTP challenge response did not match for %s", domain)
            return False
    except (httpx.RequestError, Exception) as e:
        log.warning("HTTP challenge error for %s: %s", domain, e)
        return False


async def verify_challenge(
    domain: str,
    token: str,
    method: str,
    cfg: AttestationConfig,
) -> bool:
    """Verify a challenge using the specified method."""
    if method == "dns":
        return await verify_dns_challenge(domain, token)
    elif method == "http":
        return await verify_http_challenge(domain, token, cfg)
    else:
        raise ValueError(f"Unknown challenge method: {method}")
