"""Apple System Management Controller (SMC) backend.

The AppleSMC IOKit user client is not documented by Apple, but its interface
has been stable across Intel and Apple Silicon Macs for well over a decade and
is readable without root. Sensor *keys* are four-character codes whose meaning
Apple does not publish; the mapping below follows widely used conventions and
was verified under load on an M5 (``Tp``/``Te`` rise with CPU load, ``Tg`` is
the GPU). Confidence is therefore capped at ``MEDIUM``.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import struct
import sys
from collections.abc import Callable
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    c_char_p,
    c_int,
    c_size_t,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
)
from typing import ClassVar

from thermals.backends.base import ThermalBackend
from thermals.backends.macos._cf import iokit, libsystem, require_darwin
from thermals.exceptions import BackendError, BackendUnavailableError
from thermals.models import Confidence, SensorKind, Stability, TemperatureReading
from thermals.utils.temperature import is_plausible

log = logging.getLogger("thermals.backends.smc")

SOURCE = "applesmc"

KERNEL_INDEX_SMC = 2
SMC_CMD_READ_BYTES = 5
SMC_CMD_READ_INDEX = 8
SMC_CMD_READ_KEYINFO = 9
SMC_STRUCT_SIZE = 80


class _SMCVersion(Structure):
    _fields_ = [
        ("major", c_char),
        ("minor", c_char),
        ("build", c_char),
        ("reserved", c_char),
        ("release", c_uint16),
    ]


class _SMCPLimit(Structure):
    _fields_ = [
        ("version", c_uint16),
        ("length", c_uint16),
        ("cpu_plimit", c_uint32),
        ("gpu_plimit", c_uint32),
        ("mem_plimit", c_uint32),
    ]


class _SMCKeyInfo(Structure):
    _fields_ = [
        ("data_size", c_uint32),
        ("data_type", c_uint32),
        ("data_attributes", c_uint8),
    ]


class _SMCKeyData(Structure):
    _fields_ = [
        ("key", c_uint32),
        ("vers", _SMCVersion),
        ("p_limit", _SMCPLimit),
        ("key_info", _SMCKeyInfo),
        ("result", c_uint8),
        ("status", c_uint8),
        ("data8", c_uint8),
        ("data32", c_uint32),
        ("bytes", c_uint8 * 32),
    ]


assert ctypes.sizeof(_SMCKeyData) == SMC_STRUCT_SIZE


def _key_to_int(key: str) -> int:
    return int(struct.unpack(">I", key.encode("latin-1"))[0])


def _int_to_key(value: int) -> str:
    return struct.pack(">I", value).decode("latin-1")


def decode_smc_value(data_type: str, data: bytes) -> float | None:
    """Decode an SMC value of ``data_type`` into a float.

    Supports ``flt`` (little-endian float32, Apple Silicon), ``ioft`` (16.16
    fixed point), ``sp??``/``fp??`` fixed point families (Intel) and plain
    integers. Returns ``None`` for unsupported types or malformed data.
    """
    t = data_type
    try:
        if t == "flt " and len(data) == 4:
            return float(struct.unpack("<f", data)[0])
        if t == "ioft" and len(data) == 8:
            return float(struct.unpack("<Q", data)[0]) / 65536.0
        if len(t) == 4 and t[:2] in ("sp", "fp") and len(data) == 2:
            fraction_bits = int(t[3], 16)
            fmt = ">h" if t[0] == "s" else ">H"
            return float(struct.unpack(fmt, data)[0]) / float(1 << fraction_bits)
        if t == "ui8 " and len(data) == 1:
            return float(data[0])
        if t == "si8 " and len(data) == 1:
            return float(struct.unpack(">b", data)[0])
        if t == "ui16" and len(data) == 2:
            return float(struct.unpack(">H", data)[0])
        if t == "si16" and len(data) == 2:
            return float(struct.unpack(">h", data)[0])
        if t == "ui32" and len(data) == 4:
            return float(struct.unpack(">I", data)[0])
    except (struct.error, ValueError):
        return None
    return None


_FLOAT_TYPES_PREFIX = ("flt ", "ioft", "sp", "fp")


def is_temperature_type(data_type: str) -> bool:
    """Whether an SMC data type can hold a temperature value."""
    return data_type.startswith(_FLOAT_TYPES_PREFIX)


def classify_smc_key(key: str, apple_silicon: bool) -> tuple[SensorKind, Confidence, str]:
    """Map an SMC key to ``(kind, confidence, label)``.

    Unknown keys are kept (``UNKNOWN``/``LOW``) so that sensor enumeration is
    complete; they simply never win the CPU/GPU selection.
    """
    if apple_silicon:
        prefix = key[:2]
        if prefix == "Tp":
            return SensorKind.CPU_DIE, Confidence.MEDIUM, "CPU performance core"
        if prefix == "Te":
            return SensorKind.CPU_DIE, Confidence.MEDIUM, "CPU efficiency core"
        if prefix == "Tf":
            # M3 family: Tf0x/Tf4x are P-cores, Tf1x/Tf2x are GPU clusters.
            if key[2] in "04":
                return SensorKind.CPU_DIE, Confidence.MEDIUM, "CPU performance core"
            if key[2] in "12":
                return SensorKind.GPU, Confidence.MEDIUM, "GPU"
            return SensorKind.UNKNOWN, Confidence.LOW, key
        if prefix == "Tg":
            return SensorKind.GPU, Confidence.MEDIUM, "GPU"
        if key.startswith(("TPD", "TRD")):
            return SensorKind.SOC, Confidence.MEDIUM, "SoC die (PMU)"
        if key.startswith("TB") and key.endswith("T"):
            return SensorKind.UNKNOWN, Confidence.LOW, "Battery"
        if key.startswith("TH0"):
            return SensorKind.UNKNOWN, Confidence.LOW, "Storage"
        if key.startswith("TW0"):
            return SensorKind.UNKNOWN, Confidence.LOW, "Wireless"
        return SensorKind.UNKNOWN, Confidence.LOW, key

    # Intel Macs
    if key.startswith("TC") and key[3] in "DEF":
        return SensorKind.CPU_DIE, Confidence.MEDIUM, f"CPU die {key[2]}"
    if key.startswith("TC") and key[3] == "C" and key[2].isdigit():
        return SensorKind.CPU_CORE, Confidence.MEDIUM, f"CPU core {key[2]}"
    if key == "TCXC":
        return SensorKind.CPU_PACKAGE, Confidence.MEDIUM, "CPU package (PECI)"
    if key.startswith("TC") and key[3] == "P":
        return SensorKind.CPU_PACKAGE, Confidence.LOW, "CPU proximity"
    if key == "TCGC":
        return SensorKind.GPU, Confidence.MEDIUM, "GPU (PECI)"
    if key.startswith("TG") and key[3] == "D":
        return SensorKind.GPU, Confidence.MEDIUM, f"GPU die {key[2]}"
    if key.startswith("TG") and key[3] == "P":
        return SensorKind.GPU, Confidence.LOW, "GPU proximity"
    if key.startswith("TB") and key.endswith("T"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Battery"
    if key.startswith("TA") and key.endswith("P"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Ambient"
    if key.startswith("TH") and key.endswith("P"):
        return SensorKind.UNKNOWN, Confidence.LOW, "Storage"
    return SensorKind.UNKNOWN, Confidence.LOW, key


class SMCClient:
    """Read-only client for the AppleSMC IOKit user client."""

    def __init__(self) -> None:
        self._conn: int | None = None
        self._key_info: dict[str, tuple[int, str]] = {}
        self._keys: list[str] | None = None

    def open(self) -> None:
        if self._conn is not None:
            return
        require_darwin()
        lib = iokit()
        lib.IOServiceMatching.restype = c_void_p
        lib.IOServiceMatching.argtypes = [c_char_p]
        lib.IOServiceGetMatchingService.restype = c_uint32
        lib.IOServiceGetMatchingService.argtypes = [c_uint32, c_void_p]
        lib.IOServiceOpen.restype = c_int
        lib.IOServiceOpen.argtypes = [c_uint32, c_uint32, c_uint32, POINTER(c_uint32)]
        lib.IOServiceClose.restype = c_int
        lib.IOServiceClose.argtypes = [c_uint32]
        lib.IOObjectRelease.restype = c_int
        lib.IOObjectRelease.argtypes = [c_uint32]
        lib.IOConnectCallStructMethod.restype = c_int
        lib.IOConnectCallStructMethod.argtypes = [
            c_uint32,
            c_uint32,
            c_void_p,
            c_size_t,
            c_void_p,
            POINTER(c_size_t),
        ]
        service = lib.IOServiceGetMatchingService(0, lib.IOServiceMatching(b"AppleSMC"))
        if not service:
            raise BackendUnavailableError("AppleSMC service not found")
        conn = c_uint32(0)
        result = lib.IOServiceOpen(service, libsystem().mach_task_self(), 0, byref(conn))
        lib.IOObjectRelease(service)
        if result != 0:
            raise BackendUnavailableError(f"IOServiceOpen(AppleSMC) failed: 0x{result:x}")
        self._conn = conn.value

    def close(self) -> None:
        if self._conn is not None:
            iokit().IOServiceClose(self._conn)
            self._conn = None

    def _call(self, request: _SMCKeyData) -> _SMCKeyData:
        self.open()
        response = _SMCKeyData()
        size = c_size_t(SMC_STRUCT_SIZE)
        result = iokit().IOConnectCallStructMethod(
            self._conn,
            KERNEL_INDEX_SMC,
            byref(request),
            SMC_STRUCT_SIZE,
            byref(response),
            byref(size),
        )
        if result != 0:
            raise BackendError(f"IOConnectCallStructMethod failed: 0x{result:x}")
        return response

    def key_info(self, key: str) -> tuple[int, str] | None:
        """Return ``(size, type)`` for ``key`` or ``None`` if it does not exist."""
        cached = self._key_info.get(key)
        if cached is not None:
            return cached
        request = _SMCKeyData()
        request.key = _key_to_int(key)
        request.data8 = SMC_CMD_READ_KEYINFO
        response = self._call(request)
        if response.result != 0:
            return None
        info = (int(response.key_info.data_size), _int_to_key(response.key_info.data_type))
        self._key_info[key] = info
        return info

    def read(self, key: str) -> tuple[str, bytes] | None:
        """Return ``(type, raw bytes)`` for ``key``."""
        info = self.key_info(key)
        if info is None:
            return None
        size, data_type = info
        if size == 0 or size > 32:
            return None
        request = _SMCKeyData()
        request.key = _key_to_int(key)
        request.key_info.data_size = size
        request.key_info.data_type = _key_to_int(data_type)
        request.data8 = SMC_CMD_READ_BYTES
        response = self._call(request)
        if response.result != 0:
            return None
        return data_type, bytes(response.bytes[:size])

    def read_float(self, key: str) -> float | None:
        raw = self.read(key)
        if raw is None:
            return None
        return decode_smc_value(*raw)

    def keys(self) -> list[str]:
        """All SMC key names (enumerated once and cached)."""
        if self._keys is not None:
            return self._keys
        count_value = self.read_float("#KEY")
        count = int(count_value) if count_value else 0
        keys: list[str] = []
        for index in range(count):
            request = _SMCKeyData()
            request.data8 = SMC_CMD_READ_INDEX
            request.data32 = index
            response = self._call(request)
            if response.result != 0:
                continue
            keys.append(_int_to_key(response.key))
        self._keys = keys
        return keys

    def temperature_keys(self) -> list[str]:
        """Keys starting with ``T`` whose type can hold a temperature."""
        result: list[str] = []
        for key in self.keys():
            if not key.startswith("T"):
                continue
            info = self.key_info(key)
            if info and is_temperature_type(info[1]):
                result.append(key)
        return result

    def read_temperatures(self) -> list[tuple[str, float]]:
        """Return ``(key, value)`` for every temperature key with a decodable value."""
        out: list[tuple[str, float]] = []
        for key in self.temperature_keys():
            value = self.read_float(key)
            if value is not None:
                out.append((key, value))
        return out


def is_apple_silicon() -> bool:
    return platform.machine() == "arm64"


class AppleSMCBackend(ThermalBackend):
    """Temperature sensors from the SMC. Experimental: key semantics are undocumented."""

    name: ClassVar[str] = "apple_smc"
    stability: ClassVar[Stability] = Stability.EXPERIMENTAL
    platforms: ClassVar[tuple[str, ...]] = ("Darwin",)

    def __init__(
        self,
        reader: Callable[[], list[tuple[str, float]]] | None = None,
        apple_silicon: bool | None = None,
    ) -> None:
        self._client: SMCClient | None = None
        self._reader = reader
        self._apple_silicon = is_apple_silicon() if apple_silicon is None else apple_silicon
        self._error: str | None = None

    def _read(self) -> list[tuple[str, float]]:
        if self._reader is not None:
            return self._reader()
        if self._client is None:
            self._client = SMCClient()
        return self._client.read_temperatures()

    def available(self) -> bool:
        if self._reader is None and sys.platform != "darwin":
            self._error = "not running on macOS"
            return False
        try:
            readings = self._read()
        except Exception as exc:
            self._error = str(exc)
            log.debug("SMC unavailable: %s", exc)
            return False
        if not readings:
            self._error = "SMC exposes no temperature keys"
            return False
        self._error = None
        return True

    def detail(self) -> str | None:
        return self._error

    def sensors(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for key, value in self._read():
            # 0.0 means "sensor not populated" on every Mac seen so far.
            if value == 0.0 or not is_plausible(value):
                log.debug("skipping SMC key %s with implausible value %s", key, value)
                continue
            kind, confidence, label = classify_smc_key(key, self._apple_silicon)
            readings.append(
                TemperatureReading(
                    value=value,
                    kind=kind,
                    source=SOURCE,
                    name=f"{label} ({key})" if label != key else key,
                    confidence=confidence,
                )
            )
        return readings
