#!/usr/bin/env python3
"""Manifest Factory — auto-generate OAP manifests from documentation via LLM.

Pluggable source adapters let the same factory generate manifests from any
documentation source: man pages, --help output, OpenAPI specs, etc.

Usage:
    python scripts/manifest-factory.py                              # man pages (default)
    python scripts/manifest-factory.py --source help --tools rg,fd  # --help output
    python scripts/manifest-factory.py --source openapi --spec petstore.json
    python scripts/manifest-factory.py --dry-run                    # preview only
"""

from __future__ import annotations

import abc
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

# --- Paths ---

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
MANIFESTS_DIR = REPO_ROOT / "reference" / "oap_discovery" / "manifests"


# --- Inline validation (mirrors oap_discovery.validate without pydantic) ---

def validate_manifest(data: dict) -> dict:
    """Validate a manifest dict. Returns {"valid": bool, "errors": [], "warnings": []}."""
    result = {"valid": True, "errors": [], "warnings": []}

    for key in ("oap", "name", "description", "invoke"):
        if key not in data:
            result["errors"].append(f"Missing required field: {key}")

    if result["errors"]:
        result["valid"] = False
        return result

    if data["oap"] != "1.0":
        result["errors"].append(f"Unsupported oap version: {data['oap']} (expected 1.0)")

    invoke = data.get("invoke", {})
    if not isinstance(invoke, dict):
        result["errors"].append("invoke must be an object")
    else:
        if "method" not in invoke:
            result["errors"].append("invoke.method is required")
        if "url" not in invoke:
            result["errors"].append("invoke.url is required")

    if "input" not in data:
        result["warnings"].append("Missing recommended field: input")
    if "output" not in data:
        result["warnings"].append("Missing recommended field: output")

    desc = data.get("description", "")
    if len(desc) > 1000:
        result["warnings"].append(f"Description is {len(desc)} chars (recommended max 1000)")

    if result["errors"]:
        result["valid"] = False

    return result


# --- Constants ---

ALLOWED_PREFIXES = ("/usr/bin/", "/usr/local/bin/", "/bin/", "/opt/homebrew/bin/")

BLOCKLIST = {
    # Dangerous / destructive
    "rm", "rmdir", "dd", "mkfs", "fdisk", "kill", "killall",
    "shutdown", "reboot", "halt", "init", "shred", "mknod",
    # Interactive / TUI
    "vim", "vi", "nano", "emacs", "less", "more", "top", "htop",
    "screen", "tmux", "bash", "sh", "zsh", "fish", "csh", "tcsh", "ksh",
    "ftp", "telnet", "ssh", "scp", "sftp",
    "dialog", "whiptail", "mc", "nnn", "ranger",
    "python", "python3", "perl", "ruby", "node", "lua",
    "gdb", "strace", "ltrace",
    # Privilege escalation
    "sudo", "su", "passwd", "chown", "chmod", "chgrp", "chroot",
    "newgrp", "sg",
    # Package managers
    "apt", "apt-get", "dpkg", "yum", "dnf", "pacman", "brew",
    "pip", "pip3", "npm", "gem", "cargo",
    # System admin
    "mount", "umount", "fsck", "modprobe", "insmod", "rmmod",
    "iptables", "ip6tables", "nft", "systemctl", "journalctl",
    "useradd", "userdel", "usermod", "groupadd", "groupdel",
    "crontab", "at",
    # Network tools that open connections
    "nc", "ncat", "socat", "curl", "wget", "finger",
}

BLOCKLIST_PREFIXES = ("perl", "git", "x86_64", "snmp")

MAN_PAGE_MAX_CHARS = 5000
HELP_MAX_CHARS = 5000

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3t:4b"


def load_example(name: str) -> str:
    """Load a gold-standard manifest as a JSON string."""
    path = MANIFESTS_DIR / f"{name}.json"
    return path.read_text().strip()


# --- Source Adapter Interface ---

