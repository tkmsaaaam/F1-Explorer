"""Helpers for ordering session series by classification."""

from __future__ import annotations

from math import isfinite
from typing import Any

import pandas

from f1_explorer.driver_numbers import driver_number_key


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
    lap order is used for the remaining drivers.  Deleted laps do not
    contribute that fallback.
    """
    ranks: dict[str, int] = {}
    try:
        results = session.results
    except Exception:
        results = None
    if (
        isinstance(results, pandas.DataFrame)
        and not results.empty
        and "DriverNumber" in results.columns
        and "Position" in results.columns
    ):
        for number, position in zip(results["DriverNumber"], results["Position"]):
            key = driver_number_key(number)
            position = _numeric_position(position)
            if key is not None and position is not None:
                ranks[key] = position

    try:
        laps = session.laps.dropna(subset=["LapTime"])
        if "Deleted" in laps.columns:
            laps = laps[laps["Deleted"].ne(True).fillna(True)]
        best = laps.groupby("DriverNumber")["LapTime"].min().sort_values()
    except (AttributeError, KeyError, TypeError, ValueError):
        best = pandas.Series(dtype="object")
    next_rank = max(ranks.values(), default=0) + 1
    for number in best.index:
        key = driver_number_key(number)
        if key is not None and key not in ranks:
            ranks[key] = next_rank
            next_rank += 1
    return ranks


def driver_sort_key(number: Any, ranks: dict[str, int]) -> tuple[int, str]:
    """Return a stable key that puts unclassified drivers last."""

    key = driver_number_key(number) or ""
    return ranks.get(key, 1_000_000), key
