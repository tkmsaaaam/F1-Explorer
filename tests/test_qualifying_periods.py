from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas
import pytest
from fastf1.core import Laps
from fastf1.exceptions import DataNotLoadedError

from f1_explorer.qualifying_periods import available_periods, qualifying_periods


def _laps(*lap_numbers: int) -> Laps:
    return Laps(pandas.DataFrame({"LapNumber": list(lap_numbers)}))


def _session(name, parts=(), error=None):
    laps = MagicMock()
    if error is not None:
        laps.split_qualifying_sessions.side_effect = error
    else:
        laps.split_qualifying_sessions.return_value = list(parts)
    return SimpleNamespace(name=name, laps=laps)


@pytest.mark.parametrize("name,prefix", [
    ("Qualifying", "Q"),
    ("Q", "Q"),
    ("Sprint Qualifying", "SQ"),
    ("Sprint Shootout", "SQ"),
    ("SQ", "SQ"),
])
def test_periods_use_report_labels_and_pad_missing_split_parts(name, prefix):
    q1 = _laps(1)
    periods = qualifying_periods(_session(name, [q1]))

    assert [label for label, _ in periods] == [f"{prefix}1", f"{prefix}2", f"{prefix}3"]
    assert periods[0][1] is q1
    assert [laps for _, laps in periods[1:]] == [None, None]


def test_periods_ignore_split_parts_beyond_q3():
    parts = [_laps(index) for index in range(1, 5)]

    periods = qualifying_periods(_session("Qualifying", parts))

    assert [laps for _, laps in periods] == parts[:3]


@pytest.mark.parametrize("error", [
    DataNotLoadedError("laps"),
    ValueError("Session status data is unavailable!"),
    IndexError("empty session status"),
    KeyError("Time"),
])
def test_unresolvable_split_returns_missing_periods_instead_of_raising(error):
    log = MagicMock()

    periods = qualifying_periods(_session("Qualifying", error=error), log=log)

    assert [laps for _, laps in periods] == [None, None, None]
    log.warning.assert_called_once_with(
        "Could not split qualifying sessions; using session laps", reason=str(error),
    )


def test_unresolvable_split_tolerates_a_session_without_a_name():
    laps = MagicMock()
    laps.split_qualifying_sessions.side_effect = ValueError("status")

    periods = qualifying_periods(SimpleNamespace(laps=laps))

    assert [label for label, _ in periods] == ["Q1", "Q2", "Q3"]


def test_available_periods_keeps_non_empty_periods_and_their_labels():
    q1, q3 = _laps(1), _laps(3)

    assert available_periods([("Q1", q1), ("Q2", None), ("Q3", q3)]) == [("Q1", q1), ("Q3", q3)]
    assert available_periods([("Q1", _laps())]) == []