class SourceAdapter(abc.ABC):
    """Base class for documentation source adapters."""

    name: str  # "manpage", "help", "openapi"

    @abc.abstractmethod
    def discover(self) -> list[str]:
        """Return a list of capability names to process."""

    @abc.abstractmethod
    def is_allowed(self, name: str) -> bool:
        """Return True if this capability should be processed."""

    @abc.abstractmethod
    def get_docs(self, name: str) -> str | None:
        """Return documentation text for the LLM, or None if unavailable."""

    @abc.abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt with source-specific rules and examples."""

    @abc.abstractmethod
    def fixup(self, name: str, manifest: dict) -> dict:
        """Post-generation fixup: enforce invoke spec, normalize fields."""

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """Add adapter-specific CLI arguments. Override if needed."""

    def configure(self, args: argparse.Namespace) -> None:
        """Receive parsed args. Override if needed."""


# --- ManPage Adapter ---

class ManPageAdapter(SourceAdapter):
    """Generate manifests from Unix man pages via apropos."""

    name = "manpage"

    def discover(self) -> list[str]:
        try:
            # "." matches any character — works on both Linux ("" works) and macOS ("" doesn't)
            result = subprocess.run(
                ["apropos", "-s", "1", "."],
                capture_output=True, text=True, timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("ERROR: apropos not available", file=sys.stderr)
            return []

        tools: set[str] = set()
        for line in result.stdout.splitlines():
            paren_idx = line.find("(")
            if paren_idx == -1:
                continue
            names_part = line[:paren_idx].strip()
            for name in names_part.split(","):
                name = name.strip()
                if name and name.isascii() and not name.startswith("-"):
                    tools.add(name)

        return sorted(tools)

    def is_allowed(self, name: str) -> bool:
        if name in BLOCKLIST:
            return False
        if any(name.startswith(p) for p in BLOCKLIST_PREFIXES):
            return False
        resolved = shutil.which(name)
        if resolved is None:
            return False
        return any(resolved.startswith(p) for p in ALLOWED_PREFIXES)

    def get_docs(self, name: str) -> str | None:
        try:
            result = subprocess.run(
                f"man {name} 2>/dev/null | col -b",
                capture_output=True, text=True, timeout=15, shell=True,
            )
        except subprocess.TimeoutExpired:
            return None

        text = result.stdout.strip()
        if not text or result.returncode != 0:
            return None

        if len(text) > MAN_PAGE_MAX_CHARS:
            text = text[:MAN_PAGE_MAX_CHARS] + "\n[... truncated ...]"

        return text

    def get_system_prompt(self) -> str:
        return _build_stdio_system_prompt()

    def fixup(self, name: str, manifest: dict) -> dict:
        manifest["name"] = name
        manifest["invoke"] = {"method": "stdio", "url": name}
        manifest["oap"] = "1.0"
        return manifest


# --- Help Adapter ---

class HelpAdapter(SourceAdapter):
    """Generate manifests from --help output for tools without man pages."""

    name = "help"

    def discover(self) -> list[str]:
        tools: set[str] = set()
        for prefix in ALLOWED_PREFIXES:
            p = Path(prefix)
            if not p.is_dir():
                continue
            for entry in p.iterdir():
                if entry.is_file() and os.access(entry, os.X_OK):
                    tools.add(entry.name)
        return sorted(tools)

    def is_allowed(self, name: str) -> bool:
        if name in BLOCKLIST:
            return False
        if any(name.startswith(p) for p in BLOCKLIST_PREFIXES):
            return False
        resolved = shutil.which(name)
        if resolved is None:
            return False
        return any(resolved.startswith(p) for p in ALLOWED_PREFIXES)

    def get_docs(self, name: str) -> str | None:
        try:
            result = subprocess.run(
                [name, "--help"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return None

        # --help may write to stdout or stderr
        text = (result.stdout or result.stderr or "").strip()
        if not text:
            return None

        if len(text) > HELP_MAX_CHARS:
            text = text[:HELP_MAX_CHARS] + "\n[... truncated ...]"

        return text

    def get_system_prompt(self) -> str:
        return _build_stdio_system_prompt()

    def fixup(self, name: str, manifest: dict) -> dict:
        manifest["name"] = name
        manifest["invoke"] = {"method": "stdio", "url": name}
        manifest["oap"] = "1.0"
        return manifest


# --- OpenAPI Adapter ---

class OpenAPIAdapter(SourceAdapter):
    """Generate manifests from OpenAPI/Swagger JSON specs."""

    name = "openapi"

    def __init__(self) -> None:
        self._spec: dict = {}
        self._base_url: str = ""
        self._endpoints: dict[str, dict] = {}  # name -> {method, path, op}

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--spec",
            help="Path or URL to an OpenAPI JSON spec (required for --source openapi)",
        )

    def configure(self, args: argparse.Namespace) -> None:
        spec_path = getattr(args, "spec", None)
        if not spec_path:
            print("ERROR: --spec is required for --source openapi", file=sys.stderr)
            sys.exit(1)

        # Load spec from URL or file
        if spec_path.startswith("http://") or spec_path.startswith("https://"):
            try:
                resp = httpx.get(spec_path, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                self._spec = resp.json()
            except Exception as e:
                print(f"ERROR: Failed to fetch spec from {spec_path}: {e}",
                      file=sys.stderr)
                sys.exit(1)
        else:
            try:
                self._spec = json.loads(Path(spec_path).read_text())
            except Exception as e:
                print(f"ERROR: Failed to read spec from {spec_path}: {e}",
                      file=sys.stderr)
                sys.exit(1)

        # Extract base URL
        # OpenAPI 3.x: servers[0].url
        # Swagger 2.x: host + basePath
        servers = self._spec.get("servers", [])
        if servers:
            self._base_url = servers[0].get("url", "").rstrip("/")
        else:
            host = self._spec.get("host", "localhost")
            base_path = self._spec.get("basePath", "")
            schemes = self._spec.get("schemes", ["https"])
            self._base_url = f"{schemes[0]}://{host}{base_path}".rstrip("/")

        # Index endpoints
        paths = self._spec.get("paths", {})
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method.startswith("x-") or method == "parameters":
                    continue
                if not isinstance(op, dict):
                    continue
                if op.get("deprecated", False):
                    continue

                op_id = op.get("operationId")
                if op_id:
                    name = op_id
                else:
                    # Synthesize name from method + path
                    clean_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
                    name = f"{method}_{clean_path}" if clean_path else method

                self._endpoints[name] = {
                    "method": method.upper(),
                    "path": path,
                    "op": op,
                }

    def discover(self) -> list[str]:
        return sorted(self._endpoints.keys())

    def is_allowed(self, name: str) -> bool:
        return name in self._endpoints

    def get_docs(self, name: str) -> str | None:
        ep = self._endpoints.get(name)
        if not ep:
            return None

        op = ep["op"]
        parts = [
            f"Endpoint: {ep['method']} {ep['path']}",
        ]

        summary = op.get("summary", "")
        if summary:
            parts.append(f"Summary: {summary}")

        description = op.get("description", "")
        if description:
            parts.append(f"Description: {description}")

        # Parameters
        params = op.get("parameters", [])
        if params:
            parts.append("Parameters:")
            for p in params:
                if not isinstance(p, dict):
                    continue
                required = " (required)" if p.get("required") else ""
                p_desc = p.get("description", "")
                schema = p.get("schema", {})
                p_type = schema.get("type", p.get("type", ""))
                parts.append(
                    f"  - {p.get('name', '?')} [{p.get('in', '?')}]"
                    f" ({p_type}){required}: {p_desc}"
                )

        # Request body (OpenAPI 3.x)
        request_body = op.get("requestBody", {})
        if isinstance(request_body, dict):
            content = request_body.get("content", {})
            for media_type, media_obj in content.items():
                if not isinstance(media_obj, dict):
                    continue
                schema = media_obj.get("schema", {})
                if schema:
                    parts.append(f"Request body ({media_type}):")
                    parts.append(f"  {json.dumps(schema, indent=2)}")
                break  # First content type only

        # Responses
        responses = op.get("responses", {})
        if responses:
            parts.append("Responses:")
            for status, resp_obj in responses.items():
                if not isinstance(resp_obj, dict):
                    continue
                r_desc = resp_obj.get("description", "")
                parts.append(f"  {status}: {r_desc}")
                # Include response schema if available
                content = resp_obj.get("content", {})
                for media_type, media_obj in content.items():
                    if not isinstance(media_obj, dict):
                        continue
                    schema = media_obj.get("schema", {})
                    if schema:
                        schema_str = json.dumps(schema, indent=2)
                        if len(schema_str) < 500:
                            parts.append(f"    Schema ({media_type}): {schema_str}")
                    break

        text = "\n".join(parts)
        if len(text) > MAN_PAGE_MAX_CHARS:
            text = text[:MAN_PAGE_MAX_CHARS] + "\n[... truncated ...]"

        return text

    def get_system_prompt(self) -> str:
        return f"""You generate OAP manifest JSON files for HTTP API endpoints.

