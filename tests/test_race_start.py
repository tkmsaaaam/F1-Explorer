from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from fastf1.core import Laps

from visualizations.race_start import start_samples
from visualizations.race import speed_first_10s, speed_until_turn1


def session_fixture(name="Race"):
    times = pd.to_timedelta(np.arange(99, 122), unit="s")
    car = pd.DataFrame({"SessionTime": times, "Speed": [36.] * len(times)})
    return SimpleNamespace(
        name=name, session_start_time=pd.to_timedelta(100, unit="s"),
        event=SimpleNamespace(year=2026), drivers=["1", "2"],
        car_data={"1": car, "2": car.copy()},
        pos_data={str(driver): pd.DataFrame({
            "SessionTime": times, "X": (np.arange(99, 122) - 100) * 10 - offset,
            "Y": 0.,
        }) for driver, offset in [(1, 0), (2, 20)]},
        laps=Laps(pd.DataFrame({"DriverNumber": ["1", "2"], "Driver": ["D1", "D2"], "LapNumber": [1, 1],
                               "Time": pd.to_timedelta([121, 121], unit="s")})),
        get_driver=lambda driver: SimpleNamespace(Abbreviation=f"D{driver}"),
        get_circuit_info=lambda: SimpleNamespace(corners=pd.DataFrame({
            "X": [100.], "Y": [0.], "Distance": [999.],
        })),
    )


@pytest.mark.parametrize("name", ["Race", "Sprint"])
def test_start_clock_and_driver_local_corner_distance(name):
    session = session_fixture(name)
    samples, _ = start_samples(session, "1")
    assert samples.TimeSeconds.tolist() == list(range(11))
    assert samples.Distance.iloc[0] == 0
    assert samples.Distance.iloc[-1] == pytest.approx(100)
    first, corner1 = start_samples(session, "1", until_turn1=True)
    second, corner2 = start_samples(session, "2", until_turn1=True)
    assert corner1 == pytest.approx(100)
    assert corner2 == pytest.approx(120)
    assert first.Distance.iloc[0] == second.Distance.iloc[0] == 0
    with patch("visualizations.race.save_matplotlib") as save:
        speed_first_10s(MagicMock(), "speed_first_10s.png", session)
        speed_until_turn1(MagicMock(), "speed_until_turn1.png", session)
    assert len(save.call_args_list) == 2
    speed_axis = save.call_args_list[0].args[0].axes[0]
    assert list(speed_axis.lines[0].get_xdata()) == list(range(11))
    assert speed_axis.get_ylim()[0] <= 36
    corner_axis = save.call_args_list[1].args[0].axes[0]
    assert [line.get_xdata()[0] for line in corner_axis.lines[1::2]] == [100, 120]
    for call in save.call_args_list:
        plt.close(call.args[0])


def test_missing_start_or_position_is_not_replaced_with_fastest_lap():
    session = session_fixture()
    session.session_start_time = None
    assert start_samples(session, "1") is None
    session.session_start_time = pd.to_timedelta(100, unit="s")
    session.pos_data = {}
    assert start_samples(session, "1", until_turn1=True) is None
    assert start_samples(session, "1") is not None
    session.car_data["1"] = session.car_data["1"].iloc[3:]
    assert start_samples(session, "1") is None


def test_zero_boundary_is_interpolated_and_distance_integrates_speed():
    session = session_fixture()
    session.car_data["1"] = pd.DataFrame({
        "SessionTime": pd.to_timedelta([99, 101, 110], unit="s"),
        "Speed": [0., 7.2, 72.],
    })
    samples, _ = start_samples(session, "1")
    assert samples.Speed.iloc[0] == pytest.approx(3.6)
    assert samples.Distance.iloc[0] == 0
    assert samples.Distance.iloc[-1] == pytest.approx(100.5)


def test_corner_not_reached_and_pit_lane_position_are_omitted():
    session = session_fixture()
    session.pos_data["1"]["Y"] = 1000.
    assert start_samples(session, "1", until_turn1=True) is None
    session = session_fixture()
    session.pos_data["1"]["Status"] = "OffTrack"
    assert start_samples(session, "1", until_turn1=True) is None
    session = session_fixture()
    session.pos_data["1"] = session.pos_data["1"].iloc[:5]
    assert start_samples(session, "1", until_turn1=True) is None
