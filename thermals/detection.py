"""Backend selection.

Backends are chosen from ``platform.system()`` / ``platform.machine()`` and
probed lazily. Every backend that reports itself available contributes
sensors; the first available one is reported as the primary backend.
"""

from __future__ import annotations

import logging
import platform
import threading
from collections.abc import Sequence

from thermals.backends.base import ThermalBackend

log = logging.getLogger("thermals.detection")

_lock = threading.Lock()
_backends: list[ThermalBackend] | None = None
_override: list[ThermalBackend] | None = None


def candidate_backends(
    system: str | None = None, machine: str | None = None
) -> list[ThermalBackend]:
    """Instantiate the backends that apply to ``system``/``machine`` in priority order."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()

    if system == "Darwin":
        from thermals.backends.macos import (
            AppleSiliconHIDBackend,
            AppleSMCBackend,
            PowermetricsBackend,
            ThermalPressureBackend,
        )

        backends: list[ThermalBackend] = [ThermalPressureBackend(), AppleSMCBackend()]
        if machine == "arm64":
            backends.append(AppleSiliconHIDBackend())
        backends.append(PowermetricsBackend())
        return backends

    if system == "Windows":
        from thermals.backends.windows import ACPIThermalZoneBackend, LibreHardwareMonitorBackend

        return [LibreHardwareMonitorBackend(), ACPIThermalZoneBackend()]

    if system == "Linux":
        from thermals.backends.linux import HwmonBackend, ThermalZoneBackend

        return [HwmonBackend(), ThermalZoneBackend()]

    log.debug("no backends for platform %s/%s", system, machine)
    return []


def backends() -> list[ThermalBackend]:
    """The backend instances for this system (created once)."""
    global _backends
    if _override is not None:
        return list(_override)
    with _lock:
        if _backends is None:
            _backends = candidate_backends()
        return list(_backends)


def available_backends() -> list[ThermalBackend]:
    """Backends that currently report themselves as usable."""
    result: list[ThermalBackend] = []
    for backend in backends():
        try:
            if backend.available():
                result.append(backend)
        except Exception as exc:
            log.debug("backend %s availability check raised: %s", backend.name, exc)
    return result


def set_backends(custom: Sequence[ThermalBackend] | None) -> None:
    """Override backend detection (tests, custom backends). ``None`` restores auto-detection."""
    global _override
    _override = list(custom) if custom is not None else None


def reset() -> None:
    """Forget cached backend instances and overrides."""
    global _backends, _override
    with _lock:
        _backends = None
        _override = None


def debug_report() -> list[str]:
    """Human readable probe log for ``thermals --debug``."""
    lines = [f"platform: {platform.system()} {platform.release()} ({platform.machine()})"]
    for backend in backends():
        info = backend.info()
        state = "available" if info.available else "unavailable"
        line = f"backend {info.name}: {state} [{info.stability.value}]"
        if info.detail:
            line += f" - {info.detail}"
        lines.append(line)
    return lines
