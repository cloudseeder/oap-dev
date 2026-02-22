#!/usr/bin/env python3
"""Manifest Factory — auto-generate OAP manifests from man pages via qwen3:4b.

Discovers GNU/Unix tools via apropos, reads their man pages, feeds each to
qwen3:4b with few-shot examples, and generates OAP manifests.

Usage:
    python scripts/manifest-factory.py              # Generate all
    python scripts/manifest-factory.py --dry-run    # Preview only
    python scripts/manifest-factory.py --tools sed,awk,cut,sort
    python scripts/manifest-factory.py --ollama-url http://localhost:11434
"""

from __future__ import annotations

import argparse
import json
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
    "nc", "ncat", "socat", "curl", "wget",
}

MAN_PAGE_MAX_CHARS = 2500

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3t:4b"


def load_example(name: str) -> str:
    """Load a gold-standard manifest as a JSON string."""
    path = MANIFESTS_DIR / f"{name}.json"
    return path.read_text().strip()


def build_system_prompt() -> str:
    """Build the system prompt with few-shot examples."""
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


def discover_tools() -> list[str]:
    """Discover section-1 tools via apropos."""
    try:
        result = subprocess.run(
            ["apropos", "-s", "1", ""],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("ERROR: apropos not available", file=sys.stderr)
        return []

    tools = set()
    for line in result.stdout.splitlines():
        # Format: "tool (1)            - description"
        # or:     "tool, alias (1)     - description"
        paren_idx = line.find("(")
        if paren_idx == -1:
            continue
        names_part = line[:paren_idx].strip()
        for name in names_part.split(","):
            name = name.strip()
            if name and name.isascii() and not name.startswith("-"):
                tools.add(name)

    return sorted(tools)


def is_allowed(tool: str) -> bool:
    """Check if a tool resolves to an allowed path."""
    resolved = shutil.which(tool)
    if resolved is None:
        return False
    return any(resolved.startswith(p) for p in ALLOWED_PREFIXES)


def get_man_page(tool: str) -> str | None:
    """Get plain-text man page for a tool, truncated."""
    try:
        result = subprocess.run(
            f"man {tool} 2>/dev/null | col -b",
            capture_output=True, text=True, timeout=15, shell=True,
        )
    except subprocess.TimeoutExpired:
        return None

    text = result.stdout.strip()
    if not text or result.returncode != 0:
        return None

    # Truncate to fit context window
    if len(text) > MAN_PAGE_MAX_CHARS:
        text = text[:MAN_PAGE_MAX_CHARS] + "\n[... truncated ...]"

    return text


def generate_manifest(
    tool: str,
    man_page: str,
    system_prompt: str,
    ollama_url: str,
) -> dict | None:
    """Call qwen3t:4b to generate a manifest from a man page."""
    user_prompt = f"""Here is the man page for `{tool}`:

{man_page}

Generate the OAP manifest JSON for `{tool}`."""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096},
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


def main():
    parser = argparse.ArgumentParser(description="OAP Manifest Factory")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be generated without writing files",
    )
    parser.add_argument(
        "--tools",
        help="Comma-separated list of specific tools to generate",
    )
    parser.add_argument(
        "--ollama-url", default=DEFAULT_OLLAMA_URL,
        help=f"Ollama API URL (default: {DEFAULT_OLLAMA_URL})",
    )
    args = parser.parse_args()

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

    # Discover or use specified tools
    if args.tools:
        tools = [t.strip() for t in args.tools.split(",")]
        print(f"Using specified tools: {tools}")
    else:
        print("Discovering tools via apropos...")
        tools = discover_tools()
        print(f"Found {len(tools)} section-1 commands")

    # Filter
    filtered = []
    skipped = {"blocklist": 0, "existing": 0, "not_found": 0}
    for tool in tools:
        if tool in BLOCKLIST:
            skipped["blocklist"] += 1
            continue
        if tool in existing:
            skipped["existing"] += 1
            continue
        if not is_allowed(tool):
            skipped["not_found"] += 1
            continue
        filtered.append(tool)

    print(f"After filtering: {len(filtered)} tools to process")
    print(f"  Skipped: {skipped['blocklist']} blocklisted, "
          f"{skipped['existing']} existing, "
          f"{skipped['not_found']} not in allowed paths")

    if not filtered:
        print("Nothing to do.")
        return

    # Build system prompt once
    system_prompt = build_system_prompt()

    # Process each tool
    stats = {"success": 0, "failed": 0, "no_man": 0, "invalid": 0}
    start_all = time.monotonic()

    for i, tool in enumerate(filtered, 1):
        prefix = f"[{i}/{len(filtered)}] {tool}"

        # Get man page
        man_page = get_man_page(tool)
        if not man_page:
            print(f"{prefix}: no man page, skipping")
            stats["no_man"] += 1
            continue

        if args.dry_run:
            print(f"{prefix}: would generate (man page: {len(man_page)} chars)")
            continue

        # Generate
        result = generate_manifest(tool, man_page, system_prompt, ollama_url)
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

        # Ensure required fields match the tool
        manifest["name"] = tool
        manifest["invoke"] = {"method": "stdio", "url": tool}
        manifest["oap"] = "1.0"

        # Write
        out_path = MANIFESTS_DIR / f"{tool}.json"
        out_path.write_text(json.dumps(manifest, indent=2) + "\n")

        warnings = f" (warnings: {'; '.join(validation['warnings'])})" if validation["warnings"] else ""
        print(f"{prefix}: OK — {tokens} tokens, {duration:.1f}s{warnings}")
        stats["success"] += 1

    elapsed = time.monotonic() - start_all

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Success: {stats['success']}")
    print(f"  Failed:  {stats['failed']}")
    print(f"  Invalid: {stats['invalid']}")
    print(f"  No man:  {stats['no_man']}")


if __name__ == "__main__":
    main()
