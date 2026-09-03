"""Exception hierarchy for :mod:`thermals`.

The public API never raises these for "no sensor available" situations; it
degrades to ``None`` values and populates ``reason`` fields instead. Backends
raise them internally so the API layer can log and move on.
"""

from __future__ import annotations


class ThermalsError(Exception):
    """Base class for all errors raised by thermals."""


class BackendUnavailableError(ThermalsError):
    """The backend cannot be used on this system (wrong OS, missing service, ...)."""


class BackendError(ThermalsError):
    """The backend was available but failed while reading sensors."""
