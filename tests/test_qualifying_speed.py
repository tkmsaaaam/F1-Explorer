from types import SimpleNamespace
from unittest.mock import patch
import warnings

import pandas as pd
import pytest

from f1_explorer.visualizations.qualifying_speed import (
    _TowContext, _indexed_laps, _lap_telemetry, _valid_laps,
    make_qualifying_speed, _tow_mask,
)


def _telemetry(times, speeds):
    return pd.DataFrame({
        "Date": pd.to_datetime(times, unit="s"),
        "Distance": [0.0, 100.0, 200.0],
        "Speed": speeds,
    })


def test_tow_is_classified_at_each_telemetry_distance():
    cache = {
        0: ("AAA", _telemetry([10, 11, 12], [200, 310, 290])),
        1: ("BBB", _telemetry([9, 10, 11], [190, 300, 280])),
        2: ("CCC", _telemetry([5, 6, 7], [180, 290, 270])),
    }
    assert _tow_mask(0, cache).tolist() == [True, True, True]
    assert _tow_mask(1, cache).tolist() == [False, False, False]


def test_tow_context_preserves_threshold_and_caches_each_decision(monkeypatch):
    cache = {
        0: ("AAA", _telemetry([10, 11, 12], [200, 310, 290])),
        1: ("BBB", _telemetry([7, 8, 9], [190, 300, 280])),
        2: ("CCC", _telemetry([10, 10, 10], [180, 290, 270])),
    }
    context = _TowContext(pd.DataFrame(index=[0, 1, 2]), cache)
    calls = 0
    original = __import__("f1_explorer.visualizations.qualifying_speed", fromlist=["_tow_mask_prepared"])._tow_mask_prepared

    def counted(index, prepared):
        nonlocal calls
        calls += 1
        return original(index, prepared)

    monkeypatch.setattr("f1_explorer.visualizations.qualifying_speed._tow_mask_prepared", counted)
    first = context.mask(0)
    second = context.mask(0)
    assert first.tolist() == [False, True, True]
    assert second is first
    assert calls == 1


def test_lap_telemetry_drops_missing_and_keeps_first_duplicate_distance():
    class Lap:
        def get_car_data(self):
            return pd.DataFrame({
                "Date": pd.to_datetime([0, 1, 2, 3], unit="s"),
                "Distance": [0, 100, 100, 200],
                "Speed": [200, 250, 999, None],
            })

    result = _lap_telemetry(Lap())
    assert result["Distance"].tolist() == [0.0, 100.0]
    assert result["Speed"].tolist() == [200.0, 250.0]


def test_indexed_lap_lookup_keeps_first_duplicate_index():
    laps = pd.DataFrame({"Driver": ["AAA", "BBB"]}, index=[7, 7])
    assert _indexed_laps(laps)[7]["Driver"] == "AAA"


@pytest.mark.parametrize("name,prefix", [("Qualifying", "Q"), ("Sprint Qualifying", "SQ")])
def test_lap_selections_and_measurements_are_selectable(name, prefix):
    laps = pd.DataFrame({
        "Driver": ["AAA", "AAA", "BBB", "CCC"],
        "Team": ["A", "A", "B", "C"],
        "IsAccurate": [True, True, True, False],
        "Deleted": [False, False, False, False],
        "LapTime": pd.to_timedelta([90, 89, 91, 88], unit="s"),
        "SpeedFL": [300, 305, 310, 320],
        "SpeedI1": [280, 290, 285, 300],
        "SpeedI2": [250, 255, 260, 270],
        "SpeedST": [315, 320, 318, 330],
    })
    cache = {
        0: ("AAA", _telemetry([10, 11, 12], [280, 300, 290])),
        1: ("AAA", _telemetry([20, 21, 22], [285, 305, 295])),
        2: ("BBB", _telemetry([9, 10, 11], [290, 310, 300])),
    }
    with (patch.object(pd.DataFrame, "split_qualifying_sessions",
                       return_value=[laps.iloc[[0, 2]], laps.iloc[[1]], None], create=True),
          patch("f1_explorer.visualizations.qualifying_speed._telemetry_cache", return_value=cache),
          patch("fastf1.plotting.get_team_color",
                side_effect=lambda team, session: {"A": "red", "B": "blue"}.get(team, "gray"))):
        figure = make_qualifying_speed(SimpleNamespace(name=name, laps=laps))

    assert len(figure.data) == 24
    assert list(figure.data[0].x) == ["BBB", "AAA"]
    assert list(figure.data[0].y) == [310.0, 305.0]
    assert [trace.visible for trace in figure.data].count(True) == 1
    buttons = figure.layout.updatemenus[0].buttons
    assert len(buttons) == 24
    assert buttons[0].label == "全有効ラップ · フィニッシュライン"
    assert buttons[4].label == "全有効ラップ · ラップ中の最高速（トウあり）"
    assert buttons[5].label == "全有効ラップ · ラップ中の最高速（トウなし）"
    assert buttons[6].label == f"{prefix}1ベストラップ · フィニッシュライン"
    assert buttons[12].label == f"{prefix}2ベストラップ · フィニッシュライン"
    assert buttons[18].label == f"{prefix}3ベストラップ · フィニッシュライン"
    assert buttons[1].args[1]["yaxis.range"] == [280.0, 295.0]
    assert list(figure.layout.yaxis.range) == [300.0, 315.0]
    assert figure.layout.meta["f1ExplorerKind"] == "qualifyingSpeed"
    assert all(trace.textangle == 0 for trace in figure.data)


def test_valid_filter_handles_nullable_object_flags_without_future_warning():
    laps = pd.DataFrame({
        "IsAccurate": pd.Series([True, None], dtype=object),
        "Deleted": pd.Series([False, None], dtype=object),
    })
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = _valid_laps(laps)
    assert len(result) == 1
