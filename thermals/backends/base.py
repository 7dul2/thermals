"""Backend interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from thermals.models import BackendInfo, Stability, TemperatureReading, ThermalState

log = logging.getLogger("thermals.backends")


class ThermalBackend(ABC):
    """A read-only source of temperature sensors and/or thermal state.

    Subclasses implement :meth:`available` and :meth:`sensors`; backends that
    know the system thermal pressure also override :meth:`thermal_state`.
    Backends must never write to hardware.
    """

    name: ClassVar[str] = "base"
    """Short identifier reported by ``thermals.backend()`` and the CLI."""

    stability: ClassVar[Stability] = Stability.STABLE
    """Whether the backend relies on public interfaces."""

    platforms: ClassVar[tuple[str, ...]] = ()
    """``platform.system()`` values the backend targets (informational)."""

    @abstractmethod
    def available(self) -> bool:
        """Return ``True`` if this backend can produce data on this system.

        Must not raise; return ``False`` and explain in :meth:`detail`.
        """

    @abstractmethod
    def sensors(self) -> list[TemperatureReading]:
        """Return every temperature reading the backend can currently obtain."""

    def thermal_state(self) -> ThermalState | None:
        """Return the system thermal pressure, or ``None`` if not provided."""
        return None

    def detail(self) -> str | None:
        """Human readable note on availability (for example why it is unavailable)."""
        return None

    def info(self) -> BackendInfo:
        """Describe the backend for ``thermals.list_backends()`` and the CLI."""
        try:
            avail = self.available()
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("backend %s availability check failed: %s", self.name, exc)
            avail = False
        return BackendInfo(
            name=self.name,
            available=avail,
            stability=self.stability,
            detail=self.detail(),
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
