"""Checked scalar conversions at pandas and external-data boundaries."""

from collections.abc import Buffer
from typing import Protocol, SupportsFloat, SupportsIndex, SupportsInt, runtime_checkable


def as_float(value: object) -> float:
    if isinstance(value, (int, float, str, bytes, bytearray)):
        return float(value)
    if isinstance(value, (Buffer, SupportsFloat, SupportsIndex)):
        return float(value)
    raise TypeError("Value does not support float conversion")


def as_int(value: object) -> int:
    if isinstance(value, (int, float, str, bytes, bytearray)):
        return int(value)
    if isinstance(value, (Buffer, SupportsInt, SupportsIndex)):
        return int(value)
    raise TypeError("Value does not support integer conversion")


@runtime_checkable
class _SecondsValue(Protocol):
    def total_seconds(self) -> float: ...


def as_seconds(value: object) -> float:
    """Read seconds from a timedelta-like value without guessing its unit."""
    if isinstance(value, _SecondsValue):
        return value.total_seconds()
    raise TypeError("Value must provide total_seconds()")
