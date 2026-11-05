"""Select personal fastest laps without a session-wide pace cutoff."""

from __future__ import annotations

from math import isfinite

from fastf1.core import Lap, Session

from f1_explorer.scalars import as_seconds


def fastest_laps_by_driver(session: Session) -> dict[str, Lap]:
    """Return valid FastF1 fastest laps, ordered by time then driver-number text.

    Keep FastF1's default ``pick_fastest()`` selection rules. A missing, empty,
    nonfinite, or nonpositive result is unavailable, rather than a zero time.
    """
    selected: list[tuple[float, str, Lap]] = []
    for driver_number in session.drivers:
        number = str(driver_number)
        try:
            lap = session.laps.pick_drivers(number).pick_fastest()
            if lap is None or lap.empty:
                continue
            seconds = as_seconds(lap.LapTime)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if isfinite(seconds) and seconds > 0:
            selected.append((seconds, number, lap))
    return {number: lap for _, number, lap in sorted(selected, key=lambda item: (item[0], item[1]))}
