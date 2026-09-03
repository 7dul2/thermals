from __future__ import annotations

import subprocess
from typing import Any

import pytest

from thermals.backends.windows import _powershell


def test_missing_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("thermals.backends.windows._powershell.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="PowerShell not found"):
        _powershell.run_powershell("Get-Date")


def test_run_powershell_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "thermals.backends.windows._powershell.shutil.which", lambda name: "/fake/powershell"
    )
    captured: dict[str, Any] = {}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b'{"ok":true}', stderr=b"")

    monkeypatch.setattr("thermals.backends.windows._powershell.subprocess.run", fake_run)
    assert _powershell.run_powershell("Get-Date") == '{"ok":true}'
    assert captured["args"][0] == "/fake/powershell"
    assert "-NoProfile" in captured["args"]
    assert captured["args"][-1].endswith("Get-Date")

    def failing_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Invalid namespace\nmore")

    monkeypatch.setattr("thermals.backends.windows._powershell.subprocess.run", failing_run)
    with pytest.raises(RuntimeError, match="Invalid namespace"):
        _powershell.run_powershell("Get-Date")
