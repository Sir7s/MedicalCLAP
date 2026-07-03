"""Failpoint framework (P3, Freeze Profile §5).

Deterministic crash injection for reliability tests. Failpoints are DISABLED
unless explicitly enabled via the ``MEDCLIP_FAILPOINTS=1`` environment variable
(production images must leave them disabled — ``failpoints_disabled=true``).

A failpoint is armed by name, then `trip(name)` raises `Failpoint` the next time
it is reached (one-shot), simulating a crash at that exact point.
"""
from __future__ import annotations

import os

_ARMED: set[str] = set()


class Failpoint(RuntimeError):
    """Raised when an armed failpoint is tripped."""


def enabled() -> bool:
    return os.environ.get("MEDCLIP_FAILPOINTS", "0") == "1"


def arm(name: str) -> None:
    _ARMED.add(name)


def disarm(name: str) -> None:
    _ARMED.discard(name)


def clear() -> None:
    _ARMED.clear()


def is_armed(name: str) -> bool:
    return name in _ARMED


def trip(name: str) -> None:
    """Raise Failpoint if `name` is armed and failpoints are enabled (one-shot)."""
    if enabled() and name in _ARMED:
        _ARMED.discard(name)
        raise Failpoint(name)
