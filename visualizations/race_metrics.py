"""Pure calculations used by race visualizations.

The plotting module historically mixed FastF1 data-frame operations with
rendering and omitted the last lap in several series.  This module operates
only on the small domain objects and returns ordinary, ordered containers,
which makes the calculations useful in plots, tables, and tests alike.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import TypeAlias

from visualizations.domain.driver_laps import DriverLaps
from visualizations.domain.lap import Lap

LapNumber: TypeAlias = int
LapSpan: TypeAlias = list[tuple[LapNumber, Lap | None]]
TimestampByLap: TypeAlias = dict[LapNumber, datetime]
PositionTimesByLap: TypeAlias = dict[LapNumber, dict[int, datetime]]
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

    If malformed input contains more than one position-one record for a lap,
    the earliest timestamp is chosen.  Keys are inserted in ascending order,
    making iteration deterministic while retaining the useful mapping API.
    """
    result: dict[int, datetime] = {}
    for driver in _ordered_driver_laps(driver_laps):
        for number, lap in sorted(driver.laps.items()):
            if lap.position != 1:
                continue
            previous = result.get(number)
            if previous is None or lap.at < previous:
                result[number] = lap.at
    return dict(sorted(result.items()))


def lap_times_by_position(driver_laps: Sequence[DriverLaps]) -> PositionTimesByLap:
    """Map each lap to timestamps indexed by race position.

    The result has the shape ``{lap_number: {position: timestamp}}``.  Both
    levels are sorted by their numeric keys.  A duplicate position uses the
    earliest timestamp, matching :func:`top_time_map`'s malformed-input rule.
    """
    unsorted: dict[int, dict[int, datetime]] = {}
    for driver in _ordered_driver_laps(driver_laps):
        for number, lap in sorted(driver.laps.items()):
            positions = unsorted.setdefault(number, {})
            previous = positions.get(lap.position)
            if previous is None or lap.at < previous:
                positions[lap.position] = lap.at
    return {
        number: dict(sorted(positions.items()))
        for number, positions in sorted(unsorted.items())
    }


def _seconds_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds()


def gap_to_leader(
    driver_laps: DriverLaps,
    leader_times: Mapping[int, datetime] | None = None,
    *,
    top_times: Mapping[int, datetime] | None = None,
) -> GapSeries:
    """Return the driver's gap to the leader for each inclusive lap.

    A missing driver lap or missing leader timestamp yields ``None``.  A
    leader's own gap is therefore ``0.0`` when its timing record exists.
    ``top_times`` is a descriptive keyword alias for ``leader_times``.
    """
    if leader_times is not None and top_times is not None:
        raise TypeError("provide leader_times or top_times, not both")
    times = top_times if top_times is not None else leader_times
    if times is None:
        times = {}
    result: GapSeries = []
    for number, lap in inclusive_lap_span(driver_laps):
        leader = times.get(number)
        result.append((number, None if lap is None or leader is None else _seconds_between(lap.at, leader)))
    return result


def gap_to_ahead(
    driver_laps: DriverLaps,
    position_times: Mapping[int, Mapping[int, datetime]] | None = None,
    *,
    lap_times: Mapping[int, Mapping[int, datetime]] | None = None,
) -> GapSeries:
    """Return the driver's gap to the car immediately ahead.

    ``position_times`` normally comes from :func:`lap_times_by_position`.
    A leader (position one), an absent ahead car, or a missing timing record
    produces ``None`` rather than a fabricated zero gap.
    """
    if position_times is not None and lap_times is not None:
        raise TypeError("provide position_times or lap_times, not both")
    positions = lap_times if lap_times is not None else position_times
    if positions is None:
        positions = {}
    result: GapSeries = []
    for number, lap in inclusive_lap_span(driver_laps):
        if lap is None or lap.position <= 1:
            result.append((number, None))
            continue
        ahead = positions.get(number, {}).get(lap.position - 1)
        result.append((number, None if ahead is None else _seconds_between(lap.at, ahead)))
    return result


# Small compatibility aliases make the metric names easy to discover while
# callers migrate from the corresponding ``make_*`` helpers in race.py.
make_top_time_map = top_time_map
make_lap_times_by_position = lap_times_by_position
make_lap_start_by_position_by_number = lap_times_by_position
gap_to_top = gap_to_leader
gap_to_top_by_lap = gap_to_leader
gap_to_ahead_by_lap = gap_to_ahead
inclusive_lap_spans = inclusive_lap_span


__all__ = [
    "GapSeries",
    "LapSpan",
    "PositionTimesByLap",
    "TimestampByLap",
    "gap_to_ahead",
    "gap_to_ahead_by_lap",
    "gap_to_leader",
    "gap_to_top",
    "gap_to_top_by_lap",
    "inclusive_lap_span",
    "inclusive_lap_spans",
    "lap_times_by_position",
    "make_lap_start_by_position_by_number",
    "make_lap_times_by_position",
    "make_top_time_map",
    "top_time_map",
]
