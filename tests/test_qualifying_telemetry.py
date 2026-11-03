from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from f1_explorer.visualizations.qualifying_telemetry import make_telemetry_comparison


def make_session():
    frames = []
    laps = []
    for number in (1, 2):
        frame = pd.DataFrame({
            "Distance": [0., 10., 10., 20., np.nan],
            "Time": pd.to_timedelta([0, number, number, 2 * number, 3], unit="s"),
            "Speed": [100., np.nan, 120., 130., 140.],
            "Throttle": [100., 90., 80., 70., 60.],
            "Brake": [False, False, True, False, False],
            "nGear": [3., 4., 4., 5., 6.],
        })
        data = Mock()
        data.add_distance.return_value = frame
        lap = SimpleNamespace(
            Driver=f"D{number}", Team="Team", LapTime=timedelta(seconds=number * 2),
            get_car_data=Mock(return_value=data),
        )
        frames.append(frame)
        laps.append(lap)
    session = SimpleNamespace(
        event=SimpleNamespace(year=2026),
        laps=SimpleNamespace(pick_drivers=lambda number: SimpleNamespace(
            pick_fastest=lambda: laps[int(number) - 1])),
    )
    return session, laps, frames


def build(session):
    with patch("f1_explorer.visualizations.qualifying_telemetry._ordered_quicklap_drivers", return_value=["1", "2"]), \
            patch("fastf1.plotting.get_team_color", return_value="gray"):
        return make_telemetry_comparison(session)


def test_reuses_car_data_preserving_values_and_input():
    session, laps, frames = make_session()
    originals = [frame.copy(deep=True) for frame in frames]
    figure = build(session)
    assert len(figure.data) == 10
    np.testing.assert_allclose(figure.data[0].x, [0, 5, 10, 15])
    np.testing.assert_allclose(figure.data[0].y, [0, 0, 0, 0])
    np.testing.assert_allclose(figure.data[5].y, [0, .5, 1, 1.5])
    for offset in (0, 5):
        np.testing.assert_allclose(figure.data[offset + 1].x, [0, 10, 20])
        np.testing.assert_allclose(figure.data[offset + 1].y, [100, 120, 130])
        np.testing.assert_allclose(figure.data[offset + 2].y, [100, 90, 80, 70])
        np.testing.assert_allclose(figure.data[offset + 3].y, [0, 0, 1, 0])
        np.testing.assert_allclose(figure.data[offset + 4].y, [3, 4, 4, 5])
        assert figure.data[offset + 4].line.shape == "hv"
    for lap, frame, original in zip(laps, frames, originals):
        lap.get_car_data.assert_called_once_with()
        lap.get_car_data.return_value.add_distance.assert_called_once_with()
        pd.testing.assert_frame_equal(frame, original)
    build(session)
    assert all(lap.get_car_data.call_count == 2 for lap in laps)


@pytest.mark.parametrize("missing", ["Time", "Speed", "Throttle", "Brake", "nGear"])
def test_missing_channel_only_omits_its_tab(missing):
    session, _, frames = make_session()
    frames[1].drop(columns=missing, inplace=True)
    figure = build(session)
    assert len(figure.data) == 9
    buttons = figure.layout.updatemenus[0].buttons
    missing_index = ["Time", "Speed", "Throttle", "Brake", "nGear"].index(missing)
    assert [sum(button.args[0]["visible"]) for button in buttons] == [
        1 if i == missing_index else 2 for i in range(5)
    ]


@pytest.mark.parametrize("failure", ["error", "empty"])
def test_unavailable_telemetry_is_not_retried(failure):
    session, laps, frames = make_session()
    if failure == "error":
        laps[1].get_car_data.side_effect = ValueError("unavailable")
    else:
        frames[1].drop(index=frames[1].index, inplace=True)
    assert len(build(session).data) == 5
    laps[1].get_car_data.assert_called_once_with()


def test_circuit_fetch_failure_keeps_telemetry_series():
    session, _, _ = make_session()
    session.get_circuit_info = Mock(side_effect=ConnectionError("map unavailable"))
    figure = build(session)
    assert len(figure.data) == 10
    assert len(figure.layout.annotations or ()) == 0
    session.get_circuit_info.assert_called_once_with()


def build_track_map(frames=None):
    from f1_explorer.visualizations.qualifying_telemetry import make_track_map_comparison

    session, laps, default_frames = make_session()
    if frames is None:
        frames = default_frames
    for frame in frames:
        if "X" not in frame:
            frame["X"] = [0., 1., 2., 3., np.nan][:len(frame)]
        if "Y" not in frame:
            frame["Y"] = [0., 2., 1., 0., 1.][:len(frame)]
    with patch("f1_explorer.visualizations.qualifying_telemetry._ordered_quicklap_drivers", return_value=["1", "2"]), \
            patch("f1_explorer.visualizations.qualifying_telemetry.lap_telemetry_without_driver_ahead",
                  side_effect=lambda lap: frames[laps.index(lap)]), \
            patch("fastf1.plotting.get_team_color", return_value="gray"):
        return make_track_map_comparison(session)


def test_track_map_initially_shows_only_first_speed_driver():
    figure = build_track_map()
    assert len(figure.data) == 4
    assert [trace.meta for trace in figure.data if trace.visible] == [
        {"driverNumber": "1", "metric": "Speed"}]
    assert figure.layout.title.text == "速度 — D1"
    assert figure.layout.meta["selectedDriver"] == "1"
    for menu in figure.layout.updatemenus:
        assert all(button.execute is False for button in menu.buttons)
    speed = figure.data[0]
    np.testing.assert_allclose(speed.x, [0, 2, 3])
    np.testing.assert_allclose(speed.customdata, [100, 120, 130])
    assert figure.data[1].marker.colorbar.tickvals == tuple(range(1, 9))


@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.parametrize("missing", ["Speed", "nGear", "all", "coordinates", "empty"])
def test_track_map_missing_channels_are_independent(missing):
    _, _, frames = make_session()
    if missing in ("Speed", "nGear"):
        frames[0].drop(columns=missing, inplace=True)
        frames[1][missing] = np.nan
    elif missing == "all":
        for frame in frames:
            frame[["Speed", "nGear"]] = np.nan
    elif missing == "coordinates":
        for frame in frames:
            frame["X"] = np.inf
    elif missing == "empty":
        for frame in frames:
            frame.drop(index=frame.index, inplace=True)
    figure = build_track_map(frames)
    if missing == "nGear":
        assert [trace.meta["metric"] for trace in figure.data] == ["Speed", "Speed"]
        assert sum(bool(trace.visible) for trace in figure.data) == 1
    else:
        assert not any(trace.visible for trace in figure.data)
        assert figure.layout.title.text == "速度 — 有効なデータなし"
        assert len(figure.layout.updatemenus[1].buttons) == 0
        assert len(figure.data) == (2 if missing == "Speed" else 0)


def test_track_map_initial_driver_skips_missing_speed():
    _, _, frames = make_session()
    frames[0]["Speed"] = np.nan
    figure = build_track_map(frames)
    assert [trace.meta for trace in figure.data if trace.visible] == [
        {"driverNumber": "2", "metric": "Speed"}]
    assert figure.layout.title.text == "速度 — D2"