An OAP manifest describes what an endpoint does so an LLM can discover and invoke it.

Rules:
- Output ONLY valid JSON, nothing else
- Required fields: "oap" (always "1.0"), "name", "description", "invoke"
- Recommended fields: "input", "output"
- invoke.method must match the HTTP method (GET, POST, PUT, DELETE, PATCH)
- invoke.url must be the full endpoint URL
- description: write for LLM discovery. Use specific verbs, mention key parameters, explain what the endpoint returns. Under 1000 characters.
- input.format: use "application/json" for JSON request bodies, "text/plain" for query-only endpoints
- input.description: describe the expected parameters and request body
- output.format: use "application/json" for JSON responses
- output.description: describe what the response contains
- Keep descriptions concise but informative — an LLM needs to decide if this endpoint fits a task

Base URL for this API: {self._base_url}

Example — a simple GET endpoint:
{{
  "oap": "1.0",
  "name": "listUsers",
  "description": "List all registered users. Returns a paginated JSON array of user objects with id, name, and email fields. Supports optional query parameters: limit (default 20, max 100) and offset for pagination.",
  "input": {{
    "format": "text/plain",
    "description": "Optional query parameters: limit (integer) and offset (integer) for pagination."
  }},
  "output": {{
    "format": "application/json",
    "description": "JSON array of user objects, each with id, name, and email."
  }},
  "invoke": {{
    "method": "GET",
    "url": "{self._base_url}/users"
  }}
}}

