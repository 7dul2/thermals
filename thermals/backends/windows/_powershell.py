"""Run PowerShell snippets without extra dependencies."""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("thermals.backends.windows")

_PRELUDE = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; "


def powershell_executable() -> str | None:
    """Locate ``powershell.exe`` (Windows PowerShell) or ``pwsh`` (PowerShell 7)."""
    return shutil.which("powershell") or shutil.which("pwsh")


def run_powershell(script: str, timeout: float = 15.0) -> str:
    """Execute ``script`` and return stdout. Raises ``RuntimeError`` on failure."""
    exe = powershell_executable()
    if exe is None:
        raise RuntimeError("PowerShell not found")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", _PRELUDE + script],
        capture_output=True,
        timeout=timeout,
        check=False,
        creationflags=creationflags,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        first_line = stderr.splitlines()[0] if stderr else f"exit code {result.returncode}"
        raise RuntimeError(first_line)
    return stdout
