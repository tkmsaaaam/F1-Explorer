"""Synthetic telemetry fixtures shared by qualifying-telemetry figure tests."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

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
            Driver=f"D{number}", Team="Team", LapTime=timedelta(seconds=number * 2), empty=False,
            get_car_data=Mock(return_value=data),
        )
        frames.append(frame)
        laps.append(lap)
    session = SimpleNamespace(
        event=SimpleNamespace(year=2026),
        drivers=["2", "1"],
        laps=SimpleNamespace(pick_drivers=lambda number: SimpleNamespace(
            pick_fastest=lambda: laps[int(number) - 1])),
    )
    return session, laps, frames


def build(session):
    with patch("fastf1.plotting.get_team_color", return_value="gray"):
        return make_telemetry_comparison(session)
