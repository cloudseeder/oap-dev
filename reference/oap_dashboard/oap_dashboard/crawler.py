"""Crawler for OAP manifest adoption tracking.

Reads domains from seeds.txt, fetches /.well-known/oap.json,
validates, and stores results in SQLite.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from .db import DashboardDB

log = logging.getLogger("oap.dashboard.crawler")


def validate_url(url: str) -> None:
    """Check that URL doesn't resolve to a private IP (SSRF protection)."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL: {url}")
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")
    for family, type_, proto, canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"URL resolves to private IP: {ip}")


DEFAULT_CONFIG = {
    "database": {"path": "dashboard.db"},
    "crawler": {
        "seeds_file": "seeds.txt",
        "timeout_seconds": 10,
        "concurrency": 10,
        "interval_seconds": 21600,  # 6 hours
    },
}


async def crawl_domain(client: httpx.AsyncClient, domain: str, db: DashboardDB) -> bool:
    """Crawl a single domain. Returns True if manifest was found and stored."""
    url = f"https://{domain}/.well-known/oap.json"

    # SSRF protection: validate URL doesn't resolve to private IP
    try:
        validate_url(url)
    except ValueError as e:
        log.warning("%s — blocked: %s", domain, e)
        return False

    start = time.monotonic()
    try:
        resp = await client.get(url, follow_redirects=False)  # Disable redirects for SSRF protection
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code != 200:
            db.add_snapshot(domain, "error", response_time_ms=elapsed_ms)
            log.warning("%s — HTTP %d", domain, resp.status_code)
            return False

        data = resp.json()
        manifest_hash = "sha256:" + hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()

        # Basic v1.0 validation
        required = ("oap", "name", "description", "invoke")
        if not all(k in data for k in required):
            db.add_snapshot(domain, "error", manifest_hash=manifest_hash, response_time_ms=elapsed_ms)
            log.warning("%s — missing required fields", domain)
            return False

        invoke = data.get("invoke", {})
        health_ok = None
        health_url = data.get("health")
        if health_url:
            try:
                # SSRF protection for health check URLs
                validate_url(health_url)
                h = await client.get(health_url, follow_redirects=False)
                health_ok = h.status_code == 200
            except Exception:
                health_ok = False

        is_new = db.upsert_manifest(
            domain=domain,
            name=data["name"],
            description=data["description"],
            manifest_url=url,
            manifest_hash=manifest_hash,
            oap_version=data.get("oap", "unknown"),
            invoke_url=invoke.get("url"),
            invoke_method=invoke.get("method"),
            tags=data.get("tags"),
            publisher_name=(data.get("publisher") or {}).get("name"),
            health_ok=health_ok,
        )

        db.add_snapshot(domain, "ok", manifest_hash=manifest_hash, response_time_ms=elapsed_ms)
        log.info("%s — %s (hash=%s, %dms)", domain, "new" if is_new else "updated", manifest_hash[:20], elapsed_ms)
        return True

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        db.add_snapshot(domain, "error", response_time_ms=elapsed_ms)
        log.warning("%s — %s", domain, e)
        return False


async def crawl_once(db: DashboardDB, cfg: dict) -> int:
    """Crawl all domains from seeds file. Returns count of successfully indexed manifests."""
    seeds_file = Path(cfg["crawler"]["seeds_file"])
    if not seeds_file.exists():
        log.error("Seeds file not found: %s", seeds_file)
        return 0

    domains = [
        line.strip()
        for line in seeds_file.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    log.info("Crawling %d domains", len(domains))

    sem = asyncio.Semaphore(cfg["crawler"]["concurrency"])
    timeout = httpx.Timeout(cfg["crawler"]["timeout_seconds"])

    async with httpx.AsyncClient(timeout=timeout, http2=True) as client:

        async def bounded(domain: str) -> bool:
            async with sem:
                return await crawl_domain(client, domain, db)

        results = await asyncio.gather(*(bounded(d) for d in domains), return_exceptions=True)

    count = sum(1 for r in results if r is True)
    db.update_daily_stats()
    log.info("Crawl complete — %d/%d manifests indexed", count, len(domains))
    return count


def load_config(config_path: str = "config.yaml") -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = Path(config_path)
    if p.exists():
        with open(p) as f:
            file_cfg = yaml.safe_load(f) or {}
        for section in ("database", "crawler"):
            if section in file_cfg:
                cfg[section] = {**cfg[section], **file_cfg[section]}
    return cfg


def main():
    """Entry point for oap-dashboard-crawl command."""
    import argparse

    parser = argparse.ArgumentParser(description="OAP Dashboard Crawler")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true", help="Crawl once and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = load_config(args.config)
    db = DashboardDB(cfg["database"]["path"])

    if args.once:
        asyncio.run(crawl_once(db, cfg))
    else:
        async def run_loop():
            while True:
                await crawl_once(db, cfg)
                interval = cfg["crawler"]["interval_seconds"]
                log.info("Sleeping %d seconds until next crawl", interval)
                await asyncio.sleep(interval)

        asyncio.run(run_loop())

    db.close()


if __name__ == "__main__":
    main()
