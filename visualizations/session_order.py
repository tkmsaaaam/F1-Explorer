"""Helpers for ordering session series by classification."""

from __future__ import annotations

from math import isfinite
from typing import Any

import pandas


def _numeric_position(value: Any) -> int | None:
    try:
        position = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(position) or position <= 0:
        return None
    return int(position)


def driver_order(session: Any) -> dict[str, int]:
    """Return driver-number-to-rank, with fastest-lap fallback.

    The session classification is preferred.  Practice and incomplete
    sessions sometimes lack a usable Position column, so their best recorded
    lap order is used for the remaining drivers.
    """
    ranks: dict[str, int] = {}
    try:
        results = session.results
    except Exception:
        results = None
    if isinstance(results, pandas.DataFrame) and not results.empty and "Position" in results.columns:
        for _, row in results.iterrows():
            position = _numeric_position(row.get("Position"))
            number = row.get("DriverNumber")
            if position is not None and pandas.notna(number):
                ranks[str(number)] = position

    try:
        laps = session.laps.dropna(subset=["LapTime"])
        best = laps.groupby("DriverNumber")["LapTime"].min().sort_values()
    except (AttributeError, KeyError, TypeError, ValueError):
        best = pandas.Series(dtype="object")
    next_rank = max(ranks.values(), default=0) + 1
    for number in best.index:
        key = str(number)
        if key not in ranks:
            ranks[key] = next_rank
            next_rank += 1
    return ranks


def driver_sort_key(number: Any, ranks: dict[str, int]) -> tuple[int, str]:
    """Return a stable key that puts unclassified drivers last."""

    key = str(number)
    return ranks.get(key, 1_000_000), key
