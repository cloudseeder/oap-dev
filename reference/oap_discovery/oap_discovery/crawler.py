"""Crawl, validate, embed, and store OAP manifests."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
import httpx

from .config import Config, CrawlerConfig, load_config
from .db import ManifestStore
from .ollama_client import OllamaClient
from .validate import validate_manifest

log = logging.getLogger("oap.crawler")


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


class Crawler:
    """Fetch manifests from domains or local seed files, validate, embed, and store."""

    def __init__(
        self,
        cfg: Config,
        store: ManifestStore,
        ollama: OllamaClient | None = None,
    ) -> None:
        self._cfg = cfg.crawler
        self._store = store
        self._ollama = ollama
        self._seen_hashes: dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(self._cfg.concurrency)

    async def load_seeds(self, base_dir: Path) -> int:
        """Load local seed manifest files from the seeds directory.

        Validates and stores each manifest. If an Ollama client is available,
        embeds using nomic-embed-text. Otherwise stores with a dummy embedding
        (ChromaDB requires an embedding on upsert).
        """
        seeds_dir = base_dir / self._cfg.seeds_dir
        if not seeds_dir.exists():
            log.warning("Seeds directory not found: %s", seeds_dir)
            return 0

        count = 0
        for path in sorted(seeds_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.error("Failed to read %s: %s", path, e)
                continue

            result = validate_manifest(data)
            if not result.valid:
                log.error("Invalid manifest %s: %s", path.name, result.errors)
                continue
            for w in result.warnings:
                log.warning("%s: %s", path.name, w)

            domain = path.stem  # Use filename (without .json) as domain ID
            manifest_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

            if self._seen_hashes.get(domain) == manifest_hash:
                log.debug("Skipping %s — unchanged", domain)
                continue

            # Embed the description
            if self._ollama:
                embedding, _ = await self._ollama.embed_document(data["description"])
            else:
                # Dummy embedding for seed-only mode without Ollama
                embedding = [0.0] * 768

            self._store.upsert_manifest(domain, data, embedding)
            self._seen_hashes[domain] = manifest_hash
            log.info("Indexed seed: %s (%s)", domain, data["name"])
            count += 1

        return count

    async def crawl_domain(self, domain: str) -> bool:
        """Fetch and index a manifest from a single domain."""
        url = f"https://{domain}/.well-known/oap.json"

        # SSRF protection: validate URL doesn't resolve to private IP
        try:
            validate_url(url)
        except ValueError as e:
            log.warning("Blocked URL %s: %s", url, e)
            return False

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self._cfg.request_timeout) as client:
                    resp = await client.get(
                        url,
                        headers={"User-Agent": self._cfg.user_agent},
                        follow_redirects=True,
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                log.warning("Failed to fetch %s: %s", url, e)
                return False

        result = validate_manifest(data)
        if not result.valid:
            log.warning("Invalid manifest at %s: %s", domain, result.errors)
            return False

        manifest_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        if self._seen_hashes.get(domain) == manifest_hash:
            log.debug("Skipping %s — unchanged", domain)
            return True

        if not self._ollama:
            log.error("Ollama client required for crawling remote domains")
            return False

        embedding, _ = await self._ollama.embed_document(data["description"])
        self._store.upsert_manifest(domain, data, embedding)
        self._seen_hashes[domain] = manifest_hash
        log.info("Indexed: %s (%s)", domain, data["name"])
        return True

    def _load_domain_list(self, base_dir: Path) -> list[str]:
        """Load domains from the seeds file."""
        seeds_file = base_dir / self._cfg.seeds_file
        if not seeds_file.exists():
            return []
        domains = []
        for line in seeds_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                domains.append(line)
        return domains

    async def crawl_once(self, base_dir: Path) -> int:
        """Crawl all domains from seeds file once."""
        domains = self._load_domain_list(base_dir)
        if not domains:
            log.info("No domains in seeds file")
            return 0

        tasks = [self.crawl_domain(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if r is True)

    async def run(self, base_dir: Path) -> None:
        """Run continuous crawl loop."""
        log.info("Starting crawler (interval=%ds)", self._cfg.interval)
        while True:
            count = await self.crawl_once(base_dir)
            log.info("Crawl complete: %d domains indexed", count)
            await asyncio.sleep(self._cfg.interval)


@click.command("oap-crawl")
@click.option("--config", "-c", "config_path", default="config.yaml", help="Config file path")
@click.option("--seed", is_flag=True, help="Load local seed manifests and exit")
@click.option("--once", is_flag=True, help="Crawl seed domains once and exit")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def main(config_path: str, seed: bool, once: bool, verbose: bool) -> None:
    """OAP manifest crawler."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    base_dir = Path(config_path).parent
    cfg = load_config(config_path)
    store = ManifestStore(cfg.chromadb)

    async def _run() -> None:
        ollama: OllamaClient | None = None
        if not seed:
            ollama = OllamaClient(cfg.ollama)
            if not await ollama.healthy():
                log.error("Ollama is not reachable at %s", cfg.ollama.base_url)
                sys.exit(1)

        crawler = Crawler(cfg, store, ollama)

        try:
            if seed:
                count = await crawler.load_seeds(base_dir)
                click.echo(f"Indexed {count} seed manifests ({store.count()} total in store)")
            elif once:
                count = await crawler.crawl_once(base_dir)
                click.echo(f"Crawled {count} domains")
            else:
                await crawler.run(base_dir)
        finally:
            if ollama:
                await ollama.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
