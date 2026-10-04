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