Example — a POST endpoint with JSON body:
{{
  "oap": "1.0",
  "name": "createUser",
  "description": "Create a new user account. Accepts a JSON body with name (string, required) and email (string, required). Returns the created user object with a server-assigned id.",
  "input": {{
    "format": "application/json",
    "description": "JSON object with name (string, required) and email (string, required)."
  }},
  "output": {{
    "format": "application/json",
    "description": "The created user object with id, name, and email."
  }},
  "invoke": {{
    "method": "POST",
    "url": "{self._base_url}/users"
  }}
}}"""

    def fixup(self, name: str, manifest: dict) -> dict:
        ep = self._endpoints.get(name, {})
        manifest["name"] = name
        manifest["oap"] = "1.0"
        if ep:
            manifest["invoke"] = {
                "method": ep["method"],
                "url": f"{self._base_url}{ep['path']}",
            }
        return manifest


# --- Shared helpers ---

def _build_stdio_system_prompt() -> str:
    """Build the system prompt for stdio tools (shared by manpage and help adapters)."""
    grep_example = load_example("grep")
    wc_example = load_example("wc")
    date_example = load_example("date")

    return f"""You generate OAP manifest JSON files for Unix command-line tools.

An OAP manifest describes what a tool does so an LLM can discover and invoke it.

Rules:
- Output ONLY valid JSON, nothing else
- Required fields: "oap" (always "1.0"), "name", "description", "invoke"
- Recommended fields: "input", "output"
- invoke.method is always "stdio", invoke.url is the command name
- description: write for LLM discovery. Use specific verbs, mention key flags, explain scope and limits. Under 1000 characters.
- input.description: if the tool reads from stdin, say so. If it takes command-line arguments, use the word "argument" in the description (this is critical for routing).
- input.format and output.format: use "text/plain" for text tools, "application/json" for JSON output
- Keep descriptions concise but informative — an LLM needs to decide if this tool fits a task

Here are three gold-standard examples:

Example 1 — stdin + args tool (text on stdin, pattern as argument):
{grep_example}

Example 2 — stdin-only tool (text on stdin, flags optional):
{wc_example}

