"""Minimal ctypes bindings for CoreFoundation and IOKit.

Only the handful of calls the macOS backends need are exposed. Libraries are
loaded lazily so the modules import cleanly on other platforms (tests mock the
readers).
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import c_bool, c_char_p, c_int, c_long, c_uint32, c_void_p
from functools import lru_cache

from thermals.exceptions import BackendUnavailableError

CORE_FOUNDATION_PATH = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
IOKIT_PATH = "/System/Library/Frameworks/IOKit.framework/IOKit"
FOUNDATION_PATH = "/System/Library/Frameworks/Foundation.framework/Foundation"
LIBSYSTEM_PATH = "/usr/lib/libSystem.B.dylib"
LIBOBJC_PATH = "/usr/lib/libobjc.A.dylib"

kCFStringEncodingUTF8 = 0x08000100  # noqa: N816
kCFNumberSInt32Type = 3  # noqa: N816


def require_darwin() -> None:
    """Raise :class:`BackendUnavailableError` unless running on macOS."""
    if sys.platform != "darwin":
        raise BackendUnavailableError("macOS backends require Darwin")


class CoreFoundation:
    """Thin wrapper over the CoreFoundation calls used by thermals."""

    def __init__(self) -> None:
        require_darwin()
        lib = ctypes.CDLL(CORE_FOUNDATION_PATH)
        lib.CFStringCreateWithCString.restype = c_void_p
        lib.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
        lib.CFStringGetCString.restype = c_bool
        lib.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
        lib.CFNumberCreate.restype = c_void_p
        lib.CFNumberCreate.argtypes = [c_void_p, c_int, c_void_p]
        lib.CFDictionaryCreate.restype = c_void_p
        lib.CFDictionaryCreate.argtypes = [c_void_p, c_void_p, c_void_p, c_long, c_void_p, c_void_p]
        lib.CFArrayGetCount.restype = c_long
        lib.CFArrayGetCount.argtypes = [c_void_p]
        lib.CFArrayGetValueAtIndex.restype = c_void_p
        lib.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        lib.CFGetTypeID.restype = c_long
        lib.CFGetTypeID.argtypes = [c_void_p]
        lib.CFStringGetTypeID.restype = c_long
        lib.CFStringGetTypeID.argtypes = []
        lib.CFRelease.restype = None
        lib.CFRelease.argtypes = [c_void_p]
        self.lib = lib
        self._key_callbacks = ctypes.addressof(
            ctypes.c_char.in_dll(lib, "kCFTypeDictionaryKeyCallBacks")
        )
        self._value_callbacks = ctypes.addressof(
            ctypes.c_char.in_dll(lib, "kCFTypeDictionaryValueCallBacks")
        )

    def string(self, text: str) -> int:
        """Create a CFString (caller releases)."""
        ref = self.lib.CFStringCreateWithCString(None, text.encode("utf-8"), kCFStringEncodingUTF8)
        return int(ref or 0)

    def number(self, value: int) -> int:
        """Create a CFNumber holding a 32-bit int (caller releases)."""
        boxed = c_int(value)
        ref = self.lib.CFNumberCreate(None, kCFNumberSInt32Type, ctypes.byref(boxed))
        return int(ref or 0)

    def dictionary(self, items: dict[str, int]) -> int:
        """Create a CFDictionary from string keys and int values (caller releases)."""
        count = len(items)
        keys = (c_void_p * count)(*[self.string(k) for k in items])
        values = (c_void_p * count)(*[self.number(v) for v in items.values()])
        ref = self.lib.CFDictionaryCreate(
            None, keys, values, count, self._key_callbacks, self._value_callbacks
        )
        for k in keys:
            self.release(k)
        for v in values:
            self.release(v)
        return int(ref or 0)

    def to_str(self, ref: int | None) -> str | None:
        """Convert a CFString reference to ``str`` (does not release it)."""
        if not ref:
            return None
        if self.lib.CFGetTypeID(ref) != self.lib.CFStringGetTypeID():
            return None
        buf = ctypes.create_string_buffer(512)
        if self.lib.CFStringGetCString(ref, buf, len(buf), kCFStringEncodingUTF8):
            return buf.value.decode("utf-8", errors="replace")
        return None

    def array_count(self, ref: int | None) -> int:
        return int(self.lib.CFArrayGetCount(ref)) if ref else 0

    def array_get(self, ref: int, index: int) -> int | None:
        item = self.lib.CFArrayGetValueAtIndex(ref, index)
        return int(item) if item else None

    def release(self, ref: int | None) -> None:
        if ref:
            self.lib.CFRelease(ref)


@lru_cache(maxsize=1)
def core_foundation() -> CoreFoundation:
    """Shared :class:`CoreFoundation` instance."""
    return CoreFoundation()


@lru_cache(maxsize=1)
def iokit() -> ctypes.CDLL:
    """The IOKit framework."""
    require_darwin()
    return ctypes.CDLL(IOKIT_PATH)


@lru_cache(maxsize=1)
def libsystem() -> ctypes.CDLL:
    """libSystem (for ``mach_task_self``)."""
    require_darwin()
    lib = ctypes.CDLL(LIBSYSTEM_PATH)
    lib.mach_task_self.restype = c_uint32
    lib.mach_task_self.argtypes = []
    return lib
