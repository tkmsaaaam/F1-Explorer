from datetime import datetime, timedelta

import pytest

from f1_explorer.visualizations.domain.driver import Driver
from f1_explorer.visualizations.domain.driver_laps import DriverLaps
from f1_explorer.visualizations.domain.lap import Lap
from f1_explorer.visualizations.domain.tyre import Tyre
from f1_explorer.visualizations.race_metrics import (
    gap_observations,
    gap_observations_all,
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


def test_gap_evidence_is_missing_when_ahead_or_lap_is_absent():
    leader = _driver(1, {1: 1, 3: 1})
    follower = _driver(2, {1: 2, 2: 2, 3: 2})
    observations = gap_observations(follower, [follower, leader], ahead=True)

    assert observations[0].seconds is not None
    assert observations[1].reason == "missing_comparison"
    assert observations[2].seconds is not None


def test_position_less_laps_are_excluded_from_rank_ordered_metrics():
    """A missing position is not a fabricated rank one or a zero gap."""
    leader = _driver(1, {1: 1, 2: 1})
    follower = _driver(2, {1: 2, 2: None})

    assert list(top_time_map([follower, leader])) == [1, 2]
    assert 2 not in lap_times_by_position([follower, leader])[2]

    ahead = gap_observations(follower, [follower, leader], ahead=True)
    assert ahead[0].seconds == 1.0
    assert ahead[1].reason == "missing_own_record"


def test_untimed_laps_are_excluded_from_rank_ordered_metrics():
    """A lap without a session-elapsed time keeps its position but no gap."""
    leader = _driver(1, {1: 1, 2: 1}, {2: None})
    follower = _driver(2, {1: 2, 2: 2}, {2: None})

    positions = lap_times_by_position([follower, leader])
    assert 2 not in positions

    ahead = gap_observations(follower, [follower, leader], ahead=True)
    assert ahead[0].seconds == 1.0
    assert ahead[1].reason == "missing_own_record"


def test_pit_out_attribute_and_compatibility_accessor_have_same_meaning():
    lap = _driver(1, {1: 1}).laps[1]
    assert lap.is_pit_out_lap is True
    assert lap.get_pit_out() is True


def test_lap_at_rejects_wallclock_datetime():
    """``at`` is a session-elapsed timedelta: wallclock times are a TypeError."""
    with pytest.raises(TypeError):
        Lap(80.0, datetime(2026, 1, 1), 1, is_pit_out_lap=False, tyre=Tyre("Soft", True))


def test_gap_evidence_preserves_comparison_and_rejects_ambiguity_and_negative():
    a = _driver(1, {1: 1}, {1: timedelta(seconds=80)})
    b = _driver(2, {1: 2}, {1: timedelta(seconds=83)})
    value = gap_observations(b, [a, b], ahead=True)[0]
    assert (value.seconds, value.comparison_number, value.reason) == (3, 1, None)
    assert gap_observations(a, [a, b], ahead=True)[0].reason == "no_preceding_position"
    duplicate = _driver(3, {1: 1}, {1: timedelta(seconds=81)})
    value = gap_observations(b, [a, b, duplicate], ahead=True)[0]
    assert value.seconds is None and value.reason == "ambiguous_comparison"
    early = _driver(2, {1: 2}, {1: timedelta(seconds=79)})
    assert gap_observations(early, [a, early], ahead=False)[0].reason == "invalid_time_order"
    assert gap_observations(b, [b], ahead=False)[0].reason == "missing_comparison"


def test_gap_observations_all_shares_one_index_across_drivers():
    a = _driver(1, {1: 1}, {1: timedelta(seconds=80)})
    b = _driver(2, {1: 2}, {1: timedelta(seconds=83)})
    result = gap_observations_all([a, b], ahead=True)
    assert result[1][0].reason == "no_preceding_position"
    assert (result[2][0].seconds, result[2][0].comparison_number) == (3, 1)


@pytest.mark.parametrize("ahead", [True, False])
def test_gap_evidence_lapped_and_red_flag_are_same_lap_crossings(ahead):
    a = _driver(1, {1: 1, 2: 1}, {1: timedelta(seconds=80), 2: timedelta(seconds=800)})
    b = _driver(2, {1: 2, 2: 2}, {1: timedelta(seconds=165), 2: timedelta(seconds=805)})
    observations = gap_observations(b, [a, b], ahead=ahead)
    assert [o.seconds for o in observations] == [85, 5]
    assert [o.comparison_number for o in observations] == [1, 1]


@pytest.mark.parametrize("at_a, at_b, expected", [(165, 162, 3), (180, 164, 16)])
def test_gap_evidence_leader_change_and_pit_swap(at_a, at_b, expected):
    a = _driver(1, {1: 1, 2: 2}, {1: timedelta(seconds=80), 2: timedelta(seconds=at_a)})
    b = _driver(2, {1: 2, 2: 1}, {1: timedelta(seconds=83), 2: timedelta(seconds=at_b)})
    for ahead in (True, False):
        value = gap_observations(a, [a, b], ahead=ahead)[-1]
        assert (value.seconds, value.comparison_number) == (expected, 2)


def test_gap_evidence_missing_time_and_duplicate_own_position():
    a = _driver(1, {1: 1}, {1: None})
    b = _driver(2, {1: 2})
    assert gap_observations(b, [a, b], ahead=True)[0].reason == "missing_comparison_time"
    assert gap_observations(a, [a, b], ahead=False)[0].reason == "missing_own_record"
    c = _driver(3, {1: 2})
    assert gap_observations(b, [a, b, c], ahead=True)[0].reason == "ambiguous_own_position"