Example 3 — args-only tool (no stdin needed):
{date_example}"""


# --- Adapter registry ---

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "manpage": ManPageAdapter,
    "help": HelpAdapter,
    "openapi": OpenAPIAdapter,
}


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="OAP Manifest Factory")
    parser.add_argument(
        "--source", choices=list(ADAPTERS.keys()), default="manpage",
        help="Documentation source adapter (default: manpage)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be generated without writing files",
    )
    parser.add_argument(
        "--tools",
        help="Comma-separated list of specific capabilities to generate",
    )
    parser.add_argument(
        "--ollama-url", default=DEFAULT_OLLAMA_URL,
        help=f"Ollama API URL (default: {DEFAULT_OLLAMA_URL})",
    )

    # Let all adapters add their args before parsing
    for adapter_cls in ADAPTERS.values():
        adapter_cls().add_args(parser)

    args = parser.parse_args()

    # Instantiate and configure the selected adapter
    adapter = ADAPTERS[args.source]()
    adapter.configure(args)

    ollama_url = args.ollama_url

    # Check Ollama is reachable (skip for dry runs)
    if not args.dry_run:
        try:
            resp = httpx.get(f"{ollama_url}/api/tags", timeout=10)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any(OLLAMA_MODEL in m for m in models):
                print(f"WARNING: {OLLAMA_MODEL} not found in Ollama. Available: {models}",
                      file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Cannot reach Ollama at {ollama_url}: {e}", file=sys.stderr)
            sys.exit(1)

    # Get existing manifests
    existing = {p.stem for p in MANIFESTS_DIR.glob("*.json")}
    print(f"Existing manifests: {len(existing)} ({', '.join(sorted(existing))})")

    # Discover or use specified capabilities
    if args.tools:
        names = [t.strip() for t in args.tools.split(",")]
        print(f"Using specified tools: {names}")
    else:
        print(f"Discovering via {adapter.name} adapter...")
        names = adapter.discover()
        print(f"Found {len(names)} capabilities")

    # Filter
    filtered = []
    skipped = {"disallowed": 0, "existing": 0}
    for name in names:
        if name in existing:
            skipped["existing"] += 1
            continue
        if not adapter.is_allowed(name):
            skipped["disallowed"] += 1
            continue
        filtered.append(name)

    print(f"After filtering: {len(filtered)} to process")
    print(f"  Skipped: {skipped['disallowed']} disallowed, "
          f"{skipped['existing']} existing")

    if not filtered:
        print("Nothing to do.")
        return

    # Build system prompt once
    system_prompt = adapter.get_system_prompt()

    # Process each capability
    stats = {"success": 0, "failed": 0, "no_docs": 0, "invalid": 0}
    start_all = time.monotonic()

    for i, name in enumerate(filtered, 1):
        prefix = f"[{i}/{len(filtered)}] {name}"

        # Get documentation
        docs = adapter.get_docs(name)
        if not docs:
            print(f"{prefix}: no docs, skipping")
            stats["no_docs"] += 1
            continue

        if args.dry_run:
            print(f"{prefix}: would generate (docs: {len(docs)} chars)")
            continue

        # Generate via LLM
        user_prompt = f"""Here is the documentation for `{name}`:

{docs}

Generate the OAP manifest JSON for `{name}`."""

        result = _generate_manifest(name, user_prompt, system_prompt, ollama_url)
        if result is None:
            print(f"{prefix}: generation failed")
            stats["failed"] += 1
            continue

        manifest = result["manifest"]
        tokens = result["tokens"]
        duration = result["duration_s"]

        # Validate
        validation = validate_manifest(manifest)
        if not validation["valid"]:
            print(f"{prefix}: invalid — {'; '.join(validation['errors'])}")
            stats["invalid"] += 1
            continue

        # Adapter-specific fixup
        manifest = adapter.fixup(name, manifest)

        # Write
        out_path = MANIFESTS_DIR / f"{name}.json"
        out_path.write_text(json.dumps(manifest, indent=2) + "\n")

        warnings = f" (warnings: {'; '.join(validation['warnings'])})" if validation["warnings"] else ""
        print(f"{prefix}: OK — {tokens} tokens, {duration:.1f}s{warnings}")
        stats["success"] += 1

    elapsed = time.monotonic() - start_all

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Success:  {stats['success']}")
    print(f"  Failed:   {stats['failed']}")
    print(f"  Invalid:  {stats['invalid']}")
    print(f"  No docs:  {stats['no_docs']}")


def _generate_manifest(
    name: str,
    user_prompt: str,
    system_prompt: str,
    ollama_url: str,
) -> dict | None:
    """Call qwen3t:4b to generate a manifest."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 8192},
        "think": False,
        "stream": False,
    }

    try:
        resp = httpx.post(
            f"{ollama_url}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f"  Ollama error: {e}", file=sys.stderr)
        return None

    data = resp.json()
    content = data.get("message", {}).get("content", "")
    tokens = data.get("eval_count", 0)
    duration_ns = data.get("eval_duration", 0)
    duration_s = duration_ns / 1e9 if duration_ns else 0

    try:
        manifest = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return None

    return {"manifest": manifest, "tokens": tokens, "duration_s": duration_s}


if __name__ == "__main__":
    main()
