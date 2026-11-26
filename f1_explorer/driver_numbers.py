"""Canonical driver numbers for FastF1 lookups and report grouping."""

from math import isfinite
from typing import Any, TypeVar

import pandas


def driver_number_key(value: Any) -> str | None:
    """Return a canonical text key for a driver number, or None if absent.

    Integer driver numbers survive pandas float upcasts: 1, 1.0, and "1"
    all map to "1".  Other values keep their text form.
    """
    try:
        if bool(pandas.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not isfinite(number):
        return None
    if number.is_integer():
        return str(int(number))
    return str(value)


_Frame = TypeVar("_Frame", bound=pandas.DataFrame)


def normalize_driver_numbers(laps: _Frame) -> _Frame:
    """Keep FastF1 frame metadata and leave the input untouched."""
    numbers = laps["DriverNumber"]
    keys = numbers.map(driver_number_key)
    if keys.equals(numbers):
        return laps
    return laps.assign(DriverNumber=keys)
