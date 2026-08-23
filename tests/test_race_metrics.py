from datetime import datetime, timedelta

from visualizations.domain.driver import Driver
from visualizations.domain.driver_laps import DriverLaps
from visualizations.domain.lap import Lap
from visualizations.domain.tyre import Tyre
from visualizations.race_metrics import (
    gap_to_ahead,
    gap_to_leader,
    inclusive_lap_span,
    lap_times_by_position,
    top_time_map,
)


def _driver(number: int, positions: dict[int, int]) -> DriverLaps:
    start = datetime(2026, 1, 1)
    return DriverLaps(
        Driver(number, f"D{number}", "Team"),
        {
            lap_number: Lap(
                80.0,
                start + timedelta(seconds=lap_number * 80 + number),
                position,
                is_pit_out_lap=lap_number == 1,
                tyre=Tyre("Soft", True),
            )
            for lap_number, position in positions.items()
        },
    )


def test_metrics_include_final_lap_and_preserve_missing_laps():
    leader = _driver(1, {1: 1, 3: 1})
    follower = _driver(2, {1: 2, 2: 2, 3: 2})

    assert [number for number, _ in inclusive_lap_span(leader)] == [1, 2, 3]
    assert inclusive_lap_span(leader)[1][1] is None
    assert list(top_time_map([follower, leader])) == [1, 3]
    assert gap_to_leader(follower, top_time_map([leader, follower]))[-1][0] == 3


def test_gap_to_ahead_is_none_when_ahead_or_lap_is_absent():
    leader = _driver(1, {1: 1, 3: 1})
    follower = _driver(2, {1: 2, 2: 2, 3: 2})
    positions = lap_times_by_position([follower, leader])
    gaps = gap_to_ahead(follower, positions)

    assert gaps[0][1] is not None
    assert gaps[1][1] is None
    assert gaps[2][1] is not None


def test_pit_out_attribute_and_compatibility_accessor_have_same_meaning():
    lap = _driver(1, {1: 1}).laps[1]
    assert lap.is_pit_out_lap is True
    assert lap.get_pit_out() is True
