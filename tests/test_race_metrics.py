from datetime import datetime, timedelta

import pytest

from f1_explorer.visualizations.domain.driver import Driver
from f1_explorer.visualizations.domain.driver_laps import DriverLaps
from f1_explorer.visualizations.domain.lap import Lap
from f1_explorer.visualizations.domain.tyre import Tyre
from f1_explorer.visualizations.race_metrics import (
    gap_to_ahead,
    gap_to_leader,
    inclusive_lap_span,
    lap_times_by_position,
    top_time_map,
)


def _driver(
    number: int,
    positions: dict[int, int | None],
    at_by_lap: dict[int, timedelta | None] | None = None,
) -> DriverLaps:
    """Build a driver whose laps are evenly spaced on the session clock.

    ``at_by_lap`` optionally overrides the session-elapsed time of given
    lap numbers, including ``None`` for a lap without timing.
    """
    laps = {}
    for lap_number, position in positions.items():
        default_at = timedelta(seconds=lap_number * 80 + number)
        at = default_at if at_by_lap is None else at_by_lap.get(lap_number, default_at)
        laps[lap_number] = Lap(
            80.0,
            at,
            position,
            is_pit_out_lap=lap_number == 1,
            tyre=Tyre("Soft", True),
        )
    return DriverLaps(Driver(number, f"D{number}", "Team"), laps)


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


def test_position_less_laps_are_excluded_from_rank_ordered_metrics():
    """A missing position is not a fabricated rank one or a zero gap."""
    leader = _driver(1, {1: 1, 2: 1})
    follower = _driver(2, {1: 2, 2: None})

    assert list(top_time_map([follower, leader])) == [1, 2]
    assert 2 not in lap_times_by_position([follower, leader])[2]

    ahead = gap_to_ahead(follower, lap_times_by_position([follower, leader]))
    assert ahead[0][1] == 1.0
    assert ahead[1][1] is None
    to_leader = gap_to_leader(follower, top_time_map([leader, follower]))
    assert to_leader[0][1] == 1.0
    assert to_leader[1][1] is None


def test_untimed_laps_are_excluded_from_rank_ordered_metrics():
    """A lap without a session-elapsed time keeps its position but no gap."""
    leader = _driver(1, {1: 1, 2: 1}, {2: None})
    follower = _driver(2, {1: 2, 2: 2}, {2: None})

    positions = lap_times_by_position([follower, leader])
    assert 2 not in positions

    gaps_ahead = gap_to_ahead(follower, positions)
    assert gaps_ahead[0][1] == 1.0
    assert gaps_ahead[1][1] is None
    gaps_leader = gap_to_leader(follower, top_time_map([follower, leader]))
    assert gaps_leader[0][1] == 1.0
    assert gaps_leader[1][1] is None


def test_pit_out_attribute_and_compatibility_accessor_have_same_meaning():
    lap = _driver(1, {1: 1}).laps[1]
    assert lap.is_pit_out_lap is True
    assert lap.get_pit_out() is True


def test_lap_at_rejects_wallclock_datetime():
    """``at`` is a session-elapsed timedelta: wallclock times are a TypeError."""
    with pytest.raises(TypeError):
        Lap(80.0, datetime(2026, 1, 1), 1, is_pit_out_lap=False, tyre=Tyre("Soft", True))
