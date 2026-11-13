"""Pure calculations used by race visualizations.

The plotting module historically mixed FastF1 data-frame operations with
rendering and omitted the last lap in several series.  This module operates
only on the small domain objects and returns ordinary, ordered containers,
which makes the calculations useful in plots, tables, and tests alike.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import timedelta
from dataclasses import dataclass
from math import isfinite
from typing import TypeAlias

from f1_explorer.visualizations.domain.driver_laps import DriverLaps
from f1_explorer.visualizations.domain.lap import Lap

LapNumber: TypeAlias = int
LapSpan: TypeAlias = list[tuple[LapNumber, Lap | None]]
TimestampByLap: TypeAlias = dict[LapNumber, timedelta]
PositionTimesByLap: TypeAlias = dict[LapNumber, dict[int, timedelta]]
GapSeries: TypeAlias = list[tuple[LapNumber, float | None]]


def _ordered_driver_laps(driver_laps: Iterable[DriverLaps]) -> list[DriverLaps]:
    """Return drivers in a stable order without relying on set iteration."""
    return sorted(driver_laps, key=lambda item: (item.driver.number, item.driver.name))


def inclusive_lap_span(driver_laps: DriverLaps) -> LapSpan:
    """Return every lap number from the first through the final recorded lap.

    Missing timing records are represented by ``None``.  The upper endpoint is
    intentionally inclusive; this is important for a driver's final lap.
    An empty driver has an empty span.
    """
    if not driver_laps.laps:
        return []
    first = min(driver_laps.laps)
    final = max(driver_laps.laps)
    return [(number, driver_laps.laps.get(number)) for number in range(first, final + 1)]


def top_time_map(driver_laps: Sequence[DriverLaps]) -> TimestampByLap:
    """Map each lap number to the leader's timestamp for that lap.

    Laps without a position or session-elapsed time can never be the
    leader and are skipped.  If malformed input contains more than one
    position-one record for a lap, the earliest timestamp is chosen.
    Keys are inserted in ascending order, making iteration deterministic
    while retaining the useful mapping API.
    """
    result: dict[int, timedelta] = {}
    for driver in _ordered_driver_laps(driver_laps):
        for number, lap in sorted(driver.laps.items()):
            if lap.position is None or lap.position != 1 or lap.at is None:
                continue
            previous = result.get(number)
            if previous is None or lap.at < previous:
                result[number] = lap.at
    return dict(sorted(result.items()))


def lap_times_by_position(driver_laps: Sequence[DriverLaps]) -> PositionTimesByLap:
    """Map each lap to timestamps indexed by race position.

    The result has the shape ``{lap_number: {position: timestamp}}``.
    Laps without a position or session-elapsed time provide no mapping
    entry.  Both levels are sorted by their numeric keys.  A duplicate
    position uses the earliest timestamp, matching :func:`top_time_map`'s
    malformed-input rule.
    """
    unsorted: dict[int, dict[int, timedelta]] = {}
    for driver in _ordered_driver_laps(driver_laps):
        for number, lap in sorted(driver.laps.items()):
            if lap.position is None or lap.at is None:
                continue
            positions = unsorted.setdefault(number, {})
            previous = positions.get(lap.position)
            if previous is None or lap.at < previous:
                positions[lap.position] = lap.at
    return {
        number: dict(sorted(positions.items()))
        for number, positions in sorted(unsorted.items())
    }


def _position_records(
    all_drivers: Sequence[DriverLaps],
) -> dict[tuple[int, int], list[tuple[int, Lap]]]:
    """Index every positioned lap by ``(lap_number, position)``."""
    records: dict[tuple[int, int], list[tuple[int, Lap]]] = {}
    for driver in all_drivers:
        for number, lap in driver.laps.items():
            if lap.position is not None:
                records.setdefault((number, lap.position), []).append((driver.driver.number, lap))
    return records


def _observations_for(
    driver_laps: DriverLaps,
    records: dict[tuple[int, int], list[tuple[int, Lap]]],
    *,
    ahead: bool,
) -> list[GapObservation]:
    result: list[GapObservation] = []
    for number, lap in inclusive_lap_span(driver_laps):
        comparison = None
        seconds = None
        if lap is None or lap.position is None or lap.at is None:
            reason = "missing_own_record"
        elif len(records.get((number, lap.position), [])) != 1:
            reason = "ambiguous_own_position"
        elif ahead and lap.position <= 1:
            reason = "no_preceding_position"
        else:
            candidates = records.get((number, lap.position - 1 if ahead else 1), [])
            if len(candidates) != 1:
                reason = "ambiguous_comparison" if candidates else "missing_comparison"
            else:
                comparison, other = candidates[0]
                if other.at is None:
                    reason = "missing_comparison_time"
                else:
                    delta = (lap.at - other.at).total_seconds()
                    if not isfinite(delta) or delta < 0:
                        reason = "invalid_time_order"
                    else:
                        seconds, reason = delta, None
        result.append(GapObservation(number, seconds, comparison, reason))
    return result


def gap_observations(driver_laps: DriverLaps, all_drivers: Sequence[DriverLaps],
                     *, ahead: bool) -> list[GapObservation]:
    """Same-lap crossing differences with an identifiable, unique counterpart.

    Missing upstream crossings cannot always be detected from these records.
    No inference about the nearest car on track is made.
    """
    return _observations_for(driver_laps, _position_records(all_drivers), ahead=ahead)


def gap_observations_all(all_drivers: Sequence[DriverLaps],
                         *, ahead: bool) -> dict[int, list[GapObservation]]:
    """Compute :func:`gap_observations` for every driver over one shared index.

    Building the position index once avoids re-scanning all drivers for
    every driver when a whole table or figure is assembled.  Keys are
    driver numbers in the order the drivers are given.
    """
    records = _position_records(all_drivers)
    return {driver.driver.number: _observations_for(driver, records, ahead=ahead)
            for driver in all_drivers}


__all__ = [
    "GapObservation",
    "GapSeries",
    "LapSpan",
    "PositionTimesByLap",
    "TimestampByLap",
    "gap_observations",
    "gap_observations_all",
    "inclusive_lap_span",
    "lap_times_by_position",
    "top_time_map",
]


@dataclass(frozen=True, slots=True)
class GapObservation:
    lap_number: int
    seconds: float | None
    comparison_number: int | None
    reason: str | None
