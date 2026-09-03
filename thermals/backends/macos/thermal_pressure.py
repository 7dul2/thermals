"""macOS thermal pressure via the public ``NSProcessInfo.thermalState`` API."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import CFUNCTYPE, c_char_p, c_long, c_void_p
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.backends.macos._cf import FOUNDATION_PATH, LIBOBJC_PATH, require_darwin
from thermals.exceptions import BackendError
from thermals.models import Stability, TemperatureReading, ThermalState

log = logging.getLogger("thermals.backends.thermal_pressure")

# NSProcessInfoThermalState: nominal=0, fair=1, serious=2, critical=3
THERMAL_STATE_BY_CODE: dict[int, ThermalState] = {
    0: ThermalState.NOMINAL,
    1: ThermalState.FAIR,
    2: ThermalState.SERIOUS,
    3: ThermalState.CRITICAL,
}


def map_thermal_state(code: int) -> ThermalState:
    """Map an ``NSProcessInfoThermalState`` integer to :class:`ThermalState`."""
    return THERMAL_STATE_BY_CODE.get(code, ThermalState.UNKNOWN)


def read_thermal_state_code() -> int:
    """Return ``[[NSProcessInfo processInfo] thermalState]`` as an integer."""
    require_darwin()
    objc = ctypes.CDLL(LIBOBJC_PATH)
    ctypes.CDLL(FOUNDATION_PATH)  # registers the Foundation classes with the runtime
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]
    send_object = ctypes.cast(objc.objc_msgSend, CFUNCTYPE(c_void_p, c_void_p, c_void_p))
    send_long = ctypes.cast(objc.objc_msgSend, CFUNCTYPE(c_long, c_void_p, c_void_p))

    cls = objc.objc_getClass(b"NSProcessInfo")
    if not cls:
        raise BackendError("NSProcessInfo class not found")
    process_info = send_object(cls, objc.sel_registerName(b"processInfo"))
    if not process_info:
        raise BackendError("[NSProcessInfo processInfo] returned nil")
    return int(send_long(process_info, objc.sel_registerName(b"thermalState")))


class ThermalPressureBackend(ThermalBackend):
    """System thermal pressure from Apple's public API. Provides no sensors."""

    name: ClassVar[str] = "thermal_pressure"
    stability: ClassVar[Stability] = Stability.STABLE
    platforms: ClassVar[tuple[str, ...]] = ("Darwin",)

    def __init__(self, reader: Callable[[], int] | None = None) -> None:
        self._reader = reader or read_thermal_state_code
        self._error: str | None = None

    def available(self) -> bool:
        if sys.platform != "darwin" and self._reader is read_thermal_state_code:
            self._error = "not running on macOS"
            return False
        try:
            self._reader()
        except Exception as exc:
            self._error = str(exc)
            log.debug("thermal pressure unavailable: %s", exc)
            return False
        self._error = None
        return True

    def detail(self) -> str | None:
        return self._error

    def sensors(self) -> list[TemperatureReading]:
        return []

    def thermal_state(self) -> ThermalState | None:
        try:
            return map_thermal_state(self._reader())
        except Exception as exc:
            log.debug("thermal pressure read failed: %s", exc)
            return None
