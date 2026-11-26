"""Select personal fastest laps without a session-wide pace cutoff."""

from __future__ import annotations

from math import isfinite

from fastf1.core import Lap, Laps, Session

from f1_explorer.driver_numbers import driver_number_key, normalize_driver_numbers
from f1_explorer.scalars import as_seconds


def fastest_laps_by_driver(session: Session) -> dict[str, Lap]:
    """Return valid FastF1 fastest laps, ordered by time then driver-number text.

    Keep FastF1's default ``pick_fastest()`` selection rules. A missing, empty,
    nonfinite, or nonpositive result is unavailable, rather than a zero time.
    """
    selected: list[tuple[float, str, Lap]] = []
    laps = getattr(session, "laps", None)
    if laps is None:
        return {}
    if isinstance(laps, Laps) and "DriverNumber" in laps:
        laps = normalize_driver_numbers(laps)
    for driver_number in session.drivers:
        number = driver_number_key(driver_number)
        if number is None:
            continue
        try:
            lap = laps.pick_drivers(number).pick_fastest()
            if lap is None or lap.empty:
                continue
            seconds = as_seconds(lap.LapTime)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if isfinite(seconds) and seconds > 0:
            selected.append((seconds, number, lap))
    return {number: lap for _, number, lap in sorted(selected, key=lambda item: (item[0], item[1]))}
