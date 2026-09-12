from types import SimpleNamespace
from unittest.mock import patch
import warnings

import pandas as pd

from visualizations.practice_comparison import _valid, make_practice_best, make_practice_speed


def _session(with_team=True):
    data = {
        "Driver": ["AAA", "BBB"],
        "IsAccurate": [True, True],
        "Deleted": [False, False],
        "LapTime": pd.to_timedelta([90.0, 91.0], unit="s"),
        "Sector1Time": pd.to_timedelta([30.0, 30.5], unit="s"),
        "Sector2Time": pd.to_timedelta([30.0, 30.5], unit="s"),
        "Sector3Time": pd.to_timedelta([30.0, 30.0], unit="s"),
        "SpeedFL": [320.0, 315.0], "SpeedI1": [300.0, 295.0],
        "SpeedI2": [280.0, 275.0], "SpeedST": [330.0, 325.0],
    }
    if with_team:
        data["Team"] = ["Team A", "Team B"]
    return SimpleNamespace(laps=pd.DataFrame(data), name="Practice 1")


def test_practice_best_labels_are_horizontal_and_colored():
    with patch("fastf1.plotting.get_team_color", side_effect=lambda team, session: {"Team A": "#111111", "Team B": "#222222"}[team]):
        figure = make_practice_best(_session())
    assert figure.data[0].textangle == 0
    assert figure.data[1].textangle == 0
    assert "<br>" in figure.data[0].text[0]
    for button in figure.layout.updatemenus[0].buttons:
        assert all("<br>" in label for labels in button.args[0]["text"][:2] for label in labels)
    assert list(figure.data[0].marker.color) == ["#111111", "#222222"]


def test_practice_speed_uses_padded_nonzero_ranges_and_team_colors():
    with patch("fastf1.plotting.get_team_color", side_effect=lambda team, session: {"Team A": "#111111", "Team B": "#222222"}[team]):
        figure = make_practice_speed(_session())
    assert list(figure.layout.yaxis.range) == [310.0, 325.0]
    assert list(figure.data[0].marker.color) == ["#111111", "#222222"]
    for button in figure.layout.updatemenus[0].buttons:
        assert button.args[1]["yaxis.range"] is not None
        assert button.args[1]["yaxis.autorange"] is False


def test_practice_comparisons_handle_missing_team_and_empty_data():
    session = _session(with_team=False)
    assert list(make_practice_best(session).data[0].marker.color) == ["gray", "gray"]
    assert list(make_practice_speed(session).data[0].marker.color) == ["gray", "gray"]
    empty = SimpleNamespace(laps=_session().laps.iloc[0:0], name="Practice 1")
    make_practice_best(empty)
    make_practice_speed(empty)


def test_practice_valid_filter_handles_nullable_object_flags_without_future_warning():
    laps = pd.DataFrame({
        "IsAccurate": pd.Series([True, None], dtype=object),
        "Deleted": pd.Series([False, None], dtype=object),
    })
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = _valid(laps)
    assert len(result) == 1
