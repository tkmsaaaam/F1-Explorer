from __future__ import annotations

import warnings

from unittest.mock import Mock

import pandas as pd
import pytest

from f1_explorer.telemetry import lap_telemetry_without_driver_ahead


@pytest.mark.parametrize("frequency", ["original", 2])
def test_driver_ahead_free_lap_telemetry_matches_fastf1(frequency, monkeypatch):
    from fastf1.core import Lap, Session, Telemetry

    monkeypatch.setattr(Telemetry, "TELEMETRY_FREQUENCY", frequency)
    start = pd.Timestamp("2026-01-01", tz="UTC")
    class Event(dict):
        def get_session_date(self, *_args, **_kwargs):
            return start

    session = Session(Event(EventName="Test", EventDate=start), "Practice 1")
    session._t0_date = start
    car_time = pd.to_timedelta([0, 2, 4, 6, 8, 10, 12], unit="s")
    pos_time = pd.to_timedelta([0, 3, 6, 9, 12], unit="s")
    session._car_data = {"1": Telemetry({
        "Date": start + car_time, "SessionTime": car_time, "Time": car_time,
        "Speed": [100, 110, 120, 130, 140, 150, 160],
        "Throttle": [95, 96, 97, 98, 99, 100, 100],
        "nGear": [2, 3, 4, 4, 5, 6, 7], "Source": ["car"] * 7,
    }, session=session, driver="1")}
    session._pos_data = {"1": Telemetry({
        "Date": start + pos_time, "SessionTime": pos_time, "Time": pos_time,
        "X": [0, 3, 6, 9, 12], "Y": [1, 2, 3, 4, 5],
        "Z": [0] * 5, "Source": ["pos"] * 5,
    }, session=session, driver="1")}
    lap = Lap({
        "DriverNumber": "1", "LapNumber": 1,
        "LapStartTime": pd.to_timedelta(1, unit="s"),
        "Time": pd.to_timedelta(11, unit="s"),
        "LapTime": pd.to_timedelta(10, unit="s"),
    })
    lap.session = session
    car_original = session._car_data["1"].copy(deep=True)
    pos_original = session._pos_data["1"].copy(deep=True)
    ahead_calls = []
    def counted(self, *args, **kwargs):
        ahead_calls.append(1)
        return self.assign(DriverAhead="", DistanceToDriverAhead=float("nan"))

    monkeypatch.setattr(Telemetry, "add_driver_ahead", counted)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="The 'generic' unit for NumPy timedelta is deprecated.*",
            category=DeprecationWarning, module=r"fastf1\.core",
        )
        expected = lap.get_telemetry()
        assert ahead_calls
        ahead_calls.clear()
        actual = lap_telemetry_without_driver_ahead(lap)
        distance_expected = expected.add_distance()
        distance_actual = lap_telemetry_without_driver_ahead(lap, add_distance=True)

    assert ahead_calls == []
    required = ["Time", "Distance", "Speed", "X", "Y", "nGear"]
    assert set(required).issubset(actual.columns)
    for column in ["Time", "Distance", "Speed", "X", "Y", "nGear"]:
        pd.testing.assert_series_equal(actual[column], expected[column], check_names=True)
        pd.testing.assert_series_equal(distance_actual[column], distance_expected[column], check_names=True)
    assert actual.Distance.iloc[0] == pytest.approx(expected.Distance.iloc[0])
    if frequency == 2:
        assert len(actual) == len(expected)
    assert actual.SessionTime.iloc[0] == pd.to_timedelta(1, unit="s")
    assert actual.SessionTime.iloc[-1] == pd.to_timedelta(11, unit="s")
    assert distance_actual.Distance.iloc[0] == pytest.approx(0.0)
    pd.testing.assert_frame_equal(session._car_data["1"], car_original)
    pd.testing.assert_frame_equal(session._pos_data["1"], pos_original)


def test_fallback_preserves_normal_path_and_only_adds_distance_on_request():
    import pandas as pd

    frame = Mock()
    frame.add_distance.return_value = frame

    class LapLike:
        def get_telemetry(self):
            return frame

    assert lap_telemetry_without_driver_ahead(LapLike()) is frame
    assert lap_telemetry_without_driver_ahead(LapLike(), add_distance=True) is frame
    frame.add_distance.assert_called_once_with()


@pytest.mark.parametrize("failure", ["empty", "error"])
def test_fallback_handles_empty_telemetry_or_propagates_failure(failure):
    import pandas as pd

    class LapLike:
        def get_telemetry(self):
            if failure == "error":
                raise ValueError("telemetry unavailable")
            return pd.DataFrame()

    if failure == "empty":
        assert lap_telemetry_without_driver_ahead(LapLike()).empty
    else:
        with pytest.raises(ValueError, match="unavailable"):
            lap_telemetry_without_driver_ahead(LapLike())
