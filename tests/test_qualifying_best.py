from types import SimpleNamespace
from unittest.mock import patch
import warnings

import pandas as pd
import pytest

from visualizations.qualifying_best import _valid_laps, make_qualifying_best


@pytest.mark.parametrize("name,prefix", [("Qualifying", "Q"), ("Sprint Qualifying", "SQ")])
def test_independent_bests_ratios_and_missing_sessions(name, prefix):
    laps = pd.DataFrame({
        "Driver": ["AAA", "AAA", "BBB", "BBB", "CCC"],
        "IsAccurate": [True, True, True, True, False],
        "Deleted": [False, False, False, True, False],
        "LapTime": pd.to_timedelta([100, 102, 107, 90, 80], unit="s"),
        "Sector1Time": pd.to_timedelta([30, 29, 31, 20, 19], unit="s"),
        "Sector2Time": pd.to_timedelta([30, 31, 32, 20, 19], unit="s"),
        "Sector3Time": pd.to_timedelta([40, 42, 44, 50, 42], unit="s"),
    })
    with patch.object(pd.DataFrame, "split_qualifying_sessions",
                      return_value=[laps.iloc[[0, 2]], laps.iloc[[1]], None], create=True):
        fig = make_qualifying_best(SimpleNamespace(name=name, laps=laps))
    assert list(fig.data[0].y) == [100, 107]
    assert list(fig.data[1].y) == [100, 107]
    combinations, modes = fig.layout.updatemenus
    assert len(combinations.buttons) == 16
    assert combinations.buttons[1].args[0]["y"][0] == [29, 31]
    assert combinations.buttons[4].label == f"{prefix}1 · ラップ"
    assert combinations.buttons[8].args[0]["y"][0] == [102]
    assert combinations.buttons[12].args[0]["y"][0] == []
    assert "有効なタイムなし" in combinations.buttons[12].args[1]["title.text"]
    assert combinations.buttons[1].args[0]["visible"] == [True, False, True]
    assert len(modes.buttons) == 2
    assert modes.buttons[0].args[0]["visible"] == [True, False, True]
    assert modes.buttons[1].args[0]["visible"] == [False, True, True]
    assert all(button.execute is False for button in modes.buttons)
    assert list(fig.data[2].cells.values[0]) == [1, 2]
    assert list(fig.data[2].cells.values[3]) == ["100.000%", "107.000%"]
    assert fig.data[0].text[0] == "100.000 s<br>100.000%"
    assert fig.data[0].textangle == 0
    assert fig.data[0].textposition == "inside"
    assert fig.data[0].insidetextanchor == "end"
    assert combinations.buttons[1].args[1]["yaxis.range"] == pytest.approx([28.69, 31.31])
    assert fig.data[0].marker.color == ("gray", "gray")
    assert list(fig.layout.yaxis.range) == pytest.approx([98.93, 108.07])
    assert fig.layout.height == 1500


def test_valid_filter_handles_nullable_object_flags_without_future_warning():
    laps = pd.DataFrame({
        "IsAccurate": pd.Series([True, None], dtype=object),
        "Deleted": pd.Series([False, None], dtype=object),
    })
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = _valid_laps(laps)
    assert len(result) == 1
