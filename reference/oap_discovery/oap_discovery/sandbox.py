"""macOS sandbox-exec wrapper for subprocess execution.

Wraps subprocess argv with sandbox-exec on macOS to deny file writes
except to a configurable sandbox directory. Graceful degradation on
Linux (unsandboxed, warning logged).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil

log = logging.getLogger("oap.sandbox")

# Module-level state, initialized once at startup
_enabled: bool = False
_sandbox_dir: str = ""
_profile: str = ""


def init(sandbox_dir: str) -> None:
    """Initialize sandbox state.

    Resolves symlinks, creates the sandbox directory, detects sandbox-exec
    on macOS, and builds the Seatbelt profile string.
    """
    global _enabled, _sandbox_dir, _profile

    _sandbox_dir = os.path.realpath(sandbox_dir)
    os.makedirs(_sandbox_dir, exist_ok=True)

    if '"' in _sandbox_dir:
        log.error("Sandbox dir contains quotes — cannot build Seatbelt profile: %s", _sandbox_dir)
        _enabled = False
        return

    if platform.system() != "Darwin":
        log.warning("Sandbox disabled — sandbox-exec is macOS-only (current platform: %s)", platform.system())
        _enabled = False
        return

    sb_path = shutil.which("sandbox-exec")
    if sb_path is None:
        log.warning("Sandbox disabled — sandbox-exec not found on PATH")
        _enabled = False
        return

    _profile = (
        '(version 1)\n'
        '(allow default)\n'
        '(deny file-write*)\n'
        f'(allow file-write* (subpath "{_sandbox_dir}"))\n'
        '(allow file-write* (subpath "/dev"))\n'
    )
    _enabled = True
    log.info("Sandbox enabled — writes restricted to %s", _sandbox_dir)


def wrap_argv(argv: list[str]) -> list[str]:
    """Wrap argv with sandbox-exec when enabled, pass through otherwise."""
    if not _enabled:
        return argv
    return ["/usr/bin/sandbox-exec", "-p", _profile, *argv]


def is_enabled() -> bool:
    """Return True if sandbox wrapping is active."""
    return _enabled


def get_sandbox_dir() -> str:
    """Return the resolved sandbox directory path."""
    return _sandbox_dir
